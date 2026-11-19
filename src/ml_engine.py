"""IsolationForest anomaly scoring engine and account-level risk analysis API."""

from collections import OrderedDict
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
FEATURES_PATH = PROJECT_ROOT / "data" / "bank_mule_features.csv"
SCORED_PATH = PROJECT_ROOT / "data" / "scored_bank_data.csv"
MODEL_PATH = PROJECT_ROOT / "models" / "iso_forest.joblib"

FEATURE_COLUMNS = ["amount", "Pass_Through_Ratio", "Near_Limit_Velocity"]
MODEL_PARAMS = {"n_estimators": 100, "contamination": 0.05, "random_state": 42}
HIGH_THRESHOLD = 80.0
MEDIUM_THRESHOLD = 50.0
NORMAL_CEILING = 79.99
MAX_DRIVERS = 5
INDEX_CACHE_MAXSIZE = 4


@dataclass(frozen=True)
class _CacheRecord:
    """Immutable cache entry tying a scored DataFrame to its input and artifact digests."""

    features_sha256: str
    scored_sha256: str
    stat_key: tuple[int, int, int, int, int, int] | None
    df: pd.DataFrame


@dataclass(frozen=True)
class _AccountIndex:
    """Pre-indexed row mappings and aggregates for O(1) account lookup."""

    orig_rows: dict[str, np.ndarray]
    dest_rows: dict[str, np.ndarray]
    amount_p95: float
    timestamps: pd.Series
    cutoff_24h: pd.Timestamp | None


_SCORED_CACHE: _CacheRecord | None = None
_INDEX_CACHE: OrderedDict[object, _AccountIndex] = OrderedDict()


def _artifact_stat_key(
    features_path: Path, scored_path: Path, model_path: Path
) -> tuple[int, int, int, int, int, int] | None:
    """Return (mtime_ns, size) across the artifact tuple, or None if any file is missing."""
    try:
        fs = features_path.stat()
        ss = scored_path.stat()
        ms = model_path.stat()
        return (fs.st_mtime_ns, fs.st_size, ss.st_mtime_ns, ss.st_size, ms.st_mtime_ns, ms.st_size)
    except OSError:
        return None


def get_scored_mtime() -> float:
    """Return latest modification timestamp across scored/feature artifacts for UI cache keys."""
    mtimes: list[float] = []
    for path in (SCORED_PATH, FEATURES_PATH):
        try:
            mtimes.append(path.stat().st_mtime)
        except OSError:
            continue
    return max(mtimes) if mtimes else 0.0


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
        gen_scored = gen_dir / "scored_bank_data.csv"

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
                    stat_key=_artifact_stat_key(features_path, scored_path, model_path),
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
    """Load the scored dataset as a fresh copy, using an in-memory mtime fast path when unchanged."""
    global _SCORED_CACHE
    if not FEATURES_PATH.exists():
        raise FileNotFoundError(f"Feature dataset not found: {FEATURES_PATH}")

    stat_key = _artifact_stat_key(FEATURES_PATH, SCORED_PATH, MODEL_PATH)
    cached = _SCORED_CACHE
    if cached is not None and stat_key is not None and cached.stat_key == stat_key:
        return cached.df.copy()

    resolved = _resolve_valid_generation()
    if resolved is None:
        return train_and_score().copy()

    features_sha256, scored_sha256, df = resolved
    _SCORED_CACHE = _CacheRecord(
        features_sha256=features_sha256,
        scored_sha256=scored_sha256,
        stat_key=_artifact_stat_key(FEATURES_PATH, SCORED_PATH, MODEL_PATH),
        df=df.copy(),
    )
    return df.copy()


def _df_cache_key(df: pd.DataFrame, cache_key: object | None = None) -> object:
    """Build a collision-resistant cache key for pre-indexed DataFrame lookups."""
    if cache_key is not None:
        return ("key", cache_key, len(df))
    if df.empty:
        return ("empty", tuple(df.columns))
    first_txn = str(df["txn_id"].iloc[0]) if "txn_id" in df.columns else ""
    last_txn = str(df["txn_id"].iloc[-1]) if "txn_id" in df.columns else ""
    amt_sum = float(df["amount"].sum()) if "amount" in df.columns else 0.0
    risk_sum = float(df["Risk_Score"].sum()) if "Risk_Score" in df.columns else 0.0
    return ("sig", len(df), tuple(df.columns), amt_sum, risk_sum, first_txn, last_txn)


