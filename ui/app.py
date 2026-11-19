"""FINSIGHT: Mule Account Detection & FIU-IND Compliance Workbench (single-page Streamlit dashboard).

Launch from the project root:  streamlit run ui/app.py
"""
from __future__ import annotations

import hashlib
import html
import os
from pathlib import Path
import sys
from typing import Any

from dotenv import load_dotenv
import numpy as np
import pandas as pd
import streamlit as st
from streamlit_option_menu import option_menu

# Ensure project root is on sys.path so `src.*` imports resolve reliably
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.graph_engine import build_account_subgraph
from src.ml_engine import analyze_account, assign_risk_tier, get_scored_mtime, load_scored_data
from src.sar_generator import MODEL_NAME as GEMINI_MODEL_NAME
from src.sar_generator import generate_rbi_sar

LOGO_PATH = PROJECT_ROOT / "assets" / "finsight_logo.jpeg"
NAV_OPTIONS = [
    "Executive Triage",
    "Account Forensics",
    "2-Hop Topology",
    "FIU-IND STR/SAR",
    "Settings",
]
NAV_ICONS = ["speedometer2", "search", "diagram-3", "file-earmark-text", "gear"]
CURRENCY_LABELS = {
    "compact": "Compact Lakhs/Crores (₹12.40 L)",
    "exact": "Exact INR Grouping (₹12,40,000.00)",
}
SAR_MODE_LABELS = {
    True: "Auto-Generate on Tab Open",
    False: "Manual Click Only",
}
HIGH_RISK_THRESHOLD = 80.0
MEDIUM_RISK_THRESHOLD = 50.0
MAX_HIGH_RISK_BADGES = 30
_KPI_ACCENTS = {"#0047AB", "#4F46E5", "#6D28D9", "#98E6C3"}
_SECTION_ACCENTS = {"#0047AB", "#4F46E5", "#6D28D9"}
_ALLOWED_SPACER_HEIGHTS = {"0.5rem", "0.75rem", "1rem", "1.25rem"}
_PALETTE_SWATCHES = (
    ("Navy Blue", "#0A1931"),
    ("Blue", "#0047AB"),
    ("Blue-Violet", "#4F46E5"),
    ("Violet", "#6D28D9"),
    ("Mint Green", "#98E6C3"),
    ("White", "#FFFFFF"),
)

