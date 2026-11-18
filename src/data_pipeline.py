"""Synthetic Indian UPI transaction generator and mule feature engineering pipeline."""

import os
from pathlib import Path
import tempfile
import numpy as np
import pandas as pd

RANDOM_SEED = 42
BASE_DATE = pd.Timestamp("2026-11-18 00:00:00")
TOTAL_SECONDS_IN_DAY = 86400
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "data" / "upi_mule_features.csv"

NUM_CLUSTERS = 5
COLLECTORS_PER_CLUSTER = 10
PLACEMENT_TXNS_PER_COLLECTOR = 8
FANIN_TXNS_PER_COLLECTOR = 5
HUBS_PER_CLUSTER = 2
PASSTHROUGH_TXNS_PER_HUB = 25

NUM_TOPUP_TXNS = 1500
NUM_RETAIL_TXNS = 7600
MAX_NORMAL_PASS_THROUGH = 0.34
NEAR_LIMIT_LOW = 90000.0
NEAR_LIMIT_HIGH = 100000.0


def _split_amount_exactly(total_amount: float, count: int, rng: np.random.Generator) -> list[float]:
    """Split a positive total into `count` varied chunks summing to `total_amount`."""
    weights = rng.uniform(0.85, 1.15, size=count)
    weights /= weights.sum()
    parts = [round(float(total_amount * w), 2) for w in weights[:-1]]
    parts.append(round(float(total_amount - sum(parts)), 2))
    return parts


def _format_timestamp(offset_seconds: int) -> str:
    """Clamp seconds to the 24-hour simulation window and format as timestamp string."""
    clamped = int(np.clip(offset_seconds, 0, TOTAL_SECONDS_IN_DAY - 1))
    return (BASE_DATE + pd.Timedelta(seconds=clamped)).strftime("%Y-%m-%d %H:%M:%S")


def generate_mule_clusters(rng: np.random.Generator) -> list[dict]:
    """Generate 5 mule rings with victim placements, Fan-In, and Pass-Through layering."""
    rows: list[dict] = []
    cluster_centers_sec = [10800, 25200, 41400, 57600, 73800]

    for cluster_idx, center_sec in enumerate(cluster_centers_sec, start=1):
        hubs = [f"mule_c{cluster_idx}_hub01@ybl", f"mule_c{cluster_idx}_hub02@ybl"]
        cashouts = [f"cashout_c{cluster_idx}_01@oksbi", f"cashout_c{cluster_idx}_02@oksbi"]
        hub_inflow_records: dict[str, list[tuple[float, int]]] = {h: [] for h in hubs}

        for col_idx in range(1, COLLECTORS_PER_CLUSTER + 1):
            collector = f"mule_c{cluster_idx}_col{col_idx:02d}@okaxis"
            target_hub = hubs[0] if col_idx <= 5 else hubs[1]

            fanin_amounts = [
                round(float(amt), 2)
                for amt in rng.uniform(95500.0, 99900.0, size=FANIN_TXNS_PER_COLLECTOR)
            ]
            col_outflow = sum(fanin_amounts)
            target_col_ratio = float(rng.uniform(0.955, 0.990))
            col_inflow = round(col_outflow / target_col_ratio, 2)
            placement_amounts = _split_amount_exactly(
                col_inflow, PLACEMENT_TXNS_PER_COLLECTOR, rng
            )

            # Placement inflows occur 5-20 minutes before the collector's Fan-In burst.
            for amt in placement_amounts:
                victim_id = int(rng.integers(1000, 9000))
                ts_sec = center_sec - int(rng.integers(300, 1201))
                rows.append(
                    {
                        "nameOrig": f"payer_{victim_id:04d}@okicici",
                        "nameDest": collector,
                        "amount": amt,
                        "timestamp": _format_timestamp(ts_sec),
                        "is_mule_label": 0,
                    }
                )

            # High-velocity Fan-In transfers from collectors into aggregator hubs.
            for amt in fanin_amounts:
                ts_sec = center_sec + int(rng.integers(0, 300))
                rows.append(
                    {
                        "nameOrig": collector,
                        "nameDest": target_hub,
                        "amount": amt,
                        "timestamp": _format_timestamp(ts_sec),
                        "is_mule_label": 1,
                    }
                )
                hub_inflow_records[target_hub].append((amt, ts_sec))

        # Rapid Pass-Through layering from hub mules to cash-out accounts (1-5 min lag).
        for hub_idx, hub in enumerate(hubs):
            target_hub_ratio = float(rng.uniform(0.955, 0.985))
            cashout_acct = cashouts[hub_idx]
            for inflow_amt, inflow_ts in hub_inflow_records[hub]:
                pass_amt = round(float(np.clip(inflow_amt * target_hub_ratio, 90500.0, 99500.0)), 2)
                pass_ts = inflow_ts + int(rng.integers(60, 301))
                rows.append(
                    {
                        "nameOrig": hub,
                        "nameDest": cashout_acct,
                        "amount": pass_amt,
                        "timestamp": _format_timestamp(pass_ts),
                        "is_mule_label": 1,
                    }
                )

    return rows


