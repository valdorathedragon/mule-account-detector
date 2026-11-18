"""IsolationForest anomaly scoring engine and account-level risk analysis API."""

from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FEATURES_PATH = PROJECT_ROOT / "data" / "upi_mule_features.csv"
SCORED_PATH = PROJECT_ROOT / "data" / "scored_upi_data.csv"
MODEL_PATH = PROJECT_ROOT / "models" / "iso_forest.joblib"

FEATURE_COLUMNS = ["amount", "Pass_Through_Ratio", "Near_Limit_Velocity"]
MODEL_PARAMS = {"n_estimators": 100, "contamination": 0.05, "random_state": 42}
HIGH_THRESHOLD = 80.0
MEDIUM_THRESHOLD = 50.0
NORMAL_CEILING = 79.99
MAX_DRIVERS = 5


@dataclass(frozen=True)
class _CacheRecord:
    """Immutable cache entry tying a scored DataFrame to its input and artifact digests."""

    features_sha256: str
    scored_sha256: str
    df: pd.DataFrame


_SCORED_CACHE: _CacheRecord | None = None


def _manifest_path_for(features_path: Path, scored_path: Path, model_path: Path) -> Path:
    """Derive a manifest path uniquely keyed to the (features, scored, model) artifact tuple."""
    key_src = f"{features_path.resolve()}|{scored_path.resolve()}|{model_path.resolve()}"
    digest = hashlib.sha256(key_src.encode("utf-8")).hexdigest()[:12]
    return model_path.parent / f".artifact_meta_{digest}.json"


def _create_temp_path(directory: Path, prefix: str, suffix: str, cleanup_list: list[Path]) -> Path:
    """Create a temporary file in `directory` and register it immediately for cleanup."""
    fd, name = tempfile.mkstemp(dir=directory, prefix=prefix, suffix=suffix)
    os.close(fd)
    path = Path(name)
    cleanup_list.append(path)
    return path


