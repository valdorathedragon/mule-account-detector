"""FINSIGHT: Mule Account Detection & FIU-IND Compliance Workbench (single-page Streamlit dashboard).

Launch from the project root:  streamlit run ui/app.py
"""

import html
import os
import re
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(PROJECT_ROOT), str(PROJECT_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

try:  # .env is optional; os.environ still works without python-dotenv
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=False)
except ImportError:
    pass

from src.graph_engine import build_account_subgraph
from src.ml_engine import analyze_account, load_scored_data
from src.sar_generator import format_inr, generate_rbi_sar

# ---------------------------------------------------------------- palette
BG, CARD = "#05060f", "#0b0d1e"
CYAN, VIOLET, AMBER, RED = "#22d3ee", "#8b5cf6", "#f59e0b", "#ef4444"
TEXT, MUTED, BORDER = "#e2e8f0", "#94a3b8", "#1e2140"
TIER_COLOR = {"HIGH": RED, "MEDIUM": AMBER, "LOW": CYAN}
LOGO_PATH = PROJECT_ROOT / "assets" / "finsight_logo.jpeg"

st.set_page_config(
    page_title="FINSIGHT: Mule Account Detection",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    f"""
<style>
.stApp {{ background: {BG}; color: {TEXT}; }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stSidebar"] {{ background: {CARD}; border-right: 1px solid {BORDER}; }}
.block-container {{ padding-top: 2.2rem; padding-bottom: 2rem; max-width: 1500px; }}
h1.wb-title {{ font-size: 1.7rem; font-weight: 800; margin: 0 0 .15rem 0;
  background: linear-gradient(90deg, {CYAN}, {VIOLET}); -webkit-background-clip: text;
  -webkit-text-fill-color: transparent; }}
.wb-sub {{ color: {MUTED}; font-size: .85rem; margin-bottom: 1.1rem; }}
.card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; padding: 14px 18px; }}
.kpi-label {{ color: {MUTED}; font-size: .72rem; letter-spacing: .08em; text-transform: uppercase; }}
.kpi-value {{ font-size: 1.55rem; font-weight: 700; margin-top: 4px; line-height: 1.2; word-break: break-word; }}
.kpi-sub {{ color: {MUTED}; font-size: .72rem; margin-top: 4px; }}
.badge {{ display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: .72rem;
  font-weight: 700; letter-spacing: .06em; margin-left: 8px; vertical-align: middle; }}
.sec-title {{ font-size: 1rem; font-weight: 700; margin: .4rem 0 .6rem 0; color: {TEXT}; }}
.sec-title span {{ color: {VIOLET}; }}
.pill {{ background: {CARD}; border: 1px solid {BORDER}; border-left: 4px solid {AMBER};
  border-radius: 8px; padding: 8px 12px; margin-bottom: 8px; font-size: .86rem; }}
.sar-card {{ background: {CARD}; border: 1px solid {BORDER}; border-top: 3px solid {VIOLET};
  border-radius: 12px; padding: 16px 20px; margin-top: 10px; }}
.sar-card h4 {{ margin: 0 0 8px 0; color: {CYAN}; font-size: .8rem; letter-spacing: .1em; text-transform: uppercase; }}
.sar-card p {{ font-size: .88rem; line-height: 1.6; color: {TEXT}; margin: 0 0 10px 0; text-align: justify; }}
.gm {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px; padding: 8px 10px; text-align: center; }}
.gm .k {{ color: {MUTED}; font-size: .65rem; text-transform: uppercase; letter-spacing: .06em; }}
.gm .v {{ font-size: 1.05rem; font-weight: 700; margin-top: 2px; word-break: break-word; }}
.stButton > button[kind="primary"] {{ background: linear-gradient(90deg, {VIOLET}, {CYAN}); border: 0; color: #05060f; font-weight: 700; }}
</style>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------- data
def get_scored_df() -> pd.DataFrame:
    """Return the current validated scored DataFrame from ml_engine's digest-checked cache."""
    return load_scored_data()


def get_accounts(df: pd.DataFrame) -> list[str]:
    return sorted(set(df["nameOrig"].astype(str)) | set(df["nameDest"].astype(str)))


def get_dynamic_presets(df: pd.DataFrame) -> list[tuple[str, str]]:
    """Select top real HIGH, MEDIUM, and LOW accounts from the scored IBM AML dataset."""
    if df.empty or "Risk_Score" not in df.columns:
        return []
    orig_scores = df.groupby(df["nameOrig"].astype(str))["Risk_Score"].max()
    dest_scores = df.groupby(df["nameDest"].astype(str))["Risk_Score"].max()
    acct_scores = pd.concat([orig_scores, dest_scores.drop(labels=orig_scores.index, errors="ignore")])
    both_sides = set(orig_scores.index) & set(dest_scores.index)
    orig_counts = df["nameOrig"].astype(str).value_counts()

    flagged_accts: set[str] = set()
    if "Near_Limit_Velocity" in df.columns:
        flagged_rows = df[df["Near_Limit_Velocity"] == 1]
        flagged_accts = set(flagged_rows["nameOrig"].astype(str)) | set(
            flagged_rows["nameDest"].astype(str)
        )

    presets: list[tuple[str, str]] = []
    used: set[str] = set()

    def _pick(cands: pd.Series, asc: bool, prefer_clean: bool = False, min_orig: int = 1) -> str | None:
        if cands.empty:
            return None
        pool = cands[cands.index.isin(both_sides)]
        if pool.empty:
            pool = cands
        if prefer_clean and flagged_accts:
            clean = pool[~pool.index.isin(flagged_accts)]
            if not clean.empty:
                pool = clean
        if min_orig > 1:
            active = pool[pool.index.map(lambda a: orig_counts.get(a, 0) >= min_orig)]
            if not active.empty:
                pool = active
        for acct in pool.sort_values(ascending=asc, kind="mergesort").index:
            if str(acct) not in used:
                return str(acct)
        return None

    high_acct = _pick(acct_scores[acct_scores >= 80.0], asc=False, min_orig=2)
    if high_acct:
        presets.append((high_acct, "HIGH"))
        used.add(high_acct)

    med_cands = acct_scores[(acct_scores >= 50.0) & (acct_scores < 80.0)]
    med_mid = med_cands[med_cands <= 76.0]
    med_acct = _pick(med_mid if not med_mid.empty else med_cands, asc=False, prefer_clean=True)
    if med_acct:
        presets.append((med_acct, "MEDIUM"))
        used.add(med_acct)

    low_acct = _pick(acct_scores[acct_scores < 50.0], asc=True, prefer_clean=True)
    if low_acct:
        presets.append((low_acct, "LOW"))
        used.add(low_acct)

    return presets


def esc(value: object) -> str:
    return html.escape(str(value))


def kpi_card(label: str, value_html: str, sub: str = "", accent: str = CYAN) -> str:
    return (
        f'<div class="card" style="border-top:3px solid {accent}">'
        f'<div class="kpi-label">{esc(label)}</div>'
        f'<div class="kpi-value">{value_html}</div>'
        f'<div class="kpi-sub">{esc(sub)}</div></div>'
    )


def graph_metric(label: str, value: str, color: str = TEXT) -> str:
    return f'<div class="gm"><div class="k">{esc(label)}</div><div class="v" style="color:{color}">{esc(value)}</div></div>'


def safe_filename(account_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._@-]", "_", account_id)


def _fit_graph_html(raw_html: str, canvas_px: int = 430) -> str:
    """Resize PyVis's 650px container height so it fits inside the 460px iframe without clipping."""
    return raw_html.replace("height: 650px", f"height: {canvas_px}px")


# ---------------------------------------------------------------- state / callbacks
def select_preset(account_id: str) -> None:
    st.session_state["account_select"] = account_id
    st.session_state["run_requested"] = True


def _compute_24h_totals(account_id: str, df: pd.DataFrame) -> tuple[float, float]:
    """Compute explicit trailing 24-hour inflow and outflow totals from dataset timestamps."""
    ts = pd.to_datetime(df["timestamp"], errors="coerce")
    if ts.notna().any():
        cutoff = ts.max() - pd.Timedelta(hours=24)
        window_df = df[ts >= cutoff]
    else:
        window_df = df
    inflow_24h = float(window_df.loc[window_df["nameDest"] == account_id, "amount"].sum())
    outflow_24h = float(window_df.loc[window_df["nameOrig"] == account_id, "amount"].sum())
    return round(inflow_24h, 2), round(outflow_24h, 2)


def run_analysis(account_id: str, df: pd.DataFrame, api_key_override: str | None = None) -> dict:
    result: dict = {
        "account_id": account_id,
        "df": df,
        "error": None,
        "graph_stats": {},
        "graph_html": None,
        "graph_error": None,
        "sar": None,
    }
    try:
        try:
            payload = analyze_account(account_id, df=df)
        except TypeError:
            payload = analyze_account(account_id)
        inflow_24h, outflow_24h = _compute_24h_totals(account_id, df)
        payload = {**payload, "inflow_24h": inflow_24h, "outflow_24h": outflow_24h}
        result["payload"] = payload
    except Exception as exc:  # unknown account / data issue
        result["error"] = f"Analysis failed: {exc}"
        return result

    tmp_path: Path | None = None
    try:
        try:
            fd, tmp_name = tempfile.mkstemp(prefix=".network_", suffix=".html")
            os.close(fd)
            tmp_path = Path(tmp_name)
            graph_stats = build_account_subgraph(account_id, df, output_path=str(tmp_path))
            result["graph_stats"] = graph_stats
        except Exception as exc:
            result["graph_error"] = f"Graph build failed: {exc}"
            return result

        try:
            raw_html = Path(graph_stats["output_path"]).read_text(encoding="utf-8")
            result["graph_html"] = _fit_graph_html(raw_html)
        except Exception as exc:
            result["graph_error"] = f"Graph HTML load failed: {exc}"
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    try:
        result["sar"] = generate_rbi_sar(payload, result["graph_stats"], api_key=api_key_override)
    except TypeError:
        result["sar"] = generate_rbi_sar(payload, result["graph_stats"])
    return result


# ---------------------------------------------------------------- header
if LOGO_PATH.exists():
    head_logo, head_text = st.columns([1.15, 5.85])
    with head_logo:
        st.image(str(LOGO_PATH), width="stretch")
    with head_text:
        st.markdown(
            '<h1 class="wb-title">FINSIGHT: Mule Account Detection</h1>'
            '<div class="wb-sub">Real-Time Detection of Illicit Financial Flows, Rapid Layering, '
            "and Post-KYC Mule Accounts Across Banking Networks</div>",
            unsafe_allow_html=True,
        )
else:
    st.markdown(
        '<h1 class="wb-title">FINSIGHT: Mule Account Detection</h1>'
        '<div class="wb-sub">Real-Time Detection of Illicit Financial Flows, Rapid Layering, '
        "and Post-KYC Mule Accounts Across Banking Networks</div>",
        unsafe_allow_html=True,
    )

try:
    scored_df = get_scored_df()
except Exception as exc:
    st.error(f"Could not load scored data. Run `python src/data_pipeline.py` then `python src/ml_engine.py`. ({exc})")
    st.stop()

accounts = get_accounts(scored_df)
if not accounts:
    st.error("Scored dataset contains no accounts.")
    st.stop()

presets = get_dynamic_presets(scored_df)
default_account = presets[0][0] if presets else accounts[0]
if st.session_state.get("account_select") not in accounts:
    st.session_state["account_select"] = default_account

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width="stretch")
    st.markdown(f'<div class="sec-title"><span>◆</span> Investigator Controls</div>', unsafe_allow_html=True)

    override_key = st.text_input(
        "Gemini API Key (Optional Override)",
        type="password",
        help="Held in memory for this session only. Never logged or written to disk.",
    )
    session_api_key = override_key.strip() or None
    if session_api_key or os.environ.get("GEMINI_API_KEY"):
        st.caption("🟢 Gemini key detected — live SAR synthesis enabled.")
    else:
        st.caption("🟡 No Gemini key — deterministic template SAR will be used.")

    st.markdown("**Demo presets**")
    for preset_id, tier in presets:
        if preset_id in accounts:
            st.button(
                f"[{tier}] {preset_id}",
                key=f"preset_{preset_id}",
                on_click=select_preset,
                args=(preset_id,),
                width="stretch",
            )

    st.selectbox(
        "Search account",
        options=accounts,
        key="account_select",
        help=f"{len(accounts):,} unique accounts in data/scored_bank_data.csv",
    )
    run_clicked = st.button("Run Forensic Analysis", type="primary", width="stretch")

