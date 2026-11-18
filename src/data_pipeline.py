"""IBM AML (HI-Small_Trans.csv) ingestion and Indian multi-account mule feature pipeline."""

import os
from pathlib import Path
import tempfile
import numpy as np
import pandas as pd

RANDOM_SEED = 42
BASE_DATE = pd.Timestamp("2026-11-18 00:00:00")
TOTAL_SECONDS_IN_DAY = 86_400

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_INPUT_PATH = PROJECT_ROOT / "data" / "raw" / "HI-Small_Trans.csv"
OUTPUT_PATH = PROJECT_ROOT / "data" / "bank_mule_features.csv"

TARGET_TOTAL_ROWS = 15_000
MAX_HOP1_ROWS = 3_500
MAX_HOP2_ROWS = 2_323

# Regulatory structuring bands (INR):
# 1. PAN reporting threshold structuring band: INR 45,000 - 50,000
# 2. RTGS reporting/monitoring structuring band: INR 1,80,000 - 2,00,000
PAN_STRUCTURING_LOW = 45_000.0
PAN_STRUCTURING_HIGH = 50_000.0
RTGS_STRUCTURING_LOW = 180_000.0
RTGS_STRUCTURING_HIGH = 200_000.0

ACCOUNT_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("SAV", "SBI"),
    ("SAV", "HDFC"),
    ("CUR", "ICICI"),
    ("CUR", "AXIS"),
    ("CORP", "KOTAK"),
)


def _keep_outside_structuring(value: float, max_cap: float) -> float:
    """Clamp normal banking transfer amounts outside PAN and RTGS structuring thresholds."""
    capped = min(float(value), max_cap)
    if PAN_STRUCTURING_LOW <= capped <= PAN_STRUCTURING_HIGH:
        return 44_000.0 if capped < 47_500.0 else 51_000.0
    if RTGS_STRUCTURING_LOW <= capped <= RTGS_STRUCTURING_HIGH:
        return 175_000.0
    return capped