def _sha256_bytes(data: bytes) -> str:
    """Return SHA-256 hex digest for raw bytes."""
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    """Return SHA-256 hex digest for an existing file."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_risk_scores(raw_scores: np.ndarray) -> np.ndarray:
    """Map IsolationForest decision scores to 0-100, anchoring the model boundary (0) at 80.

    Anomalies (raw < 0):  Risk = 80 + 20 * (raw / raw_min)       -> [80, 100]
    Inliers   (raw >= 0): Risk = 79.99 * (1 - raw / raw_max)     -> [0, 79.99]
    """
    raw = np.asarray(raw_scores, dtype=float)
    raw_min = min(float(raw.min()), -1e-9)
    raw_max = max(float(raw.max()), 1e-9)
    risk = np.where(
        raw < 0.0,
        HIGH_THRESHOLD + (100.0 - HIGH_THRESHOLD) * (raw / raw_min),
        NORMAL_CEILING * (1.0 - raw / raw_max),
    )
    return np.round(np.clip(risk, 0.0, 100.0), 2)


def assign_risk_tier(score: float) -> str:
    """Return HIGH (>=80), MEDIUM (50-79.99) or LOW (<50)."""
    if score >= HIGH_THRESHOLD:
        return "HIGH"
    if score >= MEDIUM_THRESHOLD:
        return "MEDIUM"
    return "LOW"


def train_and_score(
    features_path: Path = FEATURES_PATH,
    scored_path: Path = SCORED_PATH,
    model_path: Path = MODEL_PATH,
) -> pd.DataFrame:
    """Train IsolationForest, stage immutable generation artifacts, and publish atomically."""
    global _SCORED_CACHE
    model_path.parent.mkdir(parents=True, exist_ok=True)
    scored_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = _manifest_path_for(features_path, scored_path, model_path)
    gen_root = model_path.parent / "generations"
    gen_root.mkdir(parents=True, exist_ok=True)

    for _attempt in range(2):
        raw_features = features_path.read_bytes()
        features_sha256 = _sha256_bytes(raw_features)
        df = pd.read_csv(io.BytesIO(raw_features))
        X = df[FEATURE_COLUMNS].astype(float)

        model = IsolationForest(**MODEL_PARAMS)
        model.fit(X)
        raw_scores = model.decision_function(X)

        df["Anomaly_Score_Raw"] = np.round(raw_scores, 6)
        df["Risk_Score"] = normalize_risk_scores(raw_scores)
        df["Risk_Tier"] = df["Risk_Score"].map(assign_risk_tier)
        df["Is_Anomaly"] = (model.predict(X) == -1).astype(int)

        gen_id = f"{features_sha256[:12]}_{os.urandom(4).hex()}"
        gen_dir = gen_root / gen_id
        gen_dir.mkdir(parents=True, exist_ok=True)
        gen_model = gen_dir / "iso_forest.joblib"
        gen_scored = gen_dir / "scored_upi_data.csv"

        cleanup_paths: list[Path] = []
        try:
            tmp_model = _create_temp_path(model_path.parent, ".model_", ".joblib.tmp", cleanup_paths)
            tmp_scored = _create_temp_path(scored_path.parent, ".scored_", ".csv.tmp", cleanup_paths)
            tmp_meta = _create_temp_path(manifest_path.parent, ".meta_", ".json.tmp", cleanup_paths)

            bundle = {
                "model": model,
                "features": FEATURE_COLUMNS,
                "params": MODEL_PARAMS,
                "features_sha256": features_sha256,
            }
            joblib.dump(bundle, gen_model)
            df.to_csv(gen_scored, index=False)

            if _sha256_file(features_path) != features_sha256:
                continue

            model_sha256 = _sha256_file(gen_model)
            scored_sha256 = _sha256_file(gen_scored)

            # Update canonical artifact paths via temp files, then commit the immutable
            # generation pointer atomically as the single source of truth for readers.
            joblib.dump(bundle, tmp_model)
            df.to_csv(tmp_scored, index=False)
            meta_payload = {
                "generation_id": gen_id,
                "features_sha256": features_sha256,
                "model_sha256": model_sha256,
                "scored_sha256": scored_sha256,
                "model_file": str(gen_model.resolve()),
                "scored_file": str(gen_scored.resolve()),
            }
            tmp_meta.write_text(json.dumps(meta_payload), encoding="utf-8")

            os.replace(tmp_model, model_path)
            os.replace(tmp_scored, scored_path)
            os.replace(tmp_meta, manifest_path)

            if features_path == FEATURES_PATH and scored_path == SCORED_PATH and model_path == MODEL_PATH:
                _SCORED_CACHE = _CacheRecord(
                    features_sha256=features_sha256,
                    scored_sha256=scored_sha256,
                    df=df.copy(),
                )
            return df
        finally:
            for path in cleanup_paths:
                path.unlink(missing_ok=True)

    raise RuntimeError(f"Features file changed repeatedly during training: {features_path}")


def _resolve_valid_generation() -> tuple[str, str, pd.DataFrame] | None:
    """Resolve the active immutable generation once and validate it against FEATURES_PATH."""
    manifest_path = _manifest_path_for(FEATURES_PATH, SCORED_PATH, MODEL_PATH)
    if not (FEATURES_PATH.exists() and manifest_path.exists()):
        return None
    try:
        meta = json.loads(manifest_path.read_text(encoding="utf-8"))
        features_sha256 = _sha256_file(FEATURES_PATH)
        if meta.get("features_sha256") != features_sha256:
            return None

        gen_scored = Path(meta["scored_file"])
        gen_model = Path(meta["model_file"])
        if not (gen_scored.exists() and gen_model.exists()):
            return None

        scored_bytes = gen_scored.read_bytes()
        scored_sha256 = _sha256_bytes(scored_bytes)
        if meta.get("scored_sha256") != scored_sha256:
            return None
        if _sha256_file(gen_model) != meta.get("model_sha256"):
            return None

        cached = _SCORED_CACHE
        if (
            cached is not None
            and cached.features_sha256 == features_sha256
            and cached.scored_sha256 == scored_sha256
        ):
            return features_sha256, scored_sha256, cached.df.copy()

        df = pd.read_csv(io.BytesIO(scored_bytes))
        return features_sha256, scored_sha256, df
    except Exception:
        return None


def load_scored_data() -> pd.DataFrame:
    """Load the scored dataset as a fresh copy, retraining if artifacts are missing or stale."""
    global _SCORED_CACHE
    if not FEATURES_PATH.exists():
        raise FileNotFoundError(f"Feature dataset not found: {FEATURES_PATH}")

    resolved = _resolve_valid_generation()
    if resolved is None:
        return train_and_score().copy()

    features_sha256, scored_sha256, df = resolved
    _SCORED_CACHE = _CacheRecord(
        features_sha256=features_sha256,
        scored_sha256=scored_sha256,
        df=df.copy(),
    )
    return df.copy()


def _build_top_drivers(
    account_id: str,
    incoming: pd.DataFrame,
    outgoing: pd.DataFrame,
    pass_through_ratio: float,
    df: pd.DataFrame,
) -> list[str]:
    """Derive human-readable risk drivers from account behaviour."""
    drivers: list[str] = []
    combined = pd.concat([incoming, outgoing])
    involved = (
        combined.drop_duplicates(subset=["txn_id"])
        if "txn_id" in combined.columns
        else combined.drop_duplicates()
    )

    if pass_through_ratio >= 0.8:
        drivers.append(f"High Pass-Through Ratio: {pass_through_ratio:.2%} of inflow moved out")

    near_limit = int(involved["Near_Limit_Velocity"].sum())
    if near_limit > 0:
        drivers.append(f"{near_limit} near-limit UPI transfer(s) in INR 90,000-1,00,000 range")

    if not incoming.empty and not outgoing.empty:
        first_in = pd.to_datetime(incoming["timestamp"]).min()
        first_out = pd.to_datetime(outgoing["timestamp"]).min()
        lag_min = (first_out - first_in).total_seconds() / 60.0
        if 0.0 <= lag_min <= 60.0:
            drivers.append(f"Rapid turnaround: first debit {lag_min:.0f} min after first credit")

    fan_in = incoming["nameOrig"].nunique()
    if fan_in >= 5:
        drivers.append(f"Fan-In topology: {fan_in} unique remitters")

    fan_out = outgoing["nameDest"].nunique()
    if fan_out >= 5:
        drivers.append(f"Fan-Out topology: {fan_out} unique beneficiaries")

    amount_p95 = float(df["amount"].quantile(0.95))
    high_value = int((involved["amount"] > amount_p95).sum())
    if high_value > 0 and len(drivers) < MAX_DRIVERS:
        drivers.append(f"{high_value} transfers above dataset 95th percentile (INR {amount_p95:,.0f})")

    if not drivers:
        drivers.append(f"No significant anomaly drivers detected for {account_id}")
    return drivers[:MAX_DRIVERS]


def analyze_account(account_id: str, df: pd.DataFrame | None = None) -> dict:
    """Return the strict account risk contract for downstream UI, graph and SAR modules."""
    if df is None:
        df = load_scored_data()
    outgoing = df[df["nameOrig"] == account_id]
    incoming = df[df["nameDest"] == account_id]
    if outgoing.empty and incoming.empty:
        raise ValueError(f"Account not found in scored dataset: {account_id}")

    total_inflow = float(incoming["amount"].sum())
    total_outflow = float(outgoing["amount"].sum())
    pass_through_ratio = total_outflow / total_inflow if total_inflow > 0 else 0.0

    # Originated transactions reflect the account's own behaviour; receive-only
    # accounts (e.g. cash-out endpoints) inherit the risk of funds they receive.
    risk_source = outgoing if not outgoing.empty else incoming
    risk_score = float(risk_source["Risk_Score"].max())

    counterparties = sorted(
        set(incoming["nameOrig"].astype(str)) | set(outgoing["nameDest"].astype(str))
    )

    return {
        "account_id": str(account_id),
        "risk_score": round(risk_score, 2),
        "risk_tier": assign_risk_tier(risk_score),
        "total_inflow": round(total_inflow, 2),
        "total_outflow": round(total_outflow, 2),
        "pass_through_ratio": round(pass_through_ratio, 4),
        "top_drivers": _build_top_drivers(account_id, incoming, outgoing, pass_through_ratio, df),
        "counterparties": counterparties,
    }


def main() -> None:
    """Train, persist and summarise the IsolationForest scoring run."""
    df = train_and_score()
    labels = df["is_mule_label"] == 1
    flagged = df["Risk_Tier"] == "HIGH"
    true_pos = int((labels & flagged).sum())
    precision = true_pos / max(int(flagged.sum()), 1)
    recall = true_pos / max(int(labels.sum()), 1)

    print(f"Model saved to {MODEL_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Scored data saved to {SCORED_PATH.relative_to(PROJECT_ROOT)} ({len(df)} rows)")
    print(f"Risk tiers: {df['Risk_Tier'].value_counts().to_dict()}")
    print(f"HIGH-tier precision vs labels: {precision:.4f} | recall: {recall:.4f}")
    accounts = set(df["nameOrig"].astype(str)) | set(df["nameDest"].astype(str))
    demo_account = (
        "mule_c1_hub01@ybl"
        if "mule_c1_hub01@ybl" in accounts
        else (str(df.loc[df["Risk_Score"].idxmax(), "nameOrig"]) if not df.empty else None)
    )
    if demo_account:
        sample = analyze_account(demo_account, df=df)
        print(f"Sample analyze_account: { {k: v for k, v in sample.items() if k != 'counterparties'} }")


if __name__ == "__main__":
    main()