def _get_account_index(df: pd.DataFrame, cache_key: object | None = None) -> _AccountIndex:
    """Return or build cached per-account row index and global aggregates for `df`."""
    key = _df_cache_key(df, cache_key=cache_key)
    cached = _INDEX_CACHE.get(key)
    if cached is not None:
        _INDEX_CACHE.move_to_end(key)
        return cached

    orig_rows = {
        str(k): np.asarray(v, dtype=np.intp)
        for k, v in df.groupby(df["nameOrig"].astype(str), sort=False).indices.items()
    }
    dest_rows = {
        str(k): np.asarray(v, dtype=np.intp)
        for k, v in df.groupby(df["nameDest"].astype(str), sort=False).indices.items()
    }
    amount_p95 = float(df["amount"].quantile(0.95)) if not df.empty else 0.0
    if "timestamp" in df.columns and not df.empty:
        timestamps = pd.to_datetime(df["timestamp"], errors="coerce")
        cutoff_24h = timestamps.max() - pd.Timedelta(hours=24) if timestamps.notna().any() else None
    else:
        timestamps = pd.Series(dtype="datetime64[ns]")
        cutoff_24h = None

    index = _AccountIndex(
        orig_rows=orig_rows,
        dest_rows=dest_rows,
        amount_p95=amount_p95,
        timestamps=timestamps,
        cutoff_24h=cutoff_24h,
    )
    _INDEX_CACHE[key] = index
    while len(_INDEX_CACHE) > INDEX_CACHE_MAXSIZE:
        _INDEX_CACHE.popitem(last=False)
    return index


def _slice_account_rows(df: pd.DataFrame, account_id: str, idx: _AccountIndex) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray, np.ndarray]:
    """Slice incoming and outgoing rows in O(1) using pre-indexed positions."""
    key = str(account_id)
    out_pos = idx.orig_rows.get(key)
    in_pos = idx.dest_rows.get(key)
    out_arr = out_pos if out_pos is not None else np.empty(0, dtype=np.intp)
    in_arr = in_pos if in_pos is not None else np.empty(0, dtype=np.intp)
    outgoing = df.iloc[out_arr] if len(out_arr) else df.iloc[0:0]
    incoming = df.iloc[in_arr] if len(in_arr) else df.iloc[0:0]
    return incoming, outgoing, in_arr, out_arr