def generate_normal_traffic(rng: np.random.Generator) -> list[dict]:
    """Generate 9,100 legitimate UPI top-ups and retail transactions across 24 hours."""
    rows: list[dict] = []
    users = [f"user_{i:04d}@okaxis" for i in range(1, 1001)]
    user_credits: dict[str, list[tuple[int, float]]] = {u: [] for u in users}
    user_outflow: dict[str, float] = {u: 0.0 for u in users}

    # Guarantee every user receives at least one top-up, then distribute the remaining 500.
    topup_targets = list(users) + list(rng.choice(users, size=NUM_TOPUP_TXNS - len(users), replace=True))
    for dest_user in topup_targets:
        employer_id = int(rng.integers(1, 31))
        amt = round(float(rng.uniform(20000.0, 85000.0)), 2)
        ts_sec = int(rng.integers(0, TOTAL_SECONDS_IN_DAY // 2))
        rows.append(
            {
                "nameOrig": f"employer_{employer_id:02d}@sbi",
                "nameDest": dest_user,
                "amount": amt,
                "timestamp": _format_timestamp(ts_sec),
                "is_mule_label": 0,
            }
        )
        user_credits[dest_user].append((ts_sec, amt))

    # Generate 7,600 everyday retail/P2P merchant transactions keeping user outflow < 35%.
    for idx in range(NUM_RETAIL_TXNS):
        merchant_id = int(rng.integers(1, 501))
        dest_merchant = f"merchant_{merchant_id:04d}@paytm"
        ts_sec = int(rng.integers(0, TOTAL_SECONDS_IN_DAY))

        if idx < 3500:
            candidate_user = users[int(rng.integers(0, len(users)))]
            credited_by_ts = sum(a for t, a in user_credits[candidate_user] if t <= ts_sec)
            remaining_budget = MAX_NORMAL_PASS_THROUGH * credited_by_ts - user_outflow[candidate_user]
            if remaining_budget >= 500.0:
                amt = round(float(rng.uniform(50.0, min(15000.0, remaining_budget))), 2)
                user_outflow[candidate_user] += amt
                origin = candidate_user
            else:
                origin = f"payer_{int(rng.integers(1000, 9000)):04d}@okicici"
                amt = round(float(rng.uniform(50.0, 15000.0)), 2)
        else:
            origin = f"payer_{int(rng.integers(1000, 9000)):04d}@okicici"
            amt = round(float(rng.uniform(50.0, 15000.0)), 2)

        rows.append(
            {
                "nameOrig": origin,
                "nameDest": dest_merchant,
                "amount": amt,
                "timestamp": _format_timestamp(ts_sec),
                "is_mule_label": 0,
            }
        )

    return rows


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
    df["Near_Limit_Velocity"] = (
        (df["amount"] >= NEAR_LIMIT_LOW) & (df["amount"] <= NEAR_LIMIT_HIGH)
    ).astype(int)
    return df


def build_upi_dataset(seed: int = RANDOM_SEED) -> pd.DataFrame:
    """Assemble sorted 10,000-row UPI dataset with deterministic IDs and features."""
    rng = np.random.default_rng(seed)

    all_rows = generate_mule_clusters(rng) + generate_normal_traffic(rng)
    df = pd.DataFrame(all_rows)
    df = df.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    df.insert(0, "txn_id", [f"UPI20261118{i:06d}" for i in range(1, len(df) + 1)])
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
    """Generate the synthetic UPI dataset and save it atomically to CSV."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = build_upi_dataset()
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
    print(f"Saved {len(df)} transactions to {OUTPUT_PATH}")
    print(f"Mule rows: {len(mule_df)} ({len(mule_df) / len(df) * 100:.2f}%)")
    print(f"Normal rows: {len(normal_df)} ({len(normal_df) / len(df) * 100:.2f}%)")
    print(
        "Mule Pass_Through_Ratio min/max: "
        f"{mule_df['Pass_Through_Ratio'].min():.4f} / {mule_df['Pass_Through_Ratio'].max():.4f}"
    )
    print(
        "Normal Pass_Through_Ratio min/max: "
        f"{normal_df['Pass_Through_Ratio'].min():.4f} / {normal_df['Pass_Through_Ratio'].max():.4f}"
    )
    print(f"Mule Near_Limit_Velocity count: {int(mule_df['Near_Limit_Velocity'].sum())}")
    print(f"Normal Near_Limit_Velocity count: {int(normal_df['Near_Limit_Velocity'].sum())}")


if __name__ == "__main__":
    main()