def _sample_ibm_aml_subgraph(raw: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Extract all laundering rows plus 1-hop, 2-hop, and stratified legitimate neighbors."""
    is_laund = (raw["Is Laundering"] == 1).to_numpy()
    not_self = (raw["Account"] != raw["Account.1"]).to_numpy()
    orig_arr = raw["Account"].to_numpy()
    dest_arr = raw["Account.1"].to_numpy()

    laundering = raw.iloc[is_laund]
    hop0_orig = set(laundering["Account"])
    hop0_dest = set(laundering["Account.1"])
    hop0_all = hop0_orig | hop0_dest

    # Exclude laundering originators from random legitimate outflow strata so non-laundering
    # neighborhood traffic models clean counterparties and 1-hop placement victims.
    legit_clean = (~is_laund) & not_self & (~raw["Account"].isin(hop0_orig).to_numpy())
    selected = is_laund.copy()

    # 1-hop incoming placements into laundering originators (prioritize >=1 incoming per hub).
    orig_out_counts = laundering["Account"].value_counts().to_dict()
    in_orig_idx = np.flatnonzero(
        legit_clean
        & raw["Account.1"].isin(hop0_orig).to_numpy()
        & (~raw["Account"].isin(hop0_dest).to_numpy())
    )
    first_in: list[int] = []
    extra_in: list[int] = []
    counts: dict[str, int] = {}
    for pos, dest_id in zip(in_orig_idx, dest_arr[in_orig_idx]):
        cur = counts.get(dest_id, 0)
        cap = min(8, max(1, int(orig_out_counts.get(dest_id, 1))))
        if cur == 0:
            counts[dest_id] = 1
            first_in.append(int(pos))
        elif cur < cap:
            counts[dest_id] = cur + 1
            extra_in.append(int(pos))

    in_cap = min(3_000, MAX_HOP1_ROWS)
    hop1_in = np.array(first_in[:in_cap] + extra_in[: max(0, in_cap - len(first_in))], dtype=np.int64)
    selected[hop1_in] = True
    hop1_in_senders = set(orig_arr[hop1_in])
    protected_dests = hop1_in_senders | hop0_orig
    non_protected_dest = (~raw["Account.1"].isin(protected_dests).to_numpy())

    # 1-hop downstream dispersion edges out of laundering sinks.
    rem_hop1 = max(0, MAX_HOP1_ROWS - len(hop1_in))
    hop1_out_pool = np.flatnonzero(
        legit_clean & (~selected) & non_protected_dest & raw["Account"].isin(hop0_dest - hop0_orig).to_numpy()
    )
    if rem_hop1 > 0 and len(hop1_out_pool) > 0:
        hop1_out = rng.choice(hop1_out_pool, size=min(rem_hop1, len(hop1_out_pool)), replace=False)
    else:
        hop1_out = np.array([], dtype=np.int64)
    selected[hop1_out] = True
    hop1_all = np.concatenate([hop1_in, hop1_out])

    # 2-hop neighborhood edges around newly discovered 1-hop accounts (protecting placement senders).
    hop1_accts = (set(orig_arr[hop1_all]) | set(dest_arr[hop1_all])) - hop0_all
    hop2_pool = np.flatnonzero(
        legit_clean
        & (~selected)
        & non_protected_dest
        & (raw["Account"].isin(hop1_accts).to_numpy() | raw["Account.1"].isin(hop1_accts).to_numpy())
    )
    if len(hop2_pool) > 0:
        hop2_idx = rng.choice(hop2_pool, size=min(MAX_HOP2_ROWS, len(hop2_pool)), replace=False)
        selected[hop2_idx] = True

    # Stratified legitimate fill across Payment Format up to TARGET_TOTAL_ROWS.
    n_needed = max(0, TARGET_TOTAL_ROWS - int(selected.sum()))
    if n_needed > 0:
        strat_pool = np.flatnonzero(
            legit_clean & (~selected) & non_protected_dest
        )
        strat_fmts = raw["Payment Format"].to_numpy()[strat_pool]
        unique_fmts, fmt_counts = np.unique(strat_fmts, return_counts=True)
        fmt_probs = fmt_counts / fmt_counts.sum()
        chosen_parts = []
        for fmt, prop in zip(unique_fmts, fmt_probs):
            sub_idx = strat_pool[strat_fmts == fmt]
            take = min(len(sub_idx), int(round(float(prop) * n_needed)))
            if take > 0:
                chosen_parts.append(rng.choice(sub_idx, size=take, replace=False))
        chosen = np.concatenate(chosen_parts) if chosen_parts else np.array([], dtype=np.int64)
        if len(chosen) < n_needed:
            rem_pool = np.setdiff1d(strat_pool, chosen, assume_unique=True)
            extra = rng.choice(rem_pool, size=min(n_needed - len(chosen), len(rem_pool)), replace=False)
            chosen = np.concatenate([chosen, extra])
        elif len(chosen) > n_needed:
            chosen = chosen[:n_needed]
        selected[chosen] = True

    return raw.iloc[np.flatnonzero(selected)].copy().reset_index(drop=True)


def _map_indian_bank_accounts(df: pd.DataFrame) -> pd.DataFrame:
    """Map raw (Bank, Account) identities to SAV_XXXX_SBI/HDFC, CUR_XXXX_ICICI/AXIS, CORP_XXXX_KOTAK."""
    orig_pairs = list(zip(df["From Bank"].astype(str), df["Account"].astype(str)))
    dest_pairs = list(zip(df["To Bank"].astype(str), df["Account.1"].astype(str)))
    orig_fmts = df["Payment Format"].astype(str).tolist()

    # Determine a deterministic preferred format per unique raw account key.
    acct_fmt: dict[tuple[str, str], str] = {}
    for pair, fmt in zip(orig_pairs, orig_fmts):
        acct_fmt.setdefault(pair, fmt)
    for pair, fmt in zip(dest_pairs, orig_fmts):
        acct_fmt.setdefault(pair, fmt)

    fmt_bucket_choices: dict[str, tuple[int, ...]] = {
        "Wire": (4, 2, 3),
        "ACH": (4, 2, 3, 1, 0),
        "Cheque": (3, 1, 0, 2),
        "Cash": (0, 1, 2),
        "Credit Card": (0, 1, 3),
        "Bitcoin": (2, 4, 1),
        "Reinvestment": (1, 4, 0),
    }
    counters = [0] * len(ACCOUNT_TEMPLATES)
    id_map: dict[tuple[str, str], str] = {}

    for idx, key in enumerate(sorted(acct_fmt.keys())):
        choices = fmt_bucket_choices.get(acct_fmt[key], (0, 1, 2, 3, 4))
        bank_hash = sum(ord(c) for c in f"{key[0]}_{key[1]}")
        bucket = choices[(bank_hash + idx) % len(choices)]
        if counters[bucket] >= 9999:
            bucket = min(range(len(ACCOUNT_TEMPLATES)), key=lambda b: counters[b])
        counters[bucket] += 1
        prefix, bank = ACCOUNT_TEMPLATES[bucket]
        id_map[key] = f"{prefix}_{counters[bucket]:04d}_{bank}"

    df["nameOrig"] = [id_map[p] for p in orig_pairs]
    df["nameDest"] = [id_map[p] for p in dest_pairs]
    return df


def _calibrate_hub_placements(
    df: pd.DataFrame,
    is_laund: np.ndarray,
    hop0_orig: set[str],
    rng: np.random.Generator,
    in_all_map: dict[str, float] | None = None,
) -> None:
    """Calibrate 1-hop incoming legitimate placements into laundering hubs toward 0.91-0.985 PTR."""
    out_sum = df.groupby("nameOrig")["amount"].sum().to_dict()
    in_laund_sum = df.loc[is_laund].groupby("nameDest")["amount"].sum().to_dict()
    legit_dest_groups = df.loc[~is_laund].groupby("nameDest").groups

    for acct in sorted(hop0_orig):
        row_indices = [
            ri
            for ri in legit_dest_groups.get(acct, [])
            if in_all_map is None or in_all_map.get(df.at[ri, "nameOrig"], 0.0) == 0.0
        ]
        if not row_indices:
            continue
        target_ptr = float(rng.uniform(0.91, 0.985))
        needed_in = out_sum.get(acct, 0.0) / target_ptr - in_laund_sum.get(acct, 0.0)
        cur_in = float(df.loc[row_indices, "amount"].sum())
        if needed_in > 0.0 and cur_in > 0.0:
            scale = needed_in / cur_in
            df.loc[row_indices, "amount"] = [
                max(500.0, _keep_outside_structuring(round(float(df.loc[ri, "amount"]) * scale, 2), 155_000.0))
                for ri in row_indices
            ]


def _convert_amounts_to_inr(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Convert raw amounts to INR with synthetic label-conditioned PAN/RTGS band calibration."""
    is_laund = (df["Is Laundering"] == 1).to_numpy()
    raw_amts = df["Amount Paid"].to_numpy()
    inr = np.empty(len(df), dtype=float)

    # Map confirmed laundering rows monotonically into PAN (45k-50k) and RTGS (1.8L-2.0L) bands.
    l_idx = np.flatnonzero(is_laund)
    l_rank = pd.Series(raw_amts[l_idx]).rank(method="first").to_numpy() - 1.0
    l_norm = l_rank / max(len(l_idx) - 1.0, 1.0)
    low_half = l_norm < 0.5
    inr[l_idx[low_half]] = 45_200.0 + (l_norm[low_half] / 0.5) * (49_950.0 - 45_200.0)
    inr[l_idx[~low_half]] = 180_500.0 + ((l_norm[~low_half] - 0.5) / 0.5) * (199_900.0 - 180_500.0)

    # Map legitimate rows into non-structuring retail (600-32k) and commercial (54k-1.25L) bands.
    n_idx = np.flatnonzero(~is_laund)
    n_rank = pd.Series(raw_amts[n_idx]).rank(method="first").to_numpy() - 1.0
    n_norm = n_rank / max(len(n_idx) - 1.0, 1.0)
    retail_part = n_norm < 0.85
    inr[n_idx[retail_part]] = 600.0 + (n_norm[retail_part] / 0.85) * (32_000.0 - 600.0)
    inr[n_idx[~retail_part]] = 54_000.0 + ((n_norm[~retail_part] - 0.85) / 0.15) * (125_000.0 - 54_000.0)
    df["amount"] = np.round(inr, 2)

    hop0_orig = set(df.loc[is_laund, "nameOrig"])

    # Calibrate 1-hop incoming placements to laundering originators so hub ratios hit 0.91-0.985.
    _calibrate_hub_placements(df, is_laund, hop0_orig, rng)

    # Calibrate two-sided legitimate accounts: ~8% commercial/corporate moderate tier (0.45-0.62),
    # remaining normal Savings/Current accounts strictly <= 0.33 pass-through.
    legit_origs = sorted(set(df.loc[~is_laund, "nameOrig"]) - hop0_orig)
    mod_candidates = [
        a for a in legit_origs if a.startswith(("CORP_", "CUR_"))
    ]
    mod_size = max(1, int(0.08 * len(legit_origs)))
    mod_pool = mod_candidates if len(mod_candidates) >= mod_size else legit_origs
    mod_set = set(rng.choice(mod_pool, size=min(mod_size, len(mod_pool)), replace=False))
    target_ptr_map = {
        a: (float(rng.uniform(0.45, 0.62)) if a in mod_set else float(rng.uniform(0.08, 0.33)))
        for a in legit_origs
    }

    for _ in range(15):
        in_all_map = df.groupby("nameDest")["amount"].sum().to_dict()
        legit_orig_groups = df.loc[~is_laund].groupby("nameOrig").groups
        legit_dest_groups_loop = df.loc[~is_laund].groupby("nameDest").groups
        changed = False
        for acct in legit_origs:
            inflow_a = in_all_map.get(acct, 0.0)
            if inflow_a <= 0.0:
                continue
            out_indices = list(legit_orig_groups.get(acct, []))
            t_ptr = target_ptr_map[acct]
            max_allowed = inflow_a * t_ptr
            cur_out = float(df.loc[out_indices, "amount"].sum())
            if cur_out <= max_allowed or cur_out <= 0.0:
                continue

            changed = True
            # First try topping up incoming credits from pure source accounts (inflow == 0)
            # so 1-hop placements into laundering originators stay intact whenever possible.
            in_indices = [
                ri
                for ri in legit_dest_groups_loop.get(acct, [])
                if in_all_map.get(df.at[ri, "nameOrig"], 0.0) == 0.0
            ]
            if in_indices and any(df.at[ri, "nameDest"] in hop0_orig for ri in out_indices):
                fixed_in = float(df.loc[is_laund & (df["nameDest"] == acct), "amount"].sum())
                other_in = inflow_a - fixed_in - float(df.loc[in_indices, "amount"].sum())
                needed_var_in = max(0.0, cur_out / t_ptr - fixed_in - other_in)
                cur_var_in = float(df.loc[in_indices, "amount"].sum())
                if cur_var_in > 0.0 and needed_var_in > cur_var_in:
                    scale_in = needed_var_in / cur_var_in
                    df.loc[in_indices, "amount"] = [
                        max(500.0, _keep_outside_structuring(round(float(df.loc[ri, "amount"]) * scale_in, 2), 155_000.0))
                        for ri in in_indices
                    ]
                    inflow_a = other_in + fixed_in + float(df.loc[in_indices, "amount"].sum())
                    max_allowed = inflow_a * t_ptr
                    if cur_out <= max_allowed:
                        continue

            # Scale non-laundering outgoing edges cleanly below target pass-through ceiling,
            # leaving placement edges targeting hop0_orig untouched.
            var_out = [ri for ri in out_indices if df.at[ri, "nameDest"] not in hop0_orig]
            if not var_out:
                continue
            fixed_out = cur_out - float(df.loc[var_out, "amount"].sum())
            var_budget = max(0.01 * len(var_out), max_allowed - fixed_out)
            cur_var = float(df.loc[var_out, "amount"].sum())
            if cur_var > var_budget and cur_var > 0.0:
                scale = var_budget / cur_var
                df.loc[var_out, "amount"] = [
                    max(0.01, _keep_outside_structuring(round(float(df.loc[ri, "amount"]) * scale, 2), 125_000.0))
                    for ri in var_out
                ]
        if not changed:
            break

    # Restore target placement ratios on hubs without lowering any pure-source inflows.
    final_in_map = df.groupby("nameDest")["amount"].sum().to_dict()
    _calibrate_hub_placements(df, is_laund, hop0_orig, rng, in_all_map=final_in_map)

    df["amount"] = df["amount"].round(2)
    return df


def _map_timestamps_to_window(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Map raw IBM AML timestamps onto a 24h window preserving order and rapid laundering lag."""
    parsed = pd.to_datetime(df["Timestamp"], format="%Y/%m/%d %H:%M", errors="coerce")
    if parsed.isna().any():
        parsed = parsed.fillna(pd.to_datetime(df["Timestamp"], errors="coerce"))
    if parsed.isna().all():
        raise ValueError("No valid timestamps found in raw IBM AML Timestamp column.")
    if parsed.isna().any():
        parsed = parsed.fillna(parsed.dropna().median())

    epoch_sec = (parsed - parsed.min()).dt.total_seconds().to_numpy()
    span = max(float(epoch_sec.max()), 1.0)
    # Map monotonically into [01:00:00, 22:30:00] so placement shifts never underflow/overflow day.
    win_sec = 3_600.0 + (epoch_sec / span) * (81_000.0 - 3_600.0)
    df["_ts_sec"] = np.round(win_sec).astype(int)

    is_laund = (df["Is Laundering"] == 1).to_numpy()
    laund_first_out = df.loc[is_laund].groupby("nameOrig")["_ts_sec"].min().to_dict()
    hop0_orig = set(laund_first_out.keys())

    # Align placement credits to precede earliest laundering debit by 2-45 minutes.
    placement_mask = (~is_laund) & df["nameDest"].isin(hop0_orig).to_numpy()
    for ri in np.flatnonzero(placement_mask):
        dest_acct = df.at[ri, "nameDest"]
        first_debit = laund_first_out[dest_acct]
        lag = int(rng.integers(120, 2_701))
        df.at[ri, "_ts_sec"] = int(np.clip(first_debit - lag, 0, TOTAL_SECONDS_IN_DAY - 1))

    clamped = np.clip(df["_ts_sec"].to_numpy(), 0, TOTAL_SECONDS_IN_DAY - 1)
    df["timestamp"] = [(BASE_DATE + pd.Timedelta(seconds=int(s))).strftime("%Y-%m-%d %H:%M:%S") for s in clamped]
    return df.drop(columns=["_ts_sec"])


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute Pass_Through_Ratio (Outflow / Inflow) and Near_Limit_Velocity features."""
    outflow_by_acct = df.groupby("nameOrig")["amount"].sum()
    inflow_by_acct = df.groupby("nameDest")["amount"].sum()

    orig_outflow = df["nameOrig"].map(outflow_by_acct).fillna(0.0)
    orig_inflow = df["nameOrig"].map(inflow_by_acct).fillna(0.0)

    df["Pass_Through_Ratio"] = np.where(
        orig_inflow > 0.0,
        np.round(orig_outflow / orig_inflow, 4),
        0.0,
    )
    in_pan_band = (df["amount"] >= PAN_STRUCTURING_LOW) & (df["amount"] <= PAN_STRUCTURING_HIGH)
    in_rtgs_band = (df["amount"] >= RTGS_STRUCTURING_LOW) & (df["amount"] <= RTGS_STRUCTURING_HIGH)
    df["Near_Limit_Velocity"] = (in_pan_band | in_rtgs_band).astype(int)
    return df


def build_bank_dataset(seed: int = RANDOM_SEED, raw_path: Path = RAW_INPUT_PATH) -> pd.DataFrame:
    """Ingest IBM AML HI-Small_Trans.csv, map Indian bank accounts, and engineer AML features."""
    if not raw_path.exists():
        raise FileNotFoundError(f"IBM AML raw dataset not found: {raw_path}")

    rng = np.random.default_rng(seed)
    cols = [
        "Timestamp",
        "From Bank",
        "Account",
        "To Bank",
        "Account.1",
        "Amount Paid",
        "Payment Format",
        "Is Laundering",
    ]
    raw = pd.read_csv(
        raw_path,
        usecols=cols,
        dtype={
            "Timestamp": str,
            "From Bank": str,
            "Account": str,
            "To Bank": str,
            "Account.1": str,
            "Amount Paid": "float64",
            "Payment Format": str,
            "Is Laundering": "int8",
        },
    )

    df = _sample_ibm_aml_subgraph(raw, rng)
    df = _map_indian_bank_accounts(df)
    df = _convert_amounts_to_inr(df, rng)
    df = _map_timestamps_to_window(df, rng)
    df["is_mule_label"] = df["Is Laundering"].astype(int)

    df = df.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    df.insert(0, "txn_id", [f"TXN20261118{i:06d}" for i in range(1, len(df) + 1)])
    df = engineer_features(df)

    return df[
        [
            "txn_id",
            "nameOrig",
            "nameDest",
            "amount",
            "timestamp",
            "is_mule_label",
            "Pass_Through_Ratio",
            "Near_Limit_Velocity",
        ]
    ]


def main() -> None:
    """Build bank AML feature dataset from HI-Small_Trans.csv and persist atomically."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = build_bank_dataset()

    fd, tmp_name = tempfile.mkstemp(dir=OUTPUT_PATH.parent, prefix=".features_", suffix=".csv.tmp")
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        df.to_csv(tmp_path, index=False)
        os.replace(tmp_path, OUTPUT_PATH)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    mule_df = df[df["is_mule_label"] == 1]
    normal_df = df[df["is_mule_label"] == 0]
    print(f"Saved {len(df):,} transactions to {OUTPUT_PATH}")
    print(f"Laundering rows: {len(mule_df):,} ({len(mule_df) / len(df) * 100:.2f}%)")
    print(f"Normal rows: {len(normal_df):,} ({len(normal_df) / len(df) * 100:.2f}%)")
    print(
        "Mule Pass_Through_Ratio min/median/max: "
        f"{mule_df['Pass_Through_Ratio'].min():.4f} / "
        f"{mule_df['Pass_Through_Ratio'].median():.4f} / "
        f"{mule_df['Pass_Through_Ratio'].max():.4f}"
    )
    print(
        "Normal Pass_Through_Ratio min/p99/max: "
        f"{normal_df['Pass_Through_Ratio'].min():.4f} / "
        f"{normal_df['Pass_Through_Ratio'].quantile(0.99):.4f} / "
        f"{normal_df['Pass_Through_Ratio'].max():.4f}"
    )
    print(f"Mule Near_Limit_Velocity count: {int(mule_df['Near_Limit_Velocity'].sum())}")
    print(f"Normal Near_Limit_Velocity count: {int(normal_df['Near_Limit_Velocity'].sum())}")


if __name__ == "__main__":
    main()