def _build_top_drivers(
    account_id: str,
    incoming: pd.DataFrame,
    outgoing: pd.DataFrame,
    pass_through_ratio: float,
    df: pd.DataFrame,
    amount_p95: float | None = None,
    in_ts: pd.Series | None = None,
    out_ts: pd.Series | None = None,
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
        drivers.append(
            f"{near_limit} structured transfer(s) near regulatory thresholds "
            "(INR 45,000-50,000 PAN / INR 1,80,000-2,00,000 RTGS bands)"
        )

    if not incoming.empty and not outgoing.empty:
        first_in = (in_ts if in_ts is not None else pd.to_datetime(incoming["timestamp"])).min()
        first_out = (out_ts if out_ts is not None else pd.to_datetime(outgoing["timestamp"])).min()
        lag_min = (first_out - first_in).total_seconds() / 60.0
        if 0.0 <= lag_min <= 60.0:
            drivers.append(f"Rapid turnaround: first debit {lag_min:.0f} min after first credit")

    fan_in = incoming["nameOrig"].nunique()
    if fan_in >= 5:
        drivers.append(f"Fan-In topology: {fan_in} unique remitters")

    fan_out = outgoing["nameDest"].nunique()
    if fan_out >= 5:
        drivers.append(f"Fan-Out topology: {fan_out} unique beneficiaries")

    p95 = float(df["amount"].quantile(0.95)) if amount_p95 is None else amount_p95
    high_value = int((involved["amount"] > p95).sum())
    if high_value > 0 and len(drivers) < MAX_DRIVERS:
        drivers.append(f"{high_value} transfers above dataset 95th percentile (INR {p95:,.0f})")

    if not drivers:
        drivers.append(f"No significant anomaly drivers detected for {account_id}")
    return drivers[:MAX_DRIVERS]


def get_account_24h_totals(
    account_id: str, df: pd.DataFrame, cache_key: object | None = None
) -> tuple[float, float]:
    """Compute trailing 24-hour inflow and outflow using pre-indexed positions."""
    idx = _get_account_index(df, cache_key=cache_key)
    incoming, outgoing, in_arr, out_arr = _slice_account_rows(df, account_id, idx)
    if idx.cutoff_24h is not None:
        if len(in_arr):
            incoming = incoming.loc[idx.timestamps.iloc[in_arr] >= idx.cutoff_24h]
        if len(out_arr):
            outgoing = outgoing.loc[idx.timestamps.iloc[out_arr] >= idx.cutoff_24h]
    inflow_24h = float(incoming["amount"].sum()) if not incoming.empty else 0.0
    outflow_24h = float(outgoing["amount"].sum()) if not outgoing.empty else 0.0
    return round(inflow_24h, 2), round(outflow_24h, 2)


def get_account_ledger(
    account_id: str, df: pd.DataFrame, cache_key: object | None = None
) -> pd.DataFrame:
    """Return sorted transaction ledger rows involving `account_id` via O(1) index lookup."""
    idx = _get_account_index(df, cache_key=cache_key)
    incoming, outgoing, _, _ = _slice_account_rows(df, account_id, idx)
    combined = pd.concat([incoming, outgoing])
    if "txn_id" in combined.columns:
        combined = combined.drop_duplicates(subset=["txn_id"])
    else:
        combined = combined.drop_duplicates()
    cols = ["txn_id", "timestamp", "nameOrig", "nameDest", "amount", "Pass_Through_Ratio", "Risk_Score"]
    if combined.empty:
        return combined[cols].copy()
    return combined[cols].sort_values("timestamp").reset_index(drop=True)


def analyze_account(
    account_id: str, df: pd.DataFrame | None = None, cache_key: object | None = None
) -> dict:
    """Return the strict account risk contract for downstream UI, graph and SAR modules."""
    if df is None:
        df = load_scored_data()
    idx = _get_account_index(df, cache_key=cache_key)
    incoming, outgoing, in_arr, out_arr = _slice_account_rows(df, account_id, idx)
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
    in_ts = idx.timestamps.iloc[in_arr] if len(in_arr) and not idx.timestamps.empty else None
    out_ts = idx.timestamps.iloc[out_arr] if len(out_arr) and not idx.timestamps.empty else None

    return {
        "account_id": str(account_id),
        "risk_score": round(risk_score, 2),
        "risk_tier": assign_risk_tier(risk_score),
        "total_inflow": round(total_inflow, 2),
        "total_outflow": round(total_outflow, 2),
        "pass_through_ratio": round(pass_through_ratio, 4),
        "top_drivers": _build_top_drivers(
            account_id,
            incoming,
            outgoing,
            pass_through_ratio,
            df,
            amount_p95=idx.amount_p95,
            in_ts=in_ts,
            out_ts=out_ts,
        ),
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
    print(
        f"Benchmark HIGH alignment vs is_mule_label (label-calibrated INR/PTR dataset): "
        f"precision={precision:.4f} | recall={recall:.4f}"
    )
    orig_max = df.groupby(df["nameOrig"].astype(str))["Risk_Score"].max()
    dest_max = df.groupby(df["nameDest"].astype(str))["Risk_Score"].max()
    acct_scores = pd.concat([orig_max, dest_max.drop(labels=orig_max.index, errors="ignore")]).sort_values(
        ascending=False
    )
    tier_samples: dict[str, str] = {}
    for tier_name, lo, hi in (("HIGH", HIGH_THRESHOLD, 100.01), ("MEDIUM", MEDIUM_THRESHOLD, HIGH_THRESHOLD), ("LOW", 0.0, MEDIUM_THRESHOLD)):
        candidates = acct_scores[(acct_scores >= lo) & (acct_scores < hi)]
        if not candidates.empty:
            tier_samples[tier_name] = str(candidates.index[0])

    print(f"Sample accounts by tier: {tier_samples}")
    if "HIGH" in tier_samples:
        sample = analyze_account(tier_samples["HIGH"], df=df)
        print(f"Sample analyze_account (HIGH): { {k: v for k, v in sample.items() if k != 'counterparties'} }")


if __name__ == "__main__":
    main()