selected = st.session_state["account_select"]
need_run = run_clicked or st.session_state.pop("run_requested", False) or "result" not in st.session_state
if need_run:
    with st.spinner(f"Running forensic analysis for {selected}…"):
        st.session_state["result"] = run_analysis(selected, scored_df, api_key_override=session_api_key)

result = st.session_state["result"]
if result.get("error"):
    st.error(result["error"])
    st.stop()

account_id = result["account_id"]
payload, graph_stats = result["payload"], result["graph_stats"]
tier = payload["risk_tier"]
tier_color = TIER_COLOR.get(tier, CYAN)

if account_id != selected:
    st.info(f"Selection changed to **{selected}** — press *Run Forensic Analysis*. Showing results for {account_id}.")

st.markdown(
    f'<div class="sec-title">Subject account: <span style="color:{CYAN}">{esc(account_id)}</span></div>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------- row 1: KPIs
k1, k2, k3, k4 = st.columns(4)
badge = f'<span class="badge" style="background:{tier_color}22;color:{tier_color};border:1px solid {tier_color}">{esc(tier)}</span>'
k1.markdown(
    kpi_card("Risk Score", f'{payload["risk_score"]:.2f} / 100 {badge}', "IsolationForest, 0–100", tier_color),
    unsafe_allow_html=True,
)
k2.markdown(kpi_card("24h Total Inflow", esc(format_inr(payload.get("inflow_24h", payload["total_inflow"]))), "Credits received (24h window)", CYAN), unsafe_allow_html=True)
k3.markdown(kpi_card("24h Total Outflow", esc(format_inr(payload.get("outflow_24h", payload["total_outflow"]))), "Debits remitted (24h window)", VIOLET), unsafe_allow_html=True)
k4.markdown(
    kpi_card("Pass-Through Ratio", f'{payload["pass_through_ratio"] * 100:.2f}%', "Outflow ÷ inflow", AMBER),
    unsafe_allow_html=True,
)

st.write("")

# ---------------------------------------------------------------- row 2: network | drivers + SAR
left, right = st.columns([1.2, 1])

with left:
    st.markdown('<div class="sec-title"><span>◆</span> 2-Hop Transaction Network</div>', unsafe_allow_html=True)
    if result.get("graph_html"):
        components.html(result["graph_html"], height=460, scrolling=False)
    else:
        st.warning(f"Network graph unavailable: {result.get('graph_error', 'unknown error')}")

    linked = [n for n in graph_stats.get("high_risk_nodes", []) if n != account_id]
    asym = float(graph_stats.get("degree_asymmetry", 0.0))
    metrics = [
        ("Role", str(graph_stats.get("topology", "N/A")).title(), VIOLET),
        ("In-Degree", str(graph_stats.get("in_degree", "—")), CYAN),
        ("Out-Degree", str(graph_stats.get("out_degree", "—")), CYAN),
        ("Degree Asymmetry", f"{asym:+.4f}" if graph_stats else "—", AMBER),
        ("High-Risk Neighbors", str(len(linked)) if graph_stats else "—", RED if linked else TEXT),
    ]
    for col, (label, value, color) in zip(st.columns(5), metrics):
        col.markdown(graph_metric(label, value, color), unsafe_allow_html=True)

with right:
    st.markdown('<div class="sec-title"><span>◆</span> Anomaly Drivers</div>', unsafe_allow_html=True)
    for driver in payload["top_drivers"]:
        st.markdown(f'<div class="pill" style="border-left-color:{tier_color}">{esc(driver)}</div>', unsafe_allow_html=True)

    st.markdown('<div class="sec-title"><span>◆</span> FIU-IND Suspicious Activity Report</div>', unsafe_allow_html=True)
    sar_text = result.get("sar")
    if sar_text:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", sar_text) if p.strip()]
        body = "".join(f"<p>{esc(p)}</p>" for p in paragraphs)
        st.markdown(
            f'<div class="sar-card"><h4>Suspicious Activity Report · {esc(account_id)}</h4>{body}</div>',
            unsafe_allow_html=True,
        )
        st.download_button(
            "⬇ Download SAR (.txt)",
            data=sar_text,
            file_name=f"SAR_{safe_filename(account_id)}.txt",
            mime="text/plain",
            width="stretch",
        )
    else:
        st.warning("SAR unavailable because 2-hop topology metrics could not be computed for this run.")

# ---------------------------------------------------------------- row 3: ledger
st.markdown('<div class="sec-title"><span>◆</span> Account Ledger</div>', unsafe_allow_html=True)
analysis_df = result.get("df", scored_df)
ledger = analysis_df[(analysis_df["nameOrig"] == account_id) | (analysis_df["nameDest"] == account_id)]
ledger = ledger[["txn_id", "timestamp", "nameOrig", "nameDest", "amount", "Pass_Through_Ratio", "Risk_Score"]]
ledger = ledger.sort_values("timestamp").reset_index(drop=True)
st.caption(f"{len(ledger):,} transactions involving {account_id}")
st.dataframe(
    ledger,
    width="stretch",
    hide_index=True,
    height=min(420, 38 + 35 * max(len(ledger), 1)),
    column_config={
        "amount": st.column_config.NumberColumn("amount (INR)", format="%.2f"),
        "Pass_Through_Ratio": st.column_config.NumberColumn("Pass_Through_Ratio", format="%.4f"),
        "Risk_Score": st.column_config.ProgressColumn("Risk_Score", min_value=0.0, max_value=100.0, format="%.2f"),
    },
)