st.set_page_config(
    page_title="FINSIGHT | Mule Account Detection",
    page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else "🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Theme & Styling (Exact 6-Color Palette: Dark Navy & Light White Modes)
# ---------------------------------------------------------------------------
def _palette(dark_mode: bool) -> dict[str, str]:
    """Return CSS color tokens using the 6-color FINSIGHT palette."""
    if dark_mode:
        return {
            "canvas": "#0A1931",
            "surface": "#0E2240",
            "sidebar_bg": "#060D1F",
            "logo_frame_bg": "transparent",
            "logo_frame_pad": "0px",
            "text": "#FFFFFF",
            "muted": "#CBD5E1",
            "border": "rgba(79, 70, 229, 0.35)",
            "kpi_bg": "#0E2240",
            "kpi_border": "rgba(79, 70, 229, 0.35)",
            "kpi_shadow": "0 4px 16px rgba(6, 13, 31, 0.35)",
            "input_bg": "#0E2240",
            "input_border": "rgba(79, 70, 229, 0.45)",
            "low_bg": "rgba(152, 230, 195, 0.16)",
            "low_fg": "#98E6C3",
            "low_border": "rgba(152, 230, 195, 0.55)",
            "med_bg": "rgba(245, 158, 11, 0.18)",
            "med_fg": "#FBBF24",
            "med_border": "rgba(245, 158, 11, 0.50)",
            "high_bg": "rgba(239, 68, 68, 0.18)",
            "high_fg": "#F87171",
            "high_border": "rgba(239, 68, 68, 0.55)",
            "offline_bg": "rgba(109, 40, 217, 0.22)",
            "offline_fg": "#E9D5FF",
            "offline_border": "rgba(109, 40, 217, 0.55)",
            "sar_bg": "#0E2240",
            "sar_border": "rgba(109, 40, 217, 0.45)",
            "nav_icon": "#98E6C3",
            "nav_text": "#FFFFFF",
            "menu_title": "#98E6C3",
        }
    return {
        "canvas": "#FFFFFF",
        "surface": "#F4F7FB",
        "sidebar_bg": "#F4F7FB",
        "logo_frame_bg": "#060D1F",
        "logo_frame_pad": "6px",
        "text": "#0A1931",
        "muted": "#334155",
        "border": "#E2E8F0",
        "kpi_bg": "#FFFFFF",
        "kpi_border": "#E2E8F0",
        "kpi_shadow": "0 1px 4px rgba(10, 25, 49, 0.06)",
        "input_bg": "#FFFFFF",
        "input_border": "#CBD5E1",
        "low_bg": "rgba(152, 230, 195, 0.45)",
        "low_fg": "#0A1931",
        "low_border": "#0047AB",
        "med_bg": "rgba(245, 158, 11, 0.18)",
        "med_fg": "#92400E",
        "med_border": "rgba(217, 119, 6, 0.48)",
        "high_bg": "rgba(239, 68, 68, 0.14)",
        "high_fg": "#B91C1C",
        "high_border": "rgba(220, 38, 38, 0.48)",
        "offline_bg": "rgba(109, 40, 217, 0.12)",
        "offline_fg": "#6D28D9",
        "offline_border": "rgba(109, 40, 217, 0.42)",
        "sar_bg": "#F4F7FB",
        "sar_border": "rgba(109, 40, 217, 0.32)",
        "nav_icon": "#0047AB",
        "nav_text": "#0A1931",
        "menu_title": "#0047AB",
    }


def inject_custom_css(dark_mode: bool) -> None:
    """Inject FINSIGHT 6-color Dark/Light theme CSS across canvas, sidebar, and widgets."""
    p = _palette(dark_mode)
    st.markdown(
        f"""
        <style>
        .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {{
            background-color: {p["canvas"]};
            color: {p["text"]};
        }}
        [data-testid="stSidebar"], [data-testid="stSidebarContent"] {{
            background-color: {p["sidebar_bg"]} !important;
            color: {p["text"]};
        }}
        [data-testid="stSidebar"] {{
            border-right: 1px solid {p["border"]};
        }}
        [data-testid="stSidebar"] [data-testid="stImage"] {{
            background-color: {p["logo_frame_bg"]};
            padding: {p["logo_frame_pad"]};
            border-radius: 10px;
            border: none;
            box-shadow: none;
        }}
        [data-testid="stSidebar"] [data-testid="stImage"] img {{
            border-radius: 8px;
            display: block;
        }}
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] label,
        [data-testid="stAppViewContainer"] h1,
        [data-testid="stAppViewContainer"] h2,
        [data-testid="stAppViewContainer"] h3,
        [data-testid="stAppViewContainer"] label,
        [data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stAppViewContainer"] [data-testid="stCaptionContainer"] {{
            color: {p["text"]};
        }}
        [data-testid="stVerticalBlockBorderWrapper"] {{
            background-color: {p["surface"]};
            border: 1px solid {p["border"]} !important;
            border-radius: 12px;
        }}
        [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
        [data-testid="stMultiSelect"] div[data-baseweb="select"] > div,
        [data-testid="stTextInput"] div[data-baseweb="input"] > div,
        [data-testid="stTextInput"] input,
        [data-testid="stTextArea"] textarea {{
            background-color: {p["input_bg"]} !important;
            color: {p["text"]} !important;
            border-color: {p["input_border"]} !important;
        }}
        [data-testid="stSelectbox"] svg,
        [data-testid="stMultiSelect"] svg {{
            fill: {p["text"]} !important;
        }}
        [data-testid="stMultiSelect"] span[data-baseweb="tag"] {{
            background-color: #0047AB !important;
            color: #FFFFFF !important;
            border: 1px solid #4F46E5 !important;
        }}
        div[data-baseweb="popover"] ul[role="listbox"] {{
            background-color: {p["surface"]} !important;
            color: {p["text"]} !important;
            border: 1px solid {p["border"]} !important;
        }}
        [data-testid="stDataFrame"] {{
            border: 1px solid {p["border"]};
            border-radius: 10px;
            overflow: hidden;
        }}
        .stButton > button[kind="primary"],
        button[data-testid="stBaseButton-primary"] {{
            background-color: #0047AB !important;
            color: #FFFFFF !important;
            border: 1px solid #4F46E5 !important;
        }}
        .stButton > button[kind="primary"]:hover,
        button[data-testid="stBaseButton-primary"]:hover {{
            background-color: #0B5ED7 !important;
            color: #FFFFFF !important;
        }}
        .stButton > button[kind="secondary"],
        button[data-testid="stBaseButton-secondary"],
        [data-testid="stDownloadButton"] > button {{
            background-color: {p["surface"]} !important;
            color: {p["text"]} !important;
            border: 1px solid {p["border"]} !important;
        }}
        .stButton > button[kind="secondary"]:hover,
        button[data-testid="stBaseButton-secondary"]:hover,
        [data-testid="stDownloadButton"] > button:hover {{
            border-color: #4F46E5 !important;
        }}
        .finsight-banner {{
            background: linear-gradient(135deg, #0A1931 0%, #0047AB 55%, #6D28D9 100%);
            border: 1px solid rgba(79, 70, 229, 0.55);
            border-radius: 12px;
            padding: 1.15rem 1.45rem;
            margin-bottom: 1.1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 8px 24px rgba(10, 25, 49, 0.24);
        }}
        .finsight-title {{
            font-size: 1.55rem;
            font-weight: 800;
            letter-spacing: 0.03em;
            color: #FFFFFF !important;
            margin: 0;
        }}
        .finsight-subtitle {{
            color: rgba(255, 255, 255, 0.88) !important;
            font-size: 0.86rem;
            margin-top: 0.22rem;
        }}
        .finsight-banner .badge-calibrated {{
            background: rgba(152, 230, 195, 0.18) !important;
            color: #98E6C3 !important;
            border: 1px solid #98E6C3 !important;
        }}
        .finsight-section-header {{
            border-left: 4px solid #0047AB;
            padding: 0.25rem 0 0.25rem 0.9rem;
            margin: 0.2rem 0 0.9rem 0;
        }}
        .finsight-section-title {{
            color: {p["text"]};
            font-size: 1.32rem;
            font-weight: 700;
            line-height: 1.25;
            margin: 0;
        }}
        .finsight-section-desc {{
            color: {p["muted"]};
            font-size: 0.85rem;
            margin-top: 0.22rem;
        }}
        .finsight-kpi-card {{
            background-color: {p["kpi_bg"]};
            border: 1px solid {p["kpi_border"]};
            border-top: 3px solid #0047AB;
            border-radius: 12px;
            padding: 0.95rem 1.1rem;
            height: 100%;
            box-shadow: {p["kpi_shadow"]};
        }}
        .finsight-kpi-label {{
            color: {p["muted"]};
            font-size: 0.78rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        .finsight-kpi-value {{
            color: {p["text"]};
            font-size: 1.52rem;
            font-weight: 700;
            margin: 0.25rem 0 0.2rem 0;
            line-height: 1.2;
        }}
        .finsight-kpi-desc {{
            color: {p["muted"]};
            font-size: 0.78rem;
        }}
        .finsight-swatch-grid {{
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.55rem;
            margin-top: 0.65rem;
        }}
        .finsight-swatch-item {{
            display: flex;
            align-items: center;
            gap: 0.55rem;
            background: {p["kpi_bg"]};
            border: 1px solid {p["kpi_border"]};
            border-radius: 8px;
            padding: 0.45rem 0.6rem;
        }}
        .finsight-swatch-chip {{
            width: 18px;
            height: 18px;
            border-radius: 5px;
            border: 1px solid {p["border"]};
            flex-shrink: 0;
        }}
        .finsight-swatch-meta {{
            font-size: 0.76rem;
            line-height: 1.2;
            color: {p["text"]};
        }}
        .risk-pill {{
            display: inline-block;
            padding: 0.24rem 0.72rem;
            border-radius: 9999px;
            font-size: 0.76rem;
            font-weight: 700;
            letter-spacing: 0.05em;
            text-transform: uppercase;
        }}
        .risk-high {{
            background: {p["high_bg"]};
            color: {p["high_fg"]};
            border: 1px solid {p["high_border"]};
        }}
        .risk-medium {{
            background: {p["med_bg"]};
            color: {p["med_fg"]};
            border: 1px solid {p["med_border"]};
        }}
        .risk-low, .badge-calibrated, .badge-live {{
            background: {p["low_bg"]};
            color: {p["low_fg"]};
            border: 1px solid {p["low_border"]};
        }}
        .badge-offline {{
            background: {p["offline_bg"]};
            color: {p["offline_fg"]};
            border: 1px solid {p["offline_border"]};
        }}
        .sar-paper {{
            background-color: {p["sar_bg"]};
            border-left: 4px solid #6D28D9;
            border-top: 1px solid {p["sar_border"]};
            border-right: 1px solid {p["sar_border"]};
            border-bottom: 1px solid {p["sar_border"]};
            border-radius: 8px;
            padding: 1.25rem 1.4rem;
            font-size: 0.95rem;
            line-height: 1.68;
            color: {p["text"]};
        }}
        hr {{
            border-color: {p["border"]};
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_spacer(height: str = "0.75rem") -> None:
    """Render a zero-dependency vertical CSS spacer."""
    safe_height = height if height in _ALLOWED_SPACER_HEIGHTS else "0.75rem"
    st.markdown(f'<div style="height: {safe_height};"></div>', unsafe_allow_html=True)


def render_section_header(title: str, subtitle: str, accent_color: str = "#0047AB") -> None:
    """Render a native themed HTML section header with a left accent bar."""
    safe_accent = accent_color if accent_color in _SECTION_ACCENTS else "#0047AB"
    st.markdown(
        f"""
        <div class="finsight-section-header" style="border-left-color: {safe_accent};">
            <div class="finsight-section-title">{html.escape(title)}</div>
            <div class="finsight-section-desc">{html.escape(subtitle)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpi_card(
    title: str, value: str, subtitle: str, accent_color: str = "#0047AB"
) -> None:
    """Render an XSS-safe native HTML KPI card accented from the 6-color FINSIGHT palette."""
    safe_accent = accent_color if accent_color in _KPI_ACCENTS else "#0047AB"
    st.markdown(
        f"""
        <div class="finsight-kpi-card" style="border-top-color: {safe_accent};">
            <div class="finsight-kpi-label">{html.escape(title)}</div>
            <div class="finsight-kpi-value">{html.escape(value)}</div>
            <div class="finsight-kpi-desc">{html.escape(subtitle)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Indian Currency Formatting & Zero-Hash Data Caching Layer
# ---------------------------------------------------------------------------
def format_inr(amount: float | int | None, compact: bool = False) -> str:
    """Format numeric amounts in Indian Rupee conventions (Lakhs/Crores or Indian commas)."""
    if amount is None or pd.isna(amount):
        return "₹0.00"
    val = float(amount)
    sign = "-" if val < 0 else ""
    abs_val = abs(val)

    if compact:
        if abs_val >= 1e7:
            return f"{sign}₹{abs_val / 1e7:.2f} Cr"
        if abs_val >= 1e5:
            return f"{sign}₹{abs_val / 1e5:.2f} L"

    integer_part, decimal_part = f"{abs_val:.2f}".split(".")
    if len(integer_part) <= 3:
        formatted_int = integer_part
    else:
        last_three = integer_part[-3:]
        remaining = integer_part[:-3]
        groups = []
        while remaining:
            groups.append(remaining[-2:])
            remaining = remaining[:-2]
        formatted_int = ",".join(reversed(groups)) + "," + last_three
    return f"{sign}₹{formatted_int}.{decimal_part}"


@st.cache_data(show_spinner=False)
def load_logo_bytes(logo_mtime: float) -> bytes | None:
    """Read and cache FINSIGHT logo bytes keyed only by modification timestamp."""
    if logo_mtime <= 0.0 or not LOGO_PATH.exists():
        return None
    return LOGO_PATH.read_bytes()


@st.cache_data(show_spinner=False)
def get_cached_scored_data(mtime: float) -> pd.DataFrame:
    """Load transaction-level scored dataset once per artifact modification time."""
    return load_scored_data()


@st.cache_data(show_spinner=False)
def get_account_summary_df(_tx_df: pd.DataFrame, mtime: float) -> pd.DataFrame:
    """Vectorized aggregation from transaction ledger to unique bank account profiles.

    Produces one row per unique account (SAV_, CUR_, CORP_) matching `analyze_account()`
    in `src/ml_engine.py`, without hashing `_tx_df` on cache lookup.
    """
    cols = [
        "Account_ID",
        "Risk_Score",
        "Risk_Tier",
        "Total_Inflow",
        "Total_Outflow",
        "Pass_Through_Ratio",
        "Near_Limit_Velocity",
        "Tx_Count",
    ]
    if _tx_df is None or _tx_df.empty:
        return pd.DataFrame(columns=cols)

    orig_s = _tx_df["nameOrig"].astype(str)
    dest_s = _tx_df["nameDest"].astype(str)

    orig_agg = _tx_df.groupby(orig_s, sort=False).agg(
        outflow=("amount", "sum"),
        orig_risk=("Risk_Score", "max"),
        orig_nlv=("Near_Limit_Velocity", "sum"),
        orig_cnt=("amount", "size"),
    )
    dest_agg = _tx_df.groupby(dest_s, sort=False).agg(
        inflow=("amount", "sum"),
        dest_risk=("Risk_Score", "max"),
        dest_nlv=("Near_Limit_Velocity", "sum"),
        dest_cnt=("amount", "size"),
    )

    all_ids = orig_agg.index.union(dest_agg.index)

    self_mask = orig_s == dest_s
    if self_mask.any():
        self_agg = _tx_df.loc[self_mask].groupby(orig_s[self_mask], sort=False).agg(
            self_nlv=("Near_Limit_Velocity", "sum"),
            self_cnt=("amount", "size"),
        )
        self_nlv = self_agg["self_nlv"].reindex(all_ids, fill_value=0).to_numpy(dtype=np.int64)
        self_cnt = self_agg["self_cnt"].reindex(all_ids, fill_value=0).to_numpy(dtype=np.int64)
    else:
        self_nlv = np.zeros(len(all_ids), dtype=np.int64)
        self_cnt = np.zeros(len(all_ids), dtype=np.int64)

    raw_inflow = dest_agg["inflow"].reindex(all_ids, fill_value=0.0).to_numpy(dtype=float)
    raw_outflow = orig_agg["outflow"].reindex(all_ids, fill_value=0.0).to_numpy(dtype=float)

    orig_risk = orig_agg["orig_risk"].reindex(all_ids)
    dest_risk = dest_agg["dest_risk"].reindex(all_ids)
    risk_score = np.round(orig_risk.combine_first(dest_risk).fillna(0.0).to_numpy(dtype=float), 2)
    risk_tier = np.select(
        [risk_score >= HIGH_RISK_THRESHOLD, risk_score >= MEDIUM_RISK_THRESHOLD],
        ["HIGH", "MEDIUM"],
        default="LOW",
    )

    ptr = np.round(np.where(raw_inflow > 0.0, raw_outflow / np.where(raw_inflow > 0.0, raw_inflow, 1.0), 0.0), 4)
    orig_nlv = orig_agg["orig_nlv"].reindex(all_ids, fill_value=0).to_numpy(dtype=np.int64)
    dest_nlv = dest_agg["dest_nlv"].reindex(all_ids, fill_value=0).to_numpy(dtype=np.int64)
    orig_cnt = orig_agg["orig_cnt"].reindex(all_ids, fill_value=0).to_numpy(dtype=np.int64)
    dest_cnt = dest_agg["dest_cnt"].reindex(all_ids, fill_value=0).to_numpy(dtype=np.int64)

    summary = pd.DataFrame(
        {
            "Account_ID": all_ids.astype(str),
            "Risk_Score": risk_score,
            "Risk_Tier": risk_tier,
            "Total_Inflow": np.round(raw_inflow, 2),
            "Total_Outflow": np.round(raw_outflow, 2),
            "Pass_Through_Ratio": ptr,
            "Near_Limit_Velocity": orig_nlv + dest_nlv - self_nlv,
            "Tx_Count": orig_cnt + dest_cnt - self_cnt,
        }
    )
    return summary.sort_values(by=["Risk_Score", "Account_ID"], ascending=[False, True]).reset_index(
        drop=True
    )


@st.cache_data(show_spinner=False)
def get_cached_analysis(account_id: str, mtime: float, _tx_df: pd.DataFrame) -> dict[str, Any]:
    """Run and cache per-account forensic scoring keyed strictly by (account_id, mtime)."""
    return analyze_account(account_id, df=_tx_df, cache_key=mtime)


@st.cache_data(show_spinner=False)
def get_cached_subgraph(
    account_id: str,
    mtime: float,
    max_nodes: int,
    enable_physics: bool,
    dark_mode: bool,
    _tx_df: pd.DataFrame,
) -> dict[str, Any]:
    """Run and cache 2-hop topology extraction keyed by account, mtime, and visual controls."""
    return build_account_subgraph(
        account_id,
        _tx_df,
        save_html=False,
        cache_key=mtime,
        max_nodes=max_nodes,
        enable_physics=enable_physics,
        dark_mode=dark_mode,
    )


@st.cache_data(ttl=3600, show_spinner=False)
def get_cached_sar(
    account_id: str,
    mtime: float,
    key_fingerprint: str,
    refresh_nonce: int,
    _analysis: dict[str, Any],
    _graph_stats: dict[str, Any],
    _api_key: str | None = None,
) -> str:
    """Cache SAR generation per account, dataset timestamp, key fingerprint, and refresh nonce."""
    return generate_rbi_sar(_analysis, _graph_stats, api_key=_api_key)


def get_dynamic_presets(acct_df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Return canonical IBM AML benchmark presets with live scores from account summary."""
    defaults = {
        "SAV_4405_SBI": {"tier": "HIGH", "score": 100.00, "label": "SAV_4405_SBI (HIGH · 100.0)"},
        "SAV_3416_HDFC": {"tier": "MEDIUM", "score": 76.00, "label": "SAV_3416_HDFC (MEDIUM · 76.0)"},
        "SAV_3100_HDFC": {"tier": "LOW", "score": 33.75, "label": "SAV_3100_HDFC (LOW · 33.8)"},
    }
    if acct_df is None or acct_df.empty or "Account_ID" not in acct_df.columns:
        return defaults

    indexed = acct_df.set_index("Account_ID", drop=False)
    if all(acc in indexed.index for acc in defaults):
        live_presets: dict[str, dict[str, Any]] = {}
        for acc_id in defaults:
            row = indexed.loc[acc_id]
            sc = float(row["Risk_Score"])
            tier = str(row["Risk_Tier"]).upper()
            live_presets[acc_id] = {
                "tier": tier,
                "score": sc,
                "label": f"{acc_id} ({tier} · {sc:.1f})",
            }
        return live_presets

    resolved: dict[str, dict[str, Any]] = {}
    for tier in ["HIGH", "MEDIUM", "LOW"]:
        subset = acct_df[acct_df["Risk_Tier"] == tier]
        if not subset.empty:
            row = subset.iloc[0]
            acc_id = str(row["Account_ID"])
            sc = float(row["Risk_Score"])
            resolved[acc_id] = {
                "tier": tier,
                "score": sc,
                "label": f"{acc_id} ({tier} · {sc:.1f})",
            }
    return resolved or defaults


def risk_badge_html(tier: str) -> str:
    """Return a sanitized HTML badge for HIGH / MEDIUM / LOW risk tiers."""
    clean_tier = html.escape(str(tier or "UNKNOWN").upper())
    css_class = {
        "HIGH": "risk-high",
        "MEDIUM": "risk-medium",
        "LOW": "risk-low",
    }.get(clean_tier, "risk-low")
    return f'<span class="risk-pill {css_class}">{clean_tier} RISK</span>'


def gemini_status_badge_html(is_live: bool) -> str:
    """Return a sanitized status badge showing Live Gemini vs Offline Fallback."""
    if is_live:
        return '<span class="risk-pill badge-live">Live Gemini 3.8 Flash</span>'
    return '<span class="risk-pill badge-offline">Offline Template Fallback</span>'


def classify_account_segment(account_id: str) -> str:
    """Identify Indian banking account category from prefix."""
    upper_id = account_id.upper()
    if upper_id.startswith("SAV_"):
        return "Savings Account (Retail)"
    if upper_id.startswith("CUR_"):
        return "Current Account (Commercial)"
    if upper_id.startswith("CORP_"):
        return "Corporate Treasury Account"
    return "Scheduled Commercial Bank Account"


def extract_bank_code(account_id: str) -> str:
    """Extract institution identifier from account string."""
    parts = account_id.upper().split("_")
    return parts[-1] if len(parts) >= 3 else "Scheduled Bank"


# ---------------------------------------------------------------------------
# Session State & Settings Helpers
# ---------------------------------------------------------------------------
def _init_session_state(default_account: str) -> None:
    """Initialize persistent configuration and navigation keys once per session."""
    if not st.session_state.get("_dotenv_loaded", False):
        load_dotenv(PROJECT_ROOT / ".env", override=False)
        st.session_state["_dotenv_loaded"] = True

    defaults: dict[str, Any] = {
        "cfg_dark_mode": True,
        "cfg_max_graph_nodes": 65,
        "cfg_enable_graph_physics": False,
        "cfg_currency_mode": "compact",
        "cfg_sar_auto_generate": True,
        "active_nav": "Executive Triage",
        "_prev_active_nav": "Executive Triage",
        "selected_account": default_account,
        "sar_cache_by_account": {},
        "sar_refresh_nonce": {},
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def _apply_pending_state() -> None:
    """Apply cross-rerun state transitions before widgets instantiate."""
    if "pending_account_select" in st.session_state:
        target = st.session_state.pop("pending_account_select")
        st.session_state["selected_account"] = target
        st.session_state["global_account_selector"] = target
    if st.session_state.pop("_clear_api_input", False):
        st.session_state["w_gemini_api_key"] = ""


def _sync_selected_account() -> None:
    """Sync top account selector widget back to persistent selected_account."""
    chosen = st.session_state.get("global_account_selector")
    if chosen:
        st.session_state["selected_account"] = chosen


def _on_dark_mode_change() -> None:
    st.session_state["cfg_dark_mode"] = bool(st.session_state.get("w_dark_mode", True))


def _on_max_nodes_change() -> None:
    st.session_state["cfg_max_graph_nodes"] = int(st.session_state.get("w_max_graph_nodes", 65))


def _on_physics_change() -> None:
    st.session_state["cfg_enable_graph_physics"] = bool(
        st.session_state.get("w_enable_graph_physics", False)
    )


def _on_currency_change() -> None:
    label = st.session_state.get("w_currency_mode", CURRENCY_LABELS["compact"])
    st.session_state["cfg_currency_mode"] = (
        "exact" if label == CURRENCY_LABELS["exact"] else "compact"
    )


def _on_sar_mode_change() -> None:
    label = st.session_state.get("w_sar_mode", SAR_MODE_LABELS[True])
    st.session_state["cfg_sar_auto_generate"] = label == SAR_MODE_LABELS[True]


def _active_api_key() -> tuple[str | None, str]:
    """Return active in-memory Gemini API key and its non-secret fingerprint."""
    raw = os.environ.get("GEMINI_API_KEY", "").strip()
    if not raw:
        return None, "offline"
    fingerprint = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return raw, fingerprint


# ---------------------------------------------------------------------------
# Sidebar Navigation & Benchmark Presets
# ---------------------------------------------------------------------------
def render_sidebar(presets: dict[str, dict[str, Any]], dark_mode: bool) -> str:
    """Render sidebar branding, 5-module navigation menu, and benchmark presets."""
    p = _palette(dark_mode)
    logo_mtime = LOGO_PATH.stat().st_mtime if LOGO_PATH.exists() else 0.0
    logo_bytes = load_logo_bytes(logo_mtime)

    with st.sidebar:
        if logo_bytes is not None:
            st.image(logo_bytes, width="stretch")
        else:
            st.markdown("### 🛡️ FINSIGHT AML")

        st.caption("FIU-IND Compliance & Mule Account Intelligence")
        st.divider()

        current_nav = st.session_state["active_nav"]
        if current_nav not in NAV_OPTIONS:
            current_nav = NAV_OPTIONS[0]
            st.session_state["active_nav"] = current_nav

        prev_nav = st.session_state.get("_prev_active_nav", current_nav)
        manual_idx = st.session_state.pop("nav_manual_select", None)
        programmatic_nav = False
        if current_nav != prev_nav:
            programmatic_nav = True
            manual_idx = NAV_OPTIONS.index(current_nav)
            st.session_state["sidebar_nav_menu"] = current_nav

        selected_nav = option_menu(
            menu_title="Compliance Modules",
            options=NAV_OPTIONS,
            icons=NAV_ICONS,
            menu_icon="shield-lock",
            default_index=NAV_OPTIONS.index(current_nav),
            manual_select=manual_idx,
            key="sidebar_nav_menu",
            styles={
                "container": {"padding": "0!important", "background-color": "transparent"},
                "menu-title": {
                    "font-size": "12px",
                    "text-transform": "uppercase",
                    "letter-spacing": "0.08em",
                    "font-weight": "700",
                    "color": p["menu_title"],
                    "margin-bottom": "4px",
                },
                "menu-icon": {"color": p["menu_title"], "font-size": "13px"},
                "icon": {"color": p["nav_icon"], "font-size": "15px"},
                "nav-link": {
                    "font-size": "14px",
                    "text-align": "left",
                    "margin": "3px 0px",
                    "color": p["nav_text"],
                    "border-radius": "8px",
                },
                "nav-link-selected": {
                    "background-color": "#0047AB",
                    "color": "#FFFFFF",
                    "border": "1px solid #4F46E5",
                    "font-weight": "600",
                },
            },
        )
        if not programmatic_nav and selected_nav in NAV_OPTIONS:
            st.session_state["active_nav"] = selected_nav
        st.session_state["_prev_active_nav"] = st.session_state["active_nav"]

        st.divider()
        st.markdown("**Quick Benchmark Presets**")
        st.caption("IBM AML HI-Small calibrated INR accounts")

        for acc_id, meta in presets.items():
            btn_type = "primary" if meta["tier"] == "HIGH" else "secondary"
            if st.button(
                meta["label"],
                key=f"preset_btn_{acc_id}",
                width="stretch",
                type=btn_type,
            ):
                st.session_state["pending_account_select"] = acc_id
                st.rerun()

        st.divider()
        with st.container(border=True):
            st.markdown("**Model & Threshold Telemetry**")
            st.caption(
                "• **Detector:** IsolationForest (`contamination=0.05`)\n"
                "• **Precision (HIGH):** `88.67%`\n"
                "• **PAN Structuring Window:** `₹45,000 – ₹50,000`\n"
                "• **RTGS Threshold Window:** `₹1,80,000 – ₹2,00,000`"
            )

    return st.session_state["active_nav"]


# ---------------------------------------------------------------------------
# Tab 1: Executive Triage & Portfolio Surveillance
# ---------------------------------------------------------------------------
def render_executive_triage(acct_df: pd.DataFrame, compact_inr: bool) -> None:
    """Render portfolio-wide unique bank account metrics and searchable alert queue."""
    render_section_header(
        "Portfolio Surveillance & Alert Triage",
        "Real-time IsolationForest anomaly scoring across Savings, Current, and Corporate ledgers",
        accent_color="#0047AB",
    )

    total_accounts = len(acct_df)
    high_count = int((acct_df["Risk_Tier"] == "HIGH").sum())
    med_count = int((acct_df["Risk_Tier"] == "MEDIUM").sum())
    low_count = int((acct_df["Risk_Tier"] == "LOW").sum())

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi_card("Monitored Accounts", f"{total_accounts:,}", "SAV / CUR / CORP Ledgers", "#0047AB")
    with c2:
        render_kpi_card("HIGH Risk Alerts", f"{high_count:,}", "88.67% Precision · Priority STR", "#6D28D9")
    with c3:
        render_kpi_card("MEDIUM Risk Watchlist", f"{med_count:,}", "Enhanced Due Diligence (EDD)", "#4F46E5")
    with c4:
        render_kpi_card("LOW Risk Baseline", f"{low_count:,}", "Standard KYC Monitoring", "#98E6C3")

    render_spacer()

    with st.container(border=True):
        st.subheader("Alert Queue & Entity Filtering")
        f1, f2, f3 = st.columns([1.2, 1.2, 2.0])

        with f1:
            tier_filter = st.multiselect(
                "Risk Tier",
                options=["HIGH", "MEDIUM", "LOW"],
                default=["HIGH", "MEDIUM"],
                key="triage_tier_filter",
            )
        with f2:
            segment_filter = st.multiselect(
                "Account Type",
                options=["SAV_", "CUR_", "CORP_"],
                default=["SAV_", "CUR_", "CORP_"],
                format_func=lambda x: {
                    "SAV_": "Savings (SAV)",
                    "CUR_": "Current (CUR)",
                    "CORP_": "Corporate (CORP)",
                }.get(x, x),
                key="triage_segment_filter",
            )
        with f3:
            search_query = st.text_input(
                "Search Account ID or Bank (e.g., SAV_4405_SBI, KOTAK, HDFC)",
                value="",
                key="triage_search_query",
            ).strip().upper()

        mask = pd.Series(True, index=acct_df.index)
        if tier_filter:
            mask &= acct_df["Risk_Tier"].isin(tier_filter)
        if segment_filter:
            pattern = "|".join(f"^{seg}" for seg in segment_filter)
            mask &= acct_df["Account_ID"].str.upper().str.contains(pattern, regex=True)
        if search_query:
            mask &= acct_df["Account_ID"].str.upper().str.contains(search_query, regex=False)

        filtered = acct_df.loc[mask]
        display_df = filtered.head(100).copy()
        display_df["Total_Inflow"] = display_df["Total_Inflow"].map(lambda v: format_inr(v, compact=compact_inr))
        display_df["Total_Outflow"] = display_df["Total_Outflow"].map(
            lambda v: format_inr(v, compact=compact_inr)
        )

        st.dataframe(display_df, width="stretch", hide_index=True, height=340)
        st.caption(f"Showing top {len(display_df)} of {len(filtered):,} matching bank accounts.")

        if not filtered.empty:
            q1, q2 = st.columns([3, 1])
            with q1:
                chosen_from_table = st.selectbox(
                    "Select an account from filtered queue to inspect:",
                    options=filtered["Account_ID"].head(100).tolist(),
                    key="triage_inspect_select",
                )
            with q2:
                render_spacer()
                if st.button("Load into Forensics →", width="stretch", type="primary"):
                    st.session_state["pending_account_select"] = chosen_from_table
                    st.session_state["nav_manual_select"] = NAV_OPTIONS.index("Account Forensics")
                    st.session_state["active_nav"] = "Account Forensics"
                    st.rerun()


# ---------------------------------------------------------------------------
# Tab 2: Deep-Dive Account Forensics
# ---------------------------------------------------------------------------
def render_account_forensics(analysis: dict[str, Any], compact_inr: bool) -> None:
    """Render single-account behavioral forensics, INR cash flows, and anomaly drivers."""
    acc_id = str(analysis.get("account_id", "UNKNOWN"))
    risk_score = float(analysis.get("risk_score", 0.0))
    risk_tier = str(analysis.get("risk_tier", "LOW")).upper()
    inflow = float(analysis.get("total_inflow", 0.0))
    outflow = float(analysis.get("total_outflow", 0.0))
    ptr = float(analysis.get("pass_through_ratio", 0.0))
    top_drivers = analysis.get("top_drivers", [])
    counterparties = analysis.get("counterparties", [])

    render_section_header(
        f"Behavioral & Transactional Forensics — {acc_id}",
        f"{classify_account_segment(acc_id)} · Institution: {extract_bank_code(acc_id)}",
        accent_color="#4F46E5",
    )

    score_accent = {"HIGH": "#6D28D9", "MEDIUM": "#4F46E5"}.get(risk_tier, "#98E6C3")
    inflow_main = format_inr(inflow, compact=compact_inr)
    inflow_alt = format_inr(inflow, compact=not compact_inr)
    outflow_main = format_inr(outflow, compact=compact_inr)
    outflow_alt = format_inr(outflow, compact=not compact_inr)

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        render_kpi_card("Composite Mule Score", f"{risk_score:.2f} / 100", f"Tier: {risk_tier}", score_accent)
    with m2:
        render_kpi_card("Total Credit Inflow", inflow_main, inflow_alt, "#0047AB")
    with m3:
        render_kpi_card("Total Debit Outflow", outflow_main, outflow_alt, "#4F46E5")
    with m4:
        ptr_status = "Mule Layering Alert (≈1.0)" if 0.85 <= ptr <= 1.15 else "Normal Retention"
        render_kpi_card(
            "Pass-Through Ratio",
            f"{ptr:.2f}x",
            ptr_status,
            "#6D28D9" if ptr >= 0.85 else "#98E6C3",
        )

    render_spacer()

    left_col, right_col = st.columns([1.15, 1.0])
    with left_col:
        with st.container(border=True):
            st.subheader("Primary Anomaly & Structuring Drivers")
            st.caption("Feature deviations driving IsolationForest anomaly assignment")

            if isinstance(top_drivers, dict):
                driver_rows = [
                    {"Indicator / Feature": str(k), "Observed Signal": str(v)}
                    for k, v in top_drivers.items()
                ]
                st.dataframe(pd.DataFrame(driver_rows), width="stretch", hide_index=True)
            elif isinstance(top_drivers, list) and top_drivers:
                if isinstance(top_drivers[0], dict):
                    st.dataframe(pd.DataFrame(top_drivers), width="stretch", hide_index=True)
                else:
                    for idx, item in enumerate(top_drivers, start=1):
                        st.markdown(f"**{idx}.** {html.escape(str(item))}")
            else:
                st.info("No elevated anomaly drivers flagged above baseline thresholds for this account.")

            st.divider()
            st.markdown("**Regulatory Threshold Context (RBI / FIU-IND)**")
            st.markdown(
                "- **PAN Reporting Structuring (`₹45k – ₹50k`):** Repeated credits/debits just below the ₹50,000 PAN verification threshold indicate deliberate smurfing.\n"
                "- **RTGS High-Value Structuring (`₹1.8L – ₹2.0L`):** Splitting transfers immediately under the ₹2,00,000 RTGS floor evades real-time high-value scrutiny."
            )

    with right_col:
        with st.container(border=True):
            st.subheader("Connected Counterparty Ledger")
            st.caption("Direct inbound & outbound fund-flow counterparties")

            if isinstance(counterparties, pd.DataFrame) and not counterparties.empty:
                st.dataframe(counterparties, width="stretch", hide_index=True, height=320)
            elif isinstance(counterparties, list) and counterparties:
                if isinstance(counterparties[0], dict):
                    st.dataframe(pd.DataFrame(counterparties), width="stretch", hide_index=True, height=320)
                else:
                    cp_df = pd.DataFrame({"Counterparty Account": [str(c) for c in counterparties]})
                    st.dataframe(cp_df, width="stretch", hide_index=True, height=320)
            else:
                st.info("No direct counterparty records returned for this account.")


# ---------------------------------------------------------------------------
# Tab 3: 2-Hop Fund-Flow Topology (PyVis Interactive Graph)
# ---------------------------------------------------------------------------
def render_graph_topology(
    account_id: str,
    tx_df: pd.DataFrame,
    mtime: float,
    max_nodes: int,
    enable_physics: bool,
    dark_mode: bool,
) -> dict[str, Any]:
    """Build and render the cached 2-hop PyVis subgraph directly from memory."""
    render_section_header(
        f"2-Hop Fund-Flow Topology — {account_id}",
        "Interactive PyVis network analysis detecting fan-in collection, fan-out dispersal, and mule rings",
        accent_color="#0047AB",
    )

    graph_stats = get_cached_subgraph(account_id, mtime, max_nodes, enable_physics, dark_mode, tx_df)
    in_deg = int(graph_stats.get("in_degree", 0))
    out_deg = int(graph_stats.get("out_degree", 0))
    asymmetry = float(graph_stats.get("degree_asymmetry", 0.0))
    topology = str(graph_stats.get("topology", "Standard Bilateral"))
    hr_count = int(graph_stats.get("high_risk_node_count", 0))
    hr_nodes = graph_stats.get("high_risk_nodes", [])

    g1, g2, g3, g4 = st.columns(4)
    with g1:
        render_kpi_card("Detected Topology", topology, f"In: {in_deg} · Out: {out_deg}", "#0047AB")
    with g2:
        render_kpi_card("Degree Asymmetry", f"{asymmetry:+.2f}", "(In - Out) / Total Degree", "#4F46E5")
    with g3:
        render_kpi_card("2-Hop High-Risk Nodes", f"{hr_count:,}", "Full 2-hop contagion count", "#6D28D9")
    with g4:
        render_kpi_card(
            "Subgraph Connectivity",
            f"{in_deg + out_deg} Edges",
            f"Rendered {graph_stats.get('rendered_nodes', 0)}/{graph_stats.get('num_nodes', 0)} nodes",
            "#98E6C3",
        )

    render_spacer()

    with st.container(border=True):
        st.markdown("**High-Risk Neighboring Accounts in 2-Hop Neighborhood**")
        if hr_nodes:
            shown = hr_nodes[:MAX_HIGH_RISK_BADGES]
            overflow = len(hr_nodes) - len(shown)
            badges_html = " ".join(
                f'<span class="risk-pill risk-high" style="margin: 2px 4px 2px 0;">{html.escape(str(node))}</span>'
                for node in shown
            )
            if overflow > 0:
                badges_html += (
                    f' <span class="risk-pill badge-offline" style="margin: 2px 4px 2px 0;">+{overflow} more</span>'
                )
            st.markdown(badges_html, unsafe_allow_html=True)
        else:
            st.caption("No HIGH-risk peer nodes detected within 2 hops of this subject account.")

    render_spacer()

    with st.container(border=True):
        physics_note = "Interactive physics ON" if enable_physics else "Stabilized (physics auto-paused)"
        pruned_note = (
            f"Showing top {graph_stats.get('rendered_nodes')} prioritized nodes out of {graph_stats.get('num_nodes')}."
            if graph_stats.get("pruned")
            else f"Showing all {graph_stats.get('rendered_nodes', 0)} nodes."
        )
        st.caption(
            f"💡 **Graph Legend:** Red = HIGH · Violet = MEDIUM · Blue = LOW · {pruned_note} · {physics_note}"
        )
        html_content = graph_stats.get("html_content", "")
        if html_content:
            st.iframe(html_content, height=520, width="stretch")
        else:
            st.warning("PyVis graph HTML payload was empty for the selected account.")

    return graph_stats


# ---------------------------------------------------------------------------
# Tab 4: FIU-IND STR / SAR Narrative Generator
# ---------------------------------------------------------------------------
def render_sar_workbench(
    analysis: dict[str, Any],
    graph_stats: dict[str, Any],
    mtime: float,
    compact_inr: bool,
) -> None:
    """Render PMLA 2002 / RBI KYC Suspicious Transaction Report generator and export tools."""
    acc_id = str(analysis.get("account_id", "UNKNOWN"))
    risk_tier = str(analysis.get("risk_tier", "LOW")).upper()
    active_key, key_fp = _active_api_key()
    auto_generate = bool(st.session_state.get("cfg_sar_auto_generate", True))

    render_section_header(
        f"FIU-IND Suspicious Transaction Report (STR / SAR) — {acc_id}",
        f"Automated PMLA 2002 & RBI Master Direction on KYC synthesis ({GEMINI_MODEL_NAME})",
        accent_color="#6D28D9",
    )

    c_left, c_right = st.columns([2.2, 1.0])
    with c_left:
        st.markdown(
            f"**Subject Entity:** `{html.escape(acc_id)}` ({html.escape(classify_account_segment(acc_id))}) "
            f"&nbsp;|&nbsp; **Risk Tier:** {risk_badge_html(risk_tier)} "
            f"&nbsp;|&nbsp; {gemini_status_badge_html(active_key is not None)}",
            unsafe_allow_html=True,
        )
    with c_right:
        generate_clicked = st.button(
            "⚡ Generate / Refresh STR Narrative",
            type="primary",
            width="stretch",
            key="btn_generate_sar",
        )

    sar_store: dict[str, str] = st.session_state["sar_cache_by_account"]
    nonces: dict[str, int] = st.session_state["sar_refresh_nonce"]
    session_cache_key = f"{acc_id}:{key_fp}"

    if generate_clicked:
        nonces[acc_id] = nonces.get(acc_id, 0) + 1
        with st.spinner("Synthesizing evidence-tiered PMLA 2002 compliance narrative..."):
            sar_store[session_cache_key] = get_cached_sar(
                acc_id,
                mtime,
                key_fp,
                nonces[acc_id],
                analysis,
                graph_stats,
                _api_key=active_key,
            )
    elif session_cache_key not in sar_store and auto_generate:
        with st.spinner("Synthesizing evidence-tiered PMLA 2002 compliance narrative..."):
            sar_store[session_cache_key] = get_cached_sar(
                acc_id,
                mtime,
                key_fp,
                nonces.get(acc_id, 0),
                analysis,
                graph_stats,
                _api_key=active_key,
            )

    sar_text = sar_store.get(session_cache_key, "")
    render_spacer()

    if not sar_text:
        st.info(
            "Manual SAR Synthesis Mode is enabled in Settings. Click **Generate / Refresh STR Narrative** above to synthesize the report for this account."
        )
        return

    with st.container(border=True):
        st.subheader("Generated Regulatory Filing Narrative")
        escaped_paragraphs = "<br><br>".join(
            html.escape(p.strip()) for p in sar_text.split("\n\n") if p.strip()
        )
        st.markdown(f'<div class="sar-paper">{escaped_paragraphs}</div>', unsafe_allow_html=True)

    render_spacer()

    with st.container(border=True):
        st.subheader("Compliance Officer Review & Export")
        edited_sar = st.text_area(
            "Edit or annotate STR narrative prior to FIU-IND FINnet 2.0 submission:",
            value=sar_text,
            height=220,
            key=f"sar_editor_{acc_id}",
        )

        exp1, exp2 = st.columns(2)
        with exp1:
            st.download_button(
                label="Download STR Filing (.txt)",
                data=edited_sar,
                file_name=f"FIU_IND_STR_{acc_id}.txt",
                mime="text/plain",
                width="stretch",
            )
        with exp2:
            md_report = (
                f"# FIU-IND Suspicious Transaction Report (STR)\n\n"
                f"- **Subject Account:** `{acc_id}`\n"
                f"- **Institution:** {extract_bank_code(acc_id)}\n"
                f"- **Risk Tier:** {risk_tier} ({float(analysis.get('risk_score', 0.0)):.2f}/100)\n"
                f"- **Total Inflow:** {format_inr(analysis.get('total_inflow', 0.0), compact=compact_inr)}\n"
                f"- **Total Outflow:** {format_inr(analysis.get('total_outflow', 0.0), compact=compact_inr)}\n"
                f"- **Pass-Through Ratio:** {float(analysis.get('pass_through_ratio', 0.0)):.2f}x\n"
                f"- **Detected Topology:** {graph_stats.get('topology', 'N/A')}\n\n"
                f"## Regulatory Narrative (PMLA 2002 / RBI KYC)\n\n"
                f"{edited_sar}\n"
            )
            st.download_button(
                label="Download Case Dossier (.md)",
                data=md_report,
                file_name=f"FINSIGHT_Case_{acc_id}.md",
                mime="text/markdown",
                width="stretch",
            )


# ---------------------------------------------------------------------------
# Tab 5: Workbench Settings & Runtime Governance
# ---------------------------------------------------------------------------
def _render_palette_swatches() -> None:
    """Render live 6-color FINSIGHT palette swatch preview."""
    items = "".join(
        f'<div class="finsight-swatch-item">'
        f'<span class="finsight-swatch-chip" style="background-color: {hex_code};"></span>'
        f'<div class="finsight-swatch-meta"><strong>{html.escape(name)}</strong><br><code>{html.escape(hex_code)}</code></div>'
        f'</div>'
        for name, hex_code in _PALETTE_SWATCHES
    )
    st.markdown(f'<div class="finsight-swatch-grid">{items}</div>', unsafe_allow_html=True)


def render_settings() -> None:
    """Render Dark/Light theme controls, in-memory Gemini key override, and performance settings."""
    render_section_header(
        "Workbench Settings & Runtime Controls",
        "Appearance theme, in-memory Gemini API key override, graph performance, and cache controls",
        accent_color="#4F46E5",
    )

    col_left, col_right = st.columns(2)

    with col_left:
        with st.container(border=True):
            st.subheader("Appearance")
            st.toggle(
                "Dark Mode (Navy Blue #0A1931 / Light Mode #FFFFFF)",
                value=bool(st.session_state["cfg_dark_mode"]),
                key="w_dark_mode",
                on_change=_on_dark_mode_change,
            )
            mode_label = (
                "Navy Blue Dark Mode (#0A1931)"
                if st.session_state["cfg_dark_mode"]
                else "White Light Mode (#FFFFFF)"
            )
            st.caption(f"Active canvas: **{mode_label}** · Live 6-Color FINSIGHT Palette:")
            _render_palette_swatches()

        render_spacer()

        with st.container(border=True):
            st.subheader("Gemini API Key Override")
            active_key, _ = _active_api_key()
            st.markdown(
                f"**Active Synthesizer Engine:** {gemini_status_badge_html(active_key is not None)}",
                unsafe_allow_html=True,
            )
            st.caption(
                "Keys entered here update `os.environ['GEMINI_API_KEY']` strictly in process memory and are never written to disk or logged."
            )
            st.session_state.setdefault("w_gemini_api_key", "")
            entered_key = st.text_input(
                "Gemini API Key (In-Memory Override)",
                type="password",
                key="w_gemini_api_key",
                placeholder="Paste key for Live Gemini 3.8 Flash synthesis",
            )
            b1, b2 = st.columns(2)
            with b1:
                if st.button("Apply API Key", type="primary", width="stretch", key="btn_apply_api_key"):
                    cleaned = entered_key.strip()
                    if cleaned:
                        os.environ["GEMINI_API_KEY"] = cleaned
                        st.session_state["sar_cache_by_account"] = {}
                        st.session_state["_clear_api_input"] = True
                        st.toast("Gemini API key applied in process memory.", icon="🔐")
                        st.rerun()
                    else:
                        st.warning("Enter a non-empty API key before applying.")
            with b2:
                if st.button("Clear Key", width="stretch", key="btn_clear_api_key"):
                    os.environ.pop("GEMINI_API_KEY", None)
                    st.session_state["sar_cache_by_account"] = {}
                    st.session_state["_clear_api_input"] = True
                    st.toast("In-memory Gemini API key cleared; using Offline Fallback.", icon="🧹")
                    st.rerun()

    with col_right:
        with st.container(border=True):
            st.subheader("Performance & Investigation Controls")
            st.slider(
                "Max Rendered Graph Nodes",
                min_value=25,
                max_value=150,
                value=int(st.session_state["cfg_max_graph_nodes"]),
                step=5,
                key="w_max_graph_nodes",
                on_change=_on_max_nodes_change,
                help="Caps visual PyVis nodes on super-hubs while preserving full 2-hop topology statistics.",
            )
            st.toggle(
                "Interactive Graph Physics",
                value=bool(st.session_state["cfg_enable_graph_physics"]),
                key="w_enable_graph_physics",
                on_change=_on_physics_change,
                help="When Off (recommended), Barnes-Hut physics pauses automatically after initial stabilization.",
            )

            currency_options = [CURRENCY_LABELS["compact"], CURRENCY_LABELS["exact"]]
            current_currency_label = CURRENCY_LABELS[st.session_state["cfg_currency_mode"]]
            st.radio(
                "Currency Display Precision",
                options=currency_options,
                index=currency_options.index(current_currency_label),
                key="w_currency_mode",
                on_change=_on_currency_change,
            )

            sar_options = [SAR_MODE_LABELS[True], SAR_MODE_LABELS[False]]
            current_sar_label = SAR_MODE_LABELS[bool(st.session_state["cfg_sar_auto_generate"])]
            st.radio(
                "SAR Synthesis Mode",
                options=sar_options,
                index=sar_options.index(current_sar_label),
                key="w_sar_mode",
                on_change=_on_sar_mode_change,
            )

            st.divider()
            if st.button("Clear In-Memory Cache", width="stretch", key="btn_clear_cache"):
                st.cache_data.clear()
                st.session_state["sar_cache_by_account"] = {}
                st.session_state["sar_refresh_nonce"] = {}
                st.success("All Streamlit in-memory data caches and SAR session caches cleared.")


# ---------------------------------------------------------------------------
# Main Application Entrypoint
# ---------------------------------------------------------------------------
def main() -> None:
    mtime = get_scored_mtime()
    try:
        tx_df = get_cached_scored_data(mtime)
    except Exception as exc:
        st.error(f"Unable to load scored AML dataset: {exc}")
        st.stop()

    if tx_df is None or tx_df.empty:
        st.warning("Scored dataset (`data/scored_bank_data.csv`) is empty. Run `src/ml_engine.py` first.")
        st.stop()

    acct_df = get_account_summary_df(tx_df, mtime)
    presets = get_dynamic_presets(acct_df)
    default_account = next(iter(presets.keys()), "SAV_4405_SBI")

    _init_session_state(default_account)
    _apply_pending_state()

    dark_mode = bool(st.session_state["cfg_dark_mode"])
    inject_custom_css(dark_mode)

    active_nav = render_sidebar(presets, dark_mode)

    st.markdown(
        """
        <div class="finsight-banner">
            <div>
                <div class="finsight-title">FINSIGHT · MULE ACCOUNT DETECTION WORKBENCH</div>
                <div class="finsight-subtitle">
                    FIU-IND Anti-Money Laundering Surveillance · PMLA 2002 &amp; RBI KYC Compliance Engine
                </div>
            </div>
            <div style="text-align: right;">
                <span class="risk-pill badge-calibrated">INR (₹) CALIBRATED</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    all_accounts = acct_df["Account_ID"].tolist()
    current_acc = st.session_state["selected_account"]
    if current_acc not in all_accounts and all_accounts:
        current_acc = all_accounts[0]
        st.session_state["selected_account"] = current_acc
    if all_accounts and st.session_state.get("global_account_selector") not in all_accounts:
        st.session_state["global_account_selector"] = current_acc

    sel_col1, sel_col2, sel_col3 = st.columns([2.2, 1.3, 1.0])
    with sel_col1:
        st.selectbox(
            "Active Subject Account ID (SAV / CUR / CORP)",
            options=all_accounts,
            key="global_account_selector",
            on_change=_sync_selected_account,
        )

    active_account = st.session_state["selected_account"]
    analysis = get_cached_analysis(active_account, mtime, tx_df)

    with sel_col2:
        st.markdown(
            f"<div style='padding-top: 1.65rem;'>"
            f"<strong>Segment:</strong> {html.escape(classify_account_segment(active_account))}"
            f"</div>",
            unsafe_allow_html=True,
        )
    with sel_col3:
        st.markdown(
            f"<div style='padding-top: 1.55rem; text-align: right;'>"
            f"{risk_badge_html(analysis.get('risk_tier', 'LOW'))}"
            f"</div>",
            unsafe_allow_html=True,
        )

    render_spacer()

    compact_inr = st.session_state["cfg_currency_mode"] == "compact"
    max_nodes = int(st.session_state["cfg_max_graph_nodes"])
    enable_physics = bool(st.session_state["cfg_enable_graph_physics"])

    # Lazy tab execution: 2-hop graph runs only on graph/SAR tabs
    if active_nav == "Executive Triage":
        render_executive_triage(acct_df, compact_inr)
    elif active_nav == "Account Forensics":
        render_account_forensics(analysis, compact_inr)
    elif active_nav == "2-Hop Topology":
        render_graph_topology(active_account, tx_df, mtime, max_nodes, enable_physics, dark_mode)
    elif active_nav == "FIU-IND STR/SAR":
        graph_stats = get_cached_subgraph(
            active_account, mtime, max_nodes, enable_physics, dark_mode, tx_df
        )
        render_sar_workbench(analysis, graph_stats, mtime, compact_inr)
    elif active_nav == "Settings":
        render_settings()


if __name__ == "__main__":
    main()
