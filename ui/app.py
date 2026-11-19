"""FINSIGHT: Mule Account Detection & FIU-IND Compliance Workbench (single-page Streamlit dashboard).

Launch from the project root:  streamlit run ui/app.py
"""
from __future__ import annotations

import base64
import hashlib
import html
import os
from pathlib import Path
import sys
from typing import TYPE_CHECKING, Any

from dotenv import load_dotenv
import numpy as np
import pandas as pd
import streamlit as st

if TYPE_CHECKING:
    import plotly.graph_objects as go

# Ensure project root is on sys.path so `src.*` imports resolve reliably
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ml_engine import analyze_account, assign_risk_tier, get_scored_mtime, load_scored_data
from src.sar_generator import MODEL_NAME as GEMINI_MODEL_NAME

LOGO_PATH = PROJECT_ROOT / "assets" / "finsight_logo.jpeg"
NAV_OPTIONS = [
    "Executive Triage",
    "Account Forensics",
    "2-Hop Topology",
    "FIU-IND STR/SAR",
    "Settings",
]
CURRENCY_LABELS = {
    "compact": "Compact Lakhs/Crores (₹12.40 L)",
    "exact": "Exact INR Grouping (₹12,40,000.00)",
}
SAR_MODE_LABELS = {
    True: "Auto-Generate on Tab Open",
    False: "Manual Click Only",
}
MOTION_MODE_LABELS = {
    True: "Full Motion (Idle + Reactive)",
    False: "Reduced Motion",
}
GRAPH_LAYOUT_LABELS = {
    "force": "Force-Directed Cluster",
    "hierarchical": "Hierarchical Flow (L→R)",
}
TIER_CHART_COLORS = {
    "HIGH": "#EF4444",
    "MEDIUM": "#F59E0B",
    "LOW": "#98E6C3",
    "FOCAL": "#4F46E5",
}
HIGH_RISK_THRESHOLD = 80.0
MEDIUM_RISK_THRESHOLD = 50.0
MAX_HIGH_RISK_BADGES = 30
PRIORITY_SELECTOR_LIMIT = 250
_KPI_ACCENTS = {"#0047AB", "#4F46E5", "#6D28D9", "#98E6C3"}
_KPI_DELAYS = {0, 50, 100, 150}
_SECTION_ACCENTS = {"#0047AB", "#4F46E5", "#6D28D9"}
_ALLOWED_SPACER_HEIGHTS = {"0.5rem", "0.75rem", "1rem", "1.25rem"}

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
            "sidebar_bg": "#071226",
            "logo_frame_bg": "transparent",
            "logo_frame_pad": "0px",
            "text": "#FFFFFF",
            "muted": "#CBD5E1",
            "border": "1px solid rgba(152, 230, 195, 0.22)",
            "border_color": "rgba(152, 230, 195, 0.22)",
            "sidebar_border": "1px solid rgba(152, 230, 195, 0.22)",
            "specular_top": "rgba(152, 230, 195, 0.22)",
            "elevation_shadow": "0 12px 32px -6px rgba(0, 0, 0, 0.62), 0 4px 14px -2px rgba(79, 70, 229, 0.22)",
            "hover_shadow": "0 16px 36px -6px rgba(0, 0, 0, 0.72), 0 0 18px rgba(79, 70, 229, 0.42)",
            "kpi_bg": "#0E2240",
            "kpi_border": "1px solid rgba(152, 230, 195, 0.22)",
            "kpi_shadow": "0 12px 32px -6px rgba(0, 0, 0, 0.62), 0 4px 14px -2px rgba(79, 70, 229, 0.22)",
            "input_bg": "#0E2240",
            "input_border": "rgba(79, 70, 229, 0.45)",
            "primary_btn_border": "1px solid #4F46E5",
            "low_bg": "#98E6C3",
            "low_fg": "#0A1931",
            "low_border": "#0A1931",
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
            "sar_border": "1px solid rgba(152, 230, 195, 0.22)",
            "nav_icon": "#98E6C3",
            "nav_text": "#FFFFFF",
            "menu_title": "#98E6C3",
            "scroll_track": "#071226",
            "header_bg": "rgba(10, 25, 49, 0.95)",
            "listbox_hover": "#142B54",
            "toggle_off_bg": "rgba(255, 255, 255, 0.18)",
            "toggle_off_border": "rgba(79, 70, 229, 0.45)",
            "gdg_vars": (
                "--gdg-bg-cell: #0E2240; "
                "--gdg-bg-cell-medium: #0A1931; "
                "--gdg-bg-header: #071226; "
                "--gdg-bg-header-has-focus: #142B54; "
                "--gdg-text-dark: #FFFFFF; "
                "--gdg-text-medium: #CBD5E1; "
                "--gdg-text-header: #FFFFFF; "
                "--gdg-border-color: rgba(152, 230, 195, 0.22);"
            ),
            "orb_opacity": "0.16",
            "card_hover_top": "#98E6C3",
            "sheen_grad": "linear-gradient(115deg, rgba(255,255,255,0) 0%, rgba(152,230,195,0.14) 48%, rgba(255,255,255,0) 100%)",
            "nav_card_bg": "#0E2240",
            "nav_card_border": "1px solid rgba(152, 230, 195, 0.22)",
            "nav_card_shadow": "0 8px 24px rgba(6, 13, 31, 0.45)",
            "nav_title_border": "1px solid rgba(152, 230, 195, 0.22)",
            "nav_pill_hover": "#142B54",
            "nav_active_border": "1px solid #4F46E5",
            "nav_active_shadow": "0 4px 12px rgba(0, 71, 171, 0.35)",
            "table_header_bg": "#071226",
            "table_row_bg": "#0E2240",
            "table_row_alt_bg": "#0A1931",
            "table_border": "rgba(152, 230, 195, 0.22)",
        }
    return {
        "canvas": "#F6F8FC",
        "surface": "#FFFFFF",
        "sidebar_bg": "#FFFFFF",
        "logo_frame_bg": "#060D1F",
        "logo_frame_pad": "6px",
        "text": "#0A1931",
        "muted": "#334155",
        "border": "1.5px solid #0A1931",
        "border_color": "#0A1931",
        "sidebar_border": "1.5px solid #0A1931",
        "specular_top": "#0A1931",
        "elevation_shadow": "0 3px 0 rgba(10, 25, 49, 0.12), 0 8px 20px rgba(10, 25, 49, 0.06)",
        "hover_shadow": "0 5px 0 rgba(10, 25, 49, 0.16), 0 12px 26px rgba(10, 25, 49, 0.12)",
        "kpi_bg": "#FFFFFF",
        "kpi_border": "1.5px solid #0A1931",
        "kpi_shadow": "0 3px 0 rgba(10, 25, 49, 0.12), 0 8px 20px rgba(10, 25, 49, 0.06)",
        "input_bg": "#FFFFFF",
        "input_border": "rgba(10, 25, 49, 0.75)",
        "primary_btn_border": "1.5px solid #0A1931",
        "low_bg": "#98E6C3",
        "low_fg": "#0A1931",
        "low_border": "#0A1931",
        "med_bg": "rgba(245, 158, 11, 0.18)",
        "med_fg": "#92400E",
        "med_border": "rgba(217, 119, 6, 0.65)",
        "high_bg": "rgba(239, 68, 68, 0.14)",
        "high_fg": "#B91C1C",
        "high_border": "rgba(220, 38, 38, 0.65)",
        "offline_bg": "rgba(109, 40, 217, 0.12)",
        "offline_fg": "#6D28D9",
        "offline_border": "#6D28D9",
        "sar_bg": "#FFFFFF",
        "sar_border": "1.5px solid #0A1931",
        "nav_icon": "#0047AB",
        "nav_text": "#0A1931",
        "menu_title": "#0A1931",
        "scroll_track": "#F6F8FC",
        "header_bg": "rgba(246, 248, 252, 0.96)",
        "listbox_hover": "#F1F5F9",
        "toggle_off_bg": "#E2E8F0",
        "toggle_off_border": "rgba(10, 25, 49, 0.55)",
        "gdg_vars": (
            "--gdg-bg-cell: #FFFFFF; "
            "--gdg-bg-cell-medium: #F1F5F9; "
            "--gdg-bg-header: #0A1931; "
            "--gdg-bg-header-has-focus: #142B54; "
            "--gdg-text-dark: #0A1931; "
            "--gdg-text-medium: #334155; "
            "--gdg-text-header: #FFFFFF; "
            "--gdg-border-color: rgba(10, 25, 49, 0.22);"
        ),
        "orb_opacity": "0.07",
        "card_hover_top": "#4F46E5",
        "sheen_grad": "linear-gradient(115deg, rgba(255,255,255,0) 0%, rgba(79,70,229,0.10) 48%, rgba(255,255,255,0) 100%)",
        "nav_card_bg": "#FFFFFF",
        "nav_card_border": "1.5px solid #0A1931",
        "nav_card_shadow": "0 3px 0 rgba(10, 25, 49, 0.12), 0 8px 20px rgba(10, 25, 49, 0.06)",
        "nav_title_border": "1.5px solid rgba(10, 25, 49, 0.22)",
        "nav_pill_hover": "#F1F5F9",
        "nav_active_border": "1.5px solid #0A1931",
        "nav_active_shadow": "0 3px 0 rgba(10, 25, 49, 0.18), 0 4px 12px rgba(0, 71, 171, 0.25)",
        "table_header_bg": "#0A1931",
        "table_row_bg": "#FFFFFF",
        "table_row_alt_bg": "#F1F5F9",
        "table_border": "rgba(10, 25, 49, 0.22)",
    }


def inject_custom_css(dark_mode: bool, full_motion: bool = True) -> None:
    """Inject FINSIGHT 6-color Dark/Light theme CSS and ambient mesh in separate blocks."""
    p = _palette(dark_mode)
    reduced_motion_override = (
        """
        .finsight-ambient-mesh,
        .finsight-banner::after,
        .live-beacon::after,
        .finsight-kpi-card::before,
        .sar-paper::before {
            display: none !important;
            animation: none !important;
        }
        *, *::before, *::after {
            animation-duration: 0.001ms !important;
            animation-iteration-count: 1 !important;
            transition-duration: 0.001ms !important;
        }
        """
        if not full_motion
        else ""
    ).strip()
    css_markup = f"""<style>
        @keyframes ambientFloat {{
            0% {{
                transform: translate3d(0px, 0px, 0) scale(1);
            }}
            50% {{
                transform: translate3d(28px, -22px, 0) scale(1.06);
            }}
            100% {{
                transform: translate3d(-20px, 18px, 0) scale(0.96);
            }}
        }}
        @keyframes bannerSheen {{
            0%, 15% {{
                transform: translateX(-120%) skewX(-20deg);
                opacity: 0;
            }}
            35% {{
                opacity: 1;
            }}
            65%, 100% {{
                transform: translateX(260%) skewX(-20deg);
                opacity: 0;
            }}
        }}
        @keyframes livePulse {{
            0% {{
                transform: scale(1);
                opacity: 0.85;
            }}
            75%, 100% {{
                transform: scale(2.2);
                opacity: 0;
            }}
        }}
        @keyframes logoGlow {{
            0% {{
                filter: drop-shadow(0 0 4px rgba(0, 71, 171, 0.25));
                opacity: 0.96;
            }}
            100% {{
                filter: drop-shadow(0 0 12px rgba(152, 230, 195, 0.42));
                opacity: 1;
            }}
        }}
        @font-face {{
            font-family: "Source Sans";
            font-display: swap;
        }}
        @font-face {{
            font-family: "Source Code Pro";
            font-display: swap;
        }}
        html, body, .stApp {{
            font-display: swap;
        }}
        @keyframes cardReveal {{
            from {{
                opacity: 0;
            }}
            to {{
                opacity: 1;
            }}
        }}
        @keyframes fadeSlideUp {{
            from {{
                opacity: 0;
            }}
            to {{
                opacity: 1;
            }}
        }}
        @keyframes pulseAlert {{
            0%, 100% {{
                box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.32), inset 0 0 8px rgba(239, 68, 68, 0.18);
            }}
            50% {{
                box-shadow: 0 0 12px 2px rgba(239, 68, 68, 0.45), inset 0 0 12px rgba(239, 68, 68, 0.28);
            }}
        }}
        ::-webkit-scrollbar {{
            width: 8px;
            height: 8px;
        }}
        ::-webkit-scrollbar-track {{
            background: {p["scroll_track"]};
        }}
        ::-webkit-scrollbar-thumb {{
            background: linear-gradient(180deg, #0047AB 0%, #4F46E5 100%);
            border-radius: 9999px;
        }}
        ::-webkit-scrollbar-thumb:hover {{
            background: #6D28D9;
        }}
        .stApp, body, p, div, span:not([data-testid="stIconMaterial"]):not(.material-symbols-rounded), h1, h2, h3, button:not([data-testid="stIconMaterial"]), input {{
            font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif !important;
        }}
        [data-testid="stIconMaterial"],
        span[data-testid="stIconMaterial"] {{
            font-family: "Material Symbols Rounded" !important;
            font-feature-settings: "liga" 1 !important;
            -webkit-font-feature-settings: "liga" 1 !important;
        }}
        code, pre, kbd, samp, .stCode {{
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace !important;
        }}
        .finsight-mono {{
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace !important;
            font-variant-numeric: tabular-nums;
            font-size: 0.86em;
            background-color: rgba(79, 70, 229, 0.14);
            padding: 0.1rem 0.34rem;
            border-radius: 5px;
        }}
        .stApp, [data-testid="stAppViewContainer"] {{
            background-color: {p["canvas"]};
            color: {p["text"]};
        }}
        html, body, .stApp, [data-testid="stAppViewContainer"], section[data-testid="stMain"] {{
            overflow-y: auto !important;
            height: auto !important;
            min-height: 100vh;
        }}
        header[data-testid="stHeader"] {{
            background: transparent !important;
        }}
        header[data-testid="stHeader"] button,
        header[data-testid="stHeader"] svg {{
            color: {p["text"]} !important;
            fill: {p["text"]} !important;
        }}
        [data-testid="stAppViewContainer"] > .main {{
            position: relative;
            z-index: 1;
        }}
        .finsight-ambient-mesh {{
            position: fixed;
            inset: 0;
            pointer-events: none;
            z-index: 0;
            overflow: hidden;
        }}
        .finsight-ambient-mesh .ambient-orb {{
            position: absolute;
            border-radius: 9999px;
            filter: blur(72px);
            opacity: {p["orb_opacity"]};
            pointer-events: none;
            will-change: transform;
            animation: ambientFloat 14s ease-in-out 1.5s infinite alternate;
        }}
        .finsight-ambient-mesh .orb-blue {{
            width: 420px;
            height: 420px;
            top: 6%;
            left: 18%;
            background: radial-gradient(circle, #0047AB 0%, rgba(79, 70, 229, 0) 72%);
        }}
        .finsight-ambient-mesh .orb-violet {{
            width: 460px;
            height: 460px;
            bottom: 4%;
            right: 8%;
            background: radial-gradient(circle, #6D28D9 0%, rgba(109, 40, 217, 0) 72%);
            animation-delay: 1.5s;
        }}
        [data-testid="stSidebar"], [data-testid="stSidebarContent"] {{
            background-color: {p["sidebar_bg"]} !important;
            color: {p["text"]};
        }}
        [data-testid="stSidebar"] {{
            border-right: {p["sidebar_border"]} !important;
        }}
        .finsight-sidebar-logo {{
            background-color: {p["logo_frame_bg"]};
            padding: {p["logo_frame_pad"]};
            border-radius: 10px;
            margin-bottom: 0.35rem;
            min-height: 92px;
            box-sizing: border-box;
            will-change: filter, opacity;
            animation: logoGlow 5s ease-in-out 1.5s infinite alternate;
        }}
        .finsight-sidebar-logo img {{
            width: 100%;
            max-width: 170px;
            height: auto;
            aspect-ratio: 170 / 92;
            object-fit: contain;
            border-radius: 8px;
            display: block;
            margin: 0 auto;
        }}
        [data-testid="stSidebar"] [data-testid="stRadio"] {{
            background-color: {p["nav_card_bg"]};
            border: {p["nav_card_border"]};
            border-radius: 12px;
            padding: 0.65rem 0.65rem 0.55rem 0.65rem;
            box-shadow: {p["nav_card_shadow"]};
        }}
        [data-testid="stSidebar"] [data-testid="stRadio"] [data-testid="stWidgetLabel"] {{
            border-bottom: {p["nav_title_border"]};
            padding-bottom: 0.45rem;
            margin-bottom: 0.45rem;
            width: 100%;
        }}
        [data-testid="stSidebar"] [data-testid="stRadio"] [data-testid="stWidgetLabel"] p {{
            font-size: 11px !important;
            font-weight: 700 !important;
            letter-spacing: 0.08em !important;
            text-transform: uppercase !important;
            color: {p["menu_title"]} !important;
            margin: 0 !important;
        }}
        [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] {{
            gap: 4px !important;
        }}
        [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label {{
            width: 100%;
            margin: 2px 0 !important;
            padding: 0.55rem 0.75rem !important;
            border-radius: 8px !important;
            border: 1px solid transparent;
            background-color: transparent;
            color: {p["nav_text"]} !important;
            cursor: pointer;
            transition: background-color 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease;
        }}
        [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label > div:first-child {{
            display: none !important;
        }}
        [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label p {{
            font-size: 14px !important;
            font-weight: 500 !important;
            color: {p["nav_text"]} !important;
            margin: 0 !important;
        }}
        [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label:hover {{
            background-color: {p["nav_pill_hover"]} !important;
        }}
        [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) {{
            background-color: #0047AB !important;
            color: #FFFFFF !important;
            border: {p["nav_active_border"]} !important;
            font-weight: 600 !important;
            box-shadow: {p["nav_active_shadow"]} !important;
        }}
        [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) *,
        [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) p {{
            color: #FFFFFF !important;
            font-weight: 600 !important;
        }}
        .live-beacon {{
            display: inline-block;
            position: relative;
            width: 8px;
            height: 8px;
            border-radius: 9999px;
            background-color: #98E6C3;
            margin-right: 0.45rem;
            vertical-align: middle;
            pointer-events: none;
        }}
        .live-beacon::after {{
            content: "";
            position: absolute;
            inset: 0;
            border-radius: 9999px;
            background-color: #98E6C3;
            pointer-events: none;
            will-change: transform, opacity;
            animation: livePulse 2.2s ease-out 1.5s infinite;
        }}
        .telemetry-header {{
            display: flex;
            align-items: center;
            margin-bottom: 0.35rem;
            font-size: 0.92rem;
            color: {p["text"]};
        }}
        [data-testid="stWidgetLabel"] p,
        [data-testid="stWidgetLabel"] span,
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
            border: {p["border"]} !important;
            border-radius: 12px;
            box-shadow: {p["elevation_shadow"]};
            animation: cardReveal 0.32s cubic-bezier(0.22, 1, 0.36, 1) both;
            transition: transform 0.22s cubic-bezier(0.22, 1, 0.36, 1), box-shadow 0.22s ease, border-color 0.22s ease;
        }}
        [data-testid="stVerticalBlockBorderWrapper"]:hover {{
            transform: translateY(-4px) scale(1.008);
            border-color: #4F46E5 !important;
            border-top-color: {p["card_hover_top"]} !important;
            box-shadow: {p["hover_shadow"]};
        }}
        div[data-baseweb="select"] > div,
        [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
        [data-testid="stMultiSelect"] div[data-baseweb="select"] > div,
        [data-testid="stTextInput"] div[data-baseweb="input"] > div,
        [data-testid="stTextInput"] input,
        [data-testid="stTextArea"] textarea {{
            background-color: {p["input_bg"]} !important;
            color: {p["text"]} !important;
            border: 1.5px solid {p["input_border"]} !important;
            transition: border-color 0.18s ease, box-shadow 0.18s ease;
        }}
        div[data-baseweb="select"] > div *,
        [data-testid="stTextInput"] input::placeholder,
        [data-testid="stTextArea"] textarea::placeholder {{
            color: {p["text"]};
        }}
        [data-testid="stSelectbox"] div[data-baseweb="select"] > div:hover,
        [data-testid="stMultiSelect"] div[data-baseweb="select"] > div:hover,
        [data-testid="stTextInput"] div[data-baseweb="input"] > div:hover,
        [data-testid="stTextArea"] textarea:hover {{
            border-color: #4F46E5 !important;
        }}
        [data-testid="stSelectbox"] div[data-baseweb="select"]:focus-within > div,
        [data-testid="stMultiSelect"] div[data-baseweb="select"]:focus-within > div,
        [data-testid="stTextInput"] div[data-baseweb="input"]:focus-within,
        [data-testid="stTextArea"] textarea:focus {{
            border-color: #4F46E5 !important;
            box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.28), 0 0 12px rgba(0, 71, 171, 0.32) !important;
            outline: none !important;
        }}
        [data-testid="stSelectbox"] svg,
        [data-testid="stMultiSelect"] svg {{
            fill: {p["text"]} !important;
        }}
        [data-testid="stMultiSelect"] span[data-baseweb="tag"],
        [data-testid="stMultiSelect"] span[data-baseweb="tag"] * {{
            background-color: #0047AB !important;
            color: #FFFFFF !important;
            border-color: #4F46E5 !important;
        }}
        div[data-baseweb="popover"],
        div[data-baseweb="popover"] ul[role="listbox"],
        ul[role="listbox"],
        li[role="option"] {{
            background-color: {p["input_bg"]} !important;
            color: {p["text"]} !important;
        }}
        div[data-baseweb="popover"] ul[role="listbox"] {{
            border: 1.5px solid {p["input_border"]} !important;
            box-shadow: {p["elevation_shadow"]};
        }}
        li[role="option"]:hover,
        li[role="option"][aria-selected="true"] {{
            background-color: {p["listbox_hover"]} !important;
            color: {p["text"]} !important;
        }}
        [data-testid="stDataFrame"],
        [data-testid="stDataFrame"] * {{
            font-variant-numeric: tabular-nums;
        }}
        [data-testid="stDataFrame"] {{
            {p["gdg_vars"]}
            border: {p["border"]};
            border-radius: 10px;
            overflow: hidden;
            background-color: {p["input_bg"]};
        }}
        div[data-baseweb="checkbox"]:has(input[role="switch"]) > div:first-child {{
            background-color: {p["toggle_off_bg"]} !important;
            border: 1.5px solid {p["toggle_off_border"]} !important;
        }}
        div[data-baseweb="checkbox"]:has(input[role="switch"]:checked) > div:first-child {{
            background-color: #0047AB !important;
            border: 1.5px solid #0047AB !important;
        }}
        div[data-baseweb="checkbox"]:has(input[role="switch"]) > div:first-child > div {{
            background-color: #FFFFFF !important;
        }}
        .stButton > button,
        [data-testid="stDownloadButton"] > button {{
            transition: transform 0.20s cubic-bezier(0.22, 1, 0.36, 1), box-shadow 0.20s ease, border-color 0.20s ease, background-color 0.18s ease !important;
        }}
        .stButton > button[kind="primary"],
        button[kind="primary"],
        [data-testid="stBaseButton-primary"] {{
            background-color: #0047AB !important;
            color: #FFFFFF !important;
            border: {p["primary_btn_border"]} !important;
            box-shadow: {p["elevation_shadow"]};
        }}
        .stButton > button[kind="primary"] *,
        button[kind="primary"] *,
        [data-testid="stBaseButton-primary"] * {{
            color: #FFFFFF !important;
        }}
        .stButton > button[kind="primary"]:hover,
        button[kind="primary"]:hover,
        [data-testid="stBaseButton-primary"]:hover {{
            background-color: #0B5ED7 !important;
            color: #FFFFFF !important;
            transform: translateY(-2px);
            box-shadow: {p["hover_shadow"]} !important;
            border-color: #4F46E5 !important;
        }}
        .stButton > button[kind="secondary"],
        button[kind="secondary"],
        [data-testid="stBaseButton-secondary"],
        [data-testid="stDownloadButton"] > button {{
            background-color: {p["surface"]} !important;
            color: {p["text"]} !important;
            border: {p["border"]} !important;
            box-shadow: {p["elevation_shadow"]};
        }}
        .stButton > button[kind="secondary"] *,
        button[kind="secondary"] *,
        [data-testid="stBaseButton-secondary"] *,
        [data-testid="stDownloadButton"] > button * {{
            color: {p["text"]} !important;
        }}
        .stButton > button[kind="secondary"]:hover,
        button[kind="secondary"]:hover,
        [data-testid="stBaseButton-secondary"]:hover,
        [data-testid="stDownloadButton"] > button:hover {{
            transform: translateY(-2px);
            border-color: #4F46E5 !important;
            box-shadow: {p["hover_shadow"]} !important;
        }}
        .stButton > button:active,
        button[kind="primary"]:active,
        button[kind="secondary"]:active,
        [data-testid="stBaseButton-primary"]:active,
        [data-testid="stBaseButton-secondary"]:active,
        [data-testid="stDownloadButton"] > button:active {{
            transform: translateY(1px) scale(0.985) !important;
        }}
        .finsight-banner {{
            position: relative;
            overflow: hidden;
            background: linear-gradient(135deg, #0A1931 0%, #0047AB 55%, #6D28D9 100%);
            border: 1px solid rgba(79, 70, 229, 0.55);
            border-top: 1px solid rgba(255, 255, 255, 0.18);
            border-radius: 12px;
            padding: 1.15rem 1.45rem;
            margin-bottom: 1.1rem;
            min-height: 108px;
            box-sizing: border-box;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: {p["elevation_shadow"]};
            animation: fadeSlideUp 0.30s cubic-bezier(0.22, 1, 0.36, 1) both;
        }}
        .finsight-banner::after {{
            content: "";
            position: absolute;
            top: 0;
            bottom: 0;
            left: 0;
            width: 38%;
            background: linear-gradient(90deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.13) 50%, rgba(255,255,255,0) 100%);
            pointer-events: none;
            will-change: transform, opacity;
            animation: bannerSheen 7s ease-in-out 1.5s infinite;
        }}
        .finsight-title,
        h1.finsight-title {{
            font-size: 2rem !important;
            line-height: 1.2 !important;
            font-weight: 800 !important;
            letter-spacing: 0.03em;
            color: #FFFFFF !important;
            margin: 0 !important;
            padding: 0 !important;
        }}
        .finsight-subtitle {{
            color: rgba(255, 255, 255, 0.88) !important;
            font-size: 0.86rem;
            margin-top: 0.22rem;
        }}
        .finsight-banner .badge-calibrated {{
            background: #98E6C3 !important;
            color: #0A1931 !important;
            border: 1px solid #0A1931 !important;
            box-shadow: 0 2px 10px rgba(10, 25, 49, 0.22);
        }}
        .finsight-banner .badge-calibrated .live-beacon,
        .finsight-banner .badge-calibrated .live-beacon::after {{
            background-color: #0A1931 !important;
        }}
        .finsight-section-header {{
            border-left: 3.5px solid #0047AB;
            padding: 0.25rem 0 0.25rem 0.9rem;
            margin: 0.2rem 0 0.9rem 0;
            min-height: 54px;
            box-sizing: border-box;
            animation: cardReveal 0.32s cubic-bezier(0.22, 1, 0.36, 1) both;
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
            position: relative;
            overflow: hidden;
            background-color: {p["kpi_bg"]};
            border: {p["kpi_border"]};
            border-top: 3.5px solid #0047AB;
            border-radius: 12px;
            padding: 0.95rem 1.1rem;
            min-height: 114px;
            box-sizing: border-box;
            height: 100%;
            box-shadow: {p["kpi_shadow"]};
            animation: cardReveal 0.32s cubic-bezier(0.22, 1, 0.36, 1) both;
            transition: transform 0.22s cubic-bezier(0.22, 1, 0.36, 1), box-shadow 0.22s ease, border-color 0.22s ease;
        }}
        .finsight-kpi-card::before,
        .sar-paper::before {{
            content: "";
            position: absolute;
            top: 0;
            bottom: 0;
            left: 0;
            width: 45%;
            background: {p["sheen_grad"]};
            transform: translateX(-140%) skewX(-22deg);
            transition: transform 0.55s cubic-bezier(0.22, 1, 0.36, 1);
            pointer-events: none;
        }}
        .finsight-kpi-card:hover {{
            transform: translateY(-4px) scale(1.008);
            box-shadow: {p["hover_shadow"]};
            border-color: #4F46E5;
            border-top-color: {p["card_hover_top"]} !important;
        }}
        .finsight-kpi-card:hover::before,
        .sar-paper:hover::before {{
            transform: translateX(240%) skewX(-22deg);
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
            font-variant-numeric: tabular-nums;
            margin: 0.25rem 0 0.2rem 0;
            line-height: 1.2;
        }}
        .finsight-kpi-desc {{
            color: {p["muted"]};
            font-size: 0.78rem;
            font-variant-numeric: tabular-nums;
        }}
        code {{
            font-variant-numeric: tabular-nums;
        }}
        .risk-pill {{
            display: inline-block;
            padding: 0.24rem 0.72rem;
            border-radius: 9999px;
            font-size: 0.76rem;
            font-weight: 700;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            font-variant-numeric: tabular-nums;
        }}
        .risk-high {{
            background: {p["high_bg"]};
            color: {p["high_fg"]};
            border: 1px solid {p["high_border"]};
            animation: pulseAlert 2.4s ease-in-out infinite;
        }}
        .risk-medium {{
            background: {p["med_bg"]};
            color: {p["med_fg"]};
            border: 1px solid {p["med_border"]};
        }}
        .risk-low, .badge-calibrated, .badge-live {{
            background: {p["low_bg"]} !important;
            color: {p["low_fg"]} !important;
            border: 1px solid {p["low_border"]} !important;
            box-shadow: 0 2px 8px rgba(10, 25, 49, 0.14);
        }}
        .badge-offline {{
            background: {p["offline_bg"]};
            color: {p["offline_fg"]};
            border: 1px solid {p["offline_border"]};
        }}
        .sar-paper {{
            position: relative;
            overflow: hidden;
            background-color: {p["sar_bg"]};
            border: {p["sar_border"]};
            border-left: 3.5px solid #6D28D9;
            border-radius: 8px;
            padding: 1.25rem 1.4rem;
            font-size: 0.95rem;
            line-height: 1.68;
            font-variant-numeric: tabular-nums;
            color: {p["text"]};
            box-shadow: {p["elevation_shadow"]};
            animation: cardReveal 0.32s cubic-bezier(0.22, 1, 0.36, 1) both;
            transition: transform 0.22s cubic-bezier(0.22, 1, 0.36, 1), box-shadow 0.22s ease, border-color 0.22s ease;
        }}
        .sar-paper:hover {{
            transform: translateY(-4px) scale(1.008);
            border-color: #4F46E5;
            border-top-color: {p["card_hover_top"]};
            box-shadow: {p["hover_shadow"]};
        }}
        .finsight-ledger-wrap {{
            width: 100%;
            min-height: 360px;
            max-height: 360px;
            box-sizing: border-box;
            overflow-x: auto;
            overflow-y: auto;
            border: {p["border"]};
            border-radius: 10px;
            background-color: {p["table_row_bg"]};
            box-shadow: {p["elevation_shadow"]};
            margin-bottom: 0.45rem;
        }}
        .finsight-ledger-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.84rem;
            font-variant-numeric: tabular-nums;
            color: {p["text"]};
        }}
        .finsight-ledger-table thead th {{
            position: sticky;
            top: 0;
            z-index: 2;
            background-color: {p["table_header_bg"]};
            color: #FFFFFF !important;
            font-weight: 700;
            text-align: left;
            padding: 0.62rem 0.78rem;
            border-bottom: 1.5px solid #4F46E5;
            letter-spacing: 0.03em;
            white-space: nowrap;
        }}
        .finsight-ledger-table tbody tr {{
            background-color: {p["table_row_bg"]};
            border-bottom: 1px solid {p["table_border"]};
            transition: background-color 0.14s ease;
        }}
        .finsight-ledger-table tbody tr:nth-child(even) {{
            background-color: {p["table_row_alt_bg"]};
        }}
        .finsight-ledger-table tbody tr:hover {{
            background-color: {p["listbox_hover"]};
        }}
        .finsight-ledger-table td {{
            padding: 0.52rem 0.78rem;
            white-space: nowrap;
            font-variant-numeric: tabular-nums;
            color: {p["text"]};
        }}
        .finsight-ledger-table td.num-col,
        .finsight-ledger-table th.num-col {{
            text-align: right;
        }}
        hr {{
            border-color: {p["border_color"]};
        }}
        @media (prefers-reduced-motion: reduce) {{
            .finsight-ambient-mesh,
            .finsight-banner::after,
            .live-beacon::after,
            .finsight-kpi-card::before,
            .sar-paper::before {{
                display: none !important;
                animation: none !important;
            }}
            *, *::before, *::after {{
                animation-duration: 0.001ms !important;
                animation-iteration-count: 1 !important;
                transition-duration: 0.001ms !important;
            }}
        }}
        {reduced_motion_override}
</style>"""
    st.markdown(css_markup, unsafe_allow_html=True)
    st.markdown(
        '<div class="finsight-ambient-mesh" aria-hidden="true">'
        '<div class="ambient-orb orb-blue"></div>'
        '<div class="ambient-orb orb-violet"></div>'
        "</div>",
        unsafe_allow_html=True,
    )


def render_hero_banner() -> None:
    """Render the top hero command banner cleanly without duplicate style tags."""
    banner_html = (
        '<div class="finsight-banner">'
        "<div>"
        '<h1 class="finsight-title" style="font-size: 2rem; line-height: 1.2; font-weight: 800; margin: 0; padding: 0;">'
        "FINSIGHT · MULE ACCOUNT DETECTION WORKBENCH</h1>"
        '<div class="finsight-subtitle">'
        "FIU-IND Anti-Money Laundering Surveillance · PMLA 2002 &amp; RBI KYC Compliance Engine"
        "</div>"
        "</div>"
        '<div style="text-align: right;">'
        '<span class="risk-pill badge-calibrated"><span class="live-beacon"></span>INR (₹) CALIBRATED</span>'
        "</div>"
        "</div>"
    )
    st.markdown(banner_html, unsafe_allow_html=True)


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
    title: str,
    value: str,
    subtitle: str,
    accent_color: str = "#0047AB",
    delay_ms: int = 0,
) -> None:
    """Render an XSS-safe native HTML KPI card accented from the 6-color FINSIGHT palette."""
    safe_accent = accent_color if accent_color in _KPI_ACCENTS else "#0047AB"
    safe_delay = delay_ms if delay_ms in _KPI_DELAYS else 0
    st.markdown(
        f"""
        <div class="finsight-kpi-card" style="border-top-color: {safe_accent}; animation-delay: {safe_delay}ms;">
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
def load_logo_data_uri(logo_mtime: float) -> str | None:
    """Read and cache FINSIGHT logo as an in-memory base64 data URI."""
    if logo_mtime <= 0.0 or not LOGO_PATH.exists():
        return None
    encoded = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _build_priority_selector_options(
    acct_df: pd.DataFrame,
    presets: dict[str, dict[str, Any]],
    active_account: str,
    limit: int = PRIORITY_SELECTOR_LIMIT,
) -> list[str]:
    """Return Top 250 priority accounts + presets + active account to avoid 18k-item DOM serialization."""
    top_ids = acct_df["Account_ID"].head(limit).astype(str).tolist()
    seen = set(top_ids)
    for preset_id in presets:
        pid = str(preset_id)
        if pid not in seen:
            top_ids.append(pid)
            seen.add(pid)
    act = str(active_account or "").strip()
    if act and act not in seen:
        top_ids.append(act)
    return top_ids


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
    layout_mode: str,
    _tx_df: pd.DataFrame,
) -> dict[str, Any]:
    """Run and cache 2-hop topology extraction keyed by account, mtime, layout, and visual controls."""
    from src.graph_engine import build_account_subgraph

    return build_account_subgraph(
        account_id,
        _tx_df,
        save_html=False,
        cache_key=mtime,
        max_nodes=max_nodes,
        enable_physics=enable_physics,
        dark_mode=dark_mode,
        layout_mode=layout_mode,
    )


@st.cache_data(show_spinner=False)
def get_cached_timeline(account_id: str, mtime: float, _tx_df: pd.DataFrame) -> list[dict]:
    """Return ordered inbound/outbound timeline events for single-account Plotly charts."""
    from src.graph_engine import get_account_timeline_data

    return get_account_timeline_data(account_id, _tx_df, cache_key=mtime)


def build_fund_flow_sankey(sankey_data: dict[str, Any], dark_mode: bool) -> go.Figure:
    """Build interactive Plotly Sankey diagram showing inbound -> focal -> outbound INR flows."""
    import plotly.graph_objects as go

    text_color = "#FFFFFF" if dark_mode else "#0A1931"
    focal_acc = str(sankey_data.get("focal_account", "SUBJECT"))
    inbound = sankey_data.get("inbound") or []
    outbound = sankey_data.get("outbound") or []

    labels: list[str] = []
    node_colors: list[str] = []
    sources: list[int] = []
    targets: list[int] = []
    values: list[float] = []
    link_colors: list[str] = []
    link_customdata: list[str] = []

    link_rgba = {
        "HIGH": "rgba(239, 68, 68, 0.42)",
        "MEDIUM": "rgba(245, 158, 11, 0.36)",
        "LOW": "rgba(152, 230, 195, 0.38)",
    }

    for item in inbound:
        tier = str(item.get("risk_tier", "LOW")).upper()
        labels.append(f"IN · {item['account_id']}")
        node_colors.append(TIER_CHART_COLORS.get(tier, "#98E6C3"))

    focal_idx = len(labels)
    labels.append(f"★ {focal_acc}")
    node_colors.append(TIER_CHART_COLORS["FOCAL"])

    for item in outbound:
        tier = str(item.get("risk_tier", "LOW")).upper()
        labels.append(f"OUT · {item['account_id']}")
        node_colors.append(TIER_CHART_COLORS.get(tier, "#6D28D9"))

    for i, item in enumerate(inbound):
        tier = str(item.get("risk_tier", "LOW")).upper()
        amt = float(item.get("amount", 0.0))
        cnt = int(item.get("txn_count", 1))
        sources.append(i)
        targets.append(focal_idx)
        values.append(max(amt, 1.0))
        link_colors.append(link_rgba.get(tier, "rgba(152, 230, 195, 0.38)"))
        link_customdata.append(
            f"{item['account_id']} → {focal_acc}<br>Amount: {format_inr(amt)} ({cnt} txn) · Tier: {tier}"
        )

    out_offset = focal_idx + 1
    for j, item in enumerate(outbound):
        tier = str(item.get("risk_tier", "LOW")).upper()
        amt = float(item.get("amount", 0.0))
        cnt = int(item.get("txn_count", 1))
        sources.append(focal_idx)
        targets.append(out_offset + j)
        values.append(max(amt, 1.0))
        out_link_col = (
            "rgba(239, 68, 68, 0.44)"
            if tier == "HIGH"
            else ("rgba(245, 158, 11, 0.36)" if tier == "MEDIUM" else "rgba(109, 40, 217, 0.40)")
        )
        link_colors.append(out_link_col)
        link_customdata.append(
            f"{focal_acc} → {item['account_id']}<br>Amount: {format_inr(amt)} ({cnt} txn) · Tier: {tier}"
        )

    return go.Figure(
        data=[
            go.Sankey(
                arrangement="snap",
                node={
                    "pad": 16,
                    "thickness": 18,
                    "line": {
                        "color": "rgba(255,255,255,0.22)" if dark_mode else "#E2E8F0",
                        "width": 0.8,
                    },
                    "label": labels,
                    "color": node_colors,
                    "hovertemplate": "%{label}<br>Total Flow: ₹%{value:,.2f}<extra></extra>",
                },
                link={
                    "source": sources,
                    "target": targets,
                    "value": values,
                    "color": link_colors,
                    "customdata": link_customdata,
                    "hovertemplate": "%{customdata}<extra></extra>",
                },
            )
        ],
        layout={
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(0,0,0,0)",
            "font": {"color": text_color, "size": 11},
            "margin": {"l": 8, "r": 8, "t": 12, "b": 12},
            "height": 380,
        },
    )


def build_structuring_timeline(
    timeline_data: list[dict[str, Any]],
    account_id: str,
    dark_mode: bool,
) -> go.Figure:
    """Build interactive INR structuring & velocity timeline with PAN and RTGS threshold lines."""
    import plotly.graph_objects as go

    text_color = "#FFFFFF" if dark_mode else "#0A1931"
    grid_color = "rgba(255,255,255,0.10)" if dark_mode else "rgba(10,25,49,0.10)"
    stem_color = "rgba(148,163,184,0.34)" if dark_mode else "rgba(79,70,229,0.22)"

    traces: list[go.Scatter] = []
    if timeline_data:
        has_ts = bool(timeline_data[0].get("timestamp")) and timeline_data[0]["timestamp"] != "1"
        in_x, in_y, in_hover = [], [], []
        out_std_x, out_std_y, out_std_hover = [], [], []
        out_hr_x, out_hr_y, out_hr_hover = [], [], []
        stem_x: list[Any] = []
        stem_y: list[Any] = []

        for ev in timeline_data:
            x_val = ev["timestamp"] if has_ts else ev["step"]
            amt = float(ev["amount"])
            tier = str(ev.get("risk_tier", "LOW")).upper()
            hover_txt = (
                f"<b>{html.escape(ev['direction'])}</b> · {html.escape(str(ev['txn_id']))}<br>"
                f"Counterparty: {html.escape(str(ev['counterparty']))}<br>"
                f"Amount: {format_inr(amt)}<br>"
                f"Time: {html.escape(str(x_val))} · Risk Tier: {tier}"
            )
            stem_x.extend([x_val, x_val, None])
            stem_y.extend([0.0, amt, None])

            if ev["direction"] == "INBOUND":
                in_x.append(x_val)
                in_y.append(amt)
                in_hover.append(hover_txt)
            elif tier == "HIGH" or (45_000.0 <= amt <= 50_000.0) or (180_000.0 <= amt <= 200_000.0):
                out_hr_x.append(x_val)
                out_hr_y.append(amt)
                out_hr_hover.append(hover_txt)
            else:
                out_std_x.append(x_val)
                out_std_y.append(amt)
                out_std_hover.append(hover_txt)

        traces.append(
            go.Scatter(
                x=stem_x,
                y=stem_y,
                mode="lines",
                line={"color": stem_color, "width": 1.2},
                hoverinfo="skip",
                showlegend=False,
            )
        )
        if in_x:
            traces.append(
                go.Scatter(
                    x=in_x,
                    y=in_y,
                    mode="markers",
                    name="Inbound Credit",
                    marker={
                        "color": "#98E6C3",
                        "size": 9,
                        "symbol": "triangle-up",
                        "line": {"color": "#0A1931", "width": 0.8},
                    },
                    hovertext=in_hover,
                    hoverinfo="text",
                )
            )
        if out_std_x:
            traces.append(
                go.Scatter(
                    x=out_std_x,
                    y=out_std_y,
                    mode="markers",
                    name="Outbound Debit",
                    marker={
                        "color": "#6D28D9",
                        "size": 9,
                        "symbol": "diamond",
                        "line": {"color": "#FFFFFF", "width": 0.7},
                    },
                    hovertext=out_std_hover,
                    hoverinfo="text",
                )
            )
        if out_hr_x:
            traces.append(
                go.Scatter(
                    x=out_hr_x,
                    y=out_hr_y,
                    mode="markers",
                    name="Flagged / Structuring Debit",
                    marker={
                        "color": "#EF4444",
                        "size": 10,
                        "symbol": "diamond",
                        "line": {"color": "#FFFFFF", "width": 0.8},
                    },
                    hovertext=out_hr_hover,
                    hoverinfo="text",
                )
            )

    return go.Figure(
        data=traces,
        layout={
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(0,0,0,0)",
            "font": {"color": text_color, "size": 11},
            "legend": {"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1.0},
            "xaxis": {
                "title": f"Transaction Sequence / Timestamp ({account_id})",
                "gridcolor": grid_color,
                "zeroline": False,
            },
            "yaxis": {
                "title": "Transfer Amount (INR)",
                "gridcolor": grid_color,
                "tickprefix": "₹",
                "zeroline": False,
            },
            "shapes": [
                {
                    "type": "line",
                    "xref": "paper",
                    "yref": "y",
                    "x0": 0,
                    "x1": 1,
                    "y0": 50_000,
                    "y1": 50_000,
                    "line": {"color": "#F59E0B", "width": 1.5, "dash": "dash"},
                },
                {
                    "type": "line",
                    "xref": "paper",
                    "yref": "y",
                    "x0": 0,
                    "x1": 1,
                    "y0": 200_000,
                    "y1": 200_000,
                    "line": {"color": "#EF4444", "width": 1.5, "dash": "dash"},
                },
            ],
            "annotations": [
                {
                    "xref": "paper",
                    "yref": "y",
                    "x": 0.01,
                    "y": 50_000,
                    "xanchor": "left",
                    "yanchor": "bottom",
                    "text": "₹50,000 PAN Limit",
                    "showarrow": False,
                    "font": {"color": "#F59E0B", "size": 11},
                },
                {
                    "xref": "paper",
                    "yref": "y",
                    "x": 0.01,
                    "y": 200_000,
                    "xanchor": "left",
                    "yanchor": "bottom",
                    "text": "₹2,00,000 RTGS Threshold",
                    "showarrow": False,
                    "font": {"color": "#EF4444", "size": 11},
                },
            ],
            "margin": {"l": 12, "r": 12, "t": 36, "b": 12},
            "height": 360,
        },
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
    from src.sar_generator import generate_rbi_sar

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
        "cfg_full_motion": True,
        "cfg_graph_layout": "force",
        "cfg_max_graph_nodes": 65,
        "cfg_enable_graph_physics": False,
        "cfg_currency_mode": "compact",
        "cfg_sar_auto_generate": True,
        "active_nav": "Executive Triage",
        "active_nav_idx": 0,
        "_prev_active_nav": "Executive Triage",
        "_prev_nav_theme": "dark",
        "selected_account": default_account,
        "sar_cache": None,
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


def _select_preset(acc_id: str) -> None:
    """Sync preset click into selected_account and dropdown selector before rerun."""
    st.session_state["selected_account"] = acc_id
    st.session_state["global_account_selector"] = acc_id
    st.session_state["sar_cache"] = None


def _sync_selected_account() -> None:
    """Sync top account selector widget back to persistent selected_account."""
    chosen = st.session_state.get("global_account_selector")
    if chosen:
        st.session_state["selected_account"] = chosen
        st.session_state["sar_cache"] = None


def _on_dark_mode_change() -> None:
    st.session_state["cfg_dark_mode"] = bool(st.session_state.get("w_dark_mode", True))


def _on_motion_change() -> None:
    label = st.session_state.get("w_motion_mode", MOTION_MODE_LABELS[True])
    st.session_state["cfg_full_motion"] = label == MOTION_MODE_LABELS[True]


def _on_layout_mode_change() -> None:
    label = st.session_state.get("w_graph_layout_mode", GRAPH_LAYOUT_LABELS["force"])
    st.session_state["cfg_graph_layout"] = (
        "hierarchical" if label == GRAPH_LAYOUT_LABELS["hierarchical"] else "force"
    )


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


def _on_sidebar_nav_change() -> None:
    """Sync native sidebar radio selection into active_nav session keys."""
    chosen = st.session_state.get("w_sidebar_nav_radio")
    if chosen in NAV_OPTIONS:
        st.session_state["active_nav"] = chosen
        st.session_state["active_nav_idx"] = NAV_OPTIONS.index(chosen)
        st.session_state["_prev_active_nav"] = chosen


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
    """Render sidebar branding, zero-iframe st.radio navigation, and presets."""
    logo_mtime = LOGO_PATH.stat().st_mtime if LOGO_PATH.exists() else 0.0
    logo_uri = load_logo_data_uri(logo_mtime)

    with st.sidebar:
        if logo_uri is not None:
            st.markdown(
                f'<div class="finsight-sidebar-logo">'
                f'<img src="{logo_uri}" alt="FINSIGHT Logo" width="170" height="92" decoding="async" />'
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<div class="finsight-sidebar-logo"><strong>🛡️ FINSIGHT AML</strong></div>', unsafe_allow_html=True)

        st.caption("FIU-IND Compliance & Mule Account Intelligence")
        st.divider()

        current_nav = st.session_state["active_nav"]
        if current_nav not in NAV_OPTIONS:
            current_nav = NAV_OPTIONS[0]
            st.session_state["active_nav"] = current_nav

        st.session_state["active_nav_idx"] = NAV_OPTIONS.index(current_nav)
        if st.session_state.get("w_sidebar_nav_radio") != current_nav:
            st.session_state["w_sidebar_nav_radio"] = current_nav

        selected_nav = st.radio(
            "Compliance Modules",
            options=NAV_OPTIONS,
            key="w_sidebar_nav_radio",
            on_change=_on_sidebar_nav_change,
        )
        if selected_nav in NAV_OPTIONS:
            st.session_state["active_nav"] = selected_nav
            st.session_state["active_nav_idx"] = NAV_OPTIONS.index(selected_nav)
        st.session_state["_prev_active_nav"] = st.session_state["active_nav"]
        st.session_state["_prev_nav_theme"] = "dark" if dark_mode else "light"

        st.divider()
        st.markdown("**Quick Benchmark Presets**")
        st.caption("IBM AML HI-Small calibrated INR accounts")

        for acc_id, meta in presets.items():
            is_active = st.session_state.get("selected_account") == acc_id
            btn_type = "primary" if is_active else "secondary"
            st.button(
                meta["label"],
                key=f"preset_btn_{acc_id}",
                width="stretch",
                type=btn_type,
                on_click=_select_preset,
                args=(acc_id,),
            )

        st.divider()
        with st.container(border=True):
            st.markdown(
                '<div class="telemetry-header"><span class="live-beacon"></span><strong>Model &amp; Threshold Telemetry</strong></div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div style="font-size: 0.80rem; line-height: 1.6; opacity: 0.9;">'
                '• <strong>Detector:</strong> IsolationForest (<span class="finsight-mono">contamination=0.05</span>)<br>'
                '• <strong>Precision (HIGH):</strong> <span class="finsight-mono">88.67%</span><br>'
                '• <strong>PAN Structuring Window:</strong> <span class="finsight-mono">₹45,000 – ₹50,000</span><br>'
                '• <strong>RTGS Threshold Window:</strong> <span class="finsight-mono">₹1,80,000 – ₹2,00,000</span>'
                "</div>",
                unsafe_allow_html=True,
            )

    return st.session_state["active_nav"]


# ---------------------------------------------------------------------------
# Tab 1: Executive Triage & Portfolio Surveillance
# ---------------------------------------------------------------------------
def _render_html_alert_table(df_slice: pd.DataFrame) -> str:
    """Render a zero-JS-overhead, tabular-nums HTML ledger table for initial triage paint."""
    if df_slice.empty:
        return '<div class="finsight-ledger-wrap" style="padding: 1rem;">No matching accounts found.</div>'

    rows_html: list[str] = []
    for row in df_slice.itertuples(index=False):
        acc_id = html.escape(str(row.Account_ID))
        score_str = f"{float(row.Risk_Score):.2f}"
        badge = risk_badge_html(str(row.Risk_Tier))
        inflow_str = html.escape(str(row.Total_Inflow))
        outflow_str = html.escape(str(row.Total_Outflow))
        ptr_str = f"{float(row.Pass_Through_Ratio):.2f}x"
        vel_str = f"{int(row.Near_Limit_Velocity)}"
        tx_str = f"{int(row.Tx_Count):,}"
        rows_html.append(
            f"<tr>"
            f'<td><span class="finsight-mono">{acc_id}</span></td>'
            f"<td class='num-col'><strong>{score_str}</strong></td>"
            f"<td>{badge}</td>"
            f"<td class='num-col'>{inflow_str}</td>"
            f"<td class='num-col'>{outflow_str}</td>"
            f"<td class='num-col'>{ptr_str}</td>"
            f"<td class='num-col'>{vel_str}</td>"
            f"<td class='num-col'>{tx_str}</td>"
            f"</tr>"
        )

    body = "".join(rows_html)
    return (
        '<div class="finsight-ledger-wrap">'
        '<table class="finsight-ledger-table">'
        "<thead><tr>"
        "<th>Account_ID</th>"
        "<th class='num-col'>Risk_Score</th>"
        "<th>Risk_Tier</th>"
        "<th class='num-col'>Total_Inflow</th>"
        "<th class='num-col'>Total_Outflow</th>"
        "<th class='num-col'>Pass_Through</th>"
        "<th class='num-col'>Near_Limit_Vel</th>"
        "<th class='num-col'>Tx_Count</th>"
        "</tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table></div>"
    )


@st.fragment
def _render_triage_queue_fragment(acct_df: pd.DataFrame, compact_inr: bool) -> None:
    """Isolated fragment for interactive triage filtering and search without full-page reruns."""
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

        top_25_df = display_df.head(25)
        st.markdown(_render_html_alert_table(top_25_df), unsafe_allow_html=True)
        st.caption(
            f"Showing top {len(top_25_df)} priority alerts of {len(filtered):,} matching bank accounts "
            f"(toggle below for full 100-row interactive spreadsheet)."
        )

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
                    st.session_state["active_nav_idx"] = NAV_OPTIONS.index("Account Forensics")
                    st.session_state["active_nav"] = "Account Forensics"
                    st.session_state["w_sidebar_nav_radio"] = "Account Forensics"
                    st.rerun()

        if st.toggle("Enable Interactive Spreadsheet View (Top 100)", value=False):
            st.dataframe(display_df, width="stretch", hide_index=True, height=340)


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
        render_kpi_card("Monitored Accounts", f"{total_accounts:,}", "SAV / CUR / CORP Ledgers", "#0047AB", delay_ms=0)
    with c2:
        render_kpi_card("HIGH Risk Alerts", f"{high_count:,}", "88.67% Precision · Priority STR", "#6D28D9", delay_ms=50)
    with c3:
        render_kpi_card("MEDIUM Risk Watchlist", f"{med_count:,}", "Enhanced Due Diligence (EDD)", "#4F46E5", delay_ms=100)
    with c4:
        render_kpi_card("LOW Risk Baseline", f"{low_count:,}", "Standard KYC Monitoring", "#98E6C3", delay_ms=150)

    render_spacer()
    _render_triage_queue_fragment(acct_df, compact_inr)


# ---------------------------------------------------------------------------
# Tab 2: Deep-Dive Account Forensics
# ---------------------------------------------------------------------------
def render_account_forensics(
    analysis: dict[str, Any],
    tx_df: pd.DataFrame,
    mtime: float,
    compact_inr: bool,
    dark_mode: bool,
) -> None:
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
        render_kpi_card("Composite Mule Score", f"{risk_score:.2f} / 100", f"Tier: {risk_tier}", score_accent, delay_ms=0)
    with m2:
        render_kpi_card("Total Credit Inflow", inflow_main, inflow_alt, "#0047AB", delay_ms=50)
    with m3:
        render_kpi_card("Total Debit Outflow", outflow_main, outflow_alt, "#4F46E5", delay_ms=100)
    with m4:
        ptr_status = "Mule Layering Alert (≈1.0)" if 0.85 <= ptr <= 1.15 else "Normal Retention"
        render_kpi_card(
            "Pass-Through Ratio",
            f"{ptr:.2f}x",
            ptr_status,
            "#6D28D9" if ptr >= 0.85 else "#98E6C3",
            delay_ms=150,
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

    render_spacer()
    with st.container(border=True):
        st.subheader("INR Structuring & Velocity Timeline")
        st.caption(
            "Inbound credits vs. outbound debits across timestamps with ₹50,000 PAN & ₹2,00,000 RTGS threshold markers"
        )
        timeline_events = get_cached_timeline(acc_id, mtime, tx_df)
        if timeline_events:
            timeline_fig = build_structuring_timeline(timeline_events, acc_id, dark_mode)
            st.plotly_chart(timeline_fig, width="stretch", height=360, config={"displayModeBar": False})
        else:
            st.info("No chronological transactions available for this account.")


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
    layout_mode: str,
) -> dict[str, Any]:
    """Build and render the cached 2-hop PyVis subgraph plus interactive Plotly charts."""
    render_section_header(
        f"2-Hop Fund-Flow Topology — {account_id}",
        "Interactive PyVis network analysis detecting fan-in collection, fan-out dispersal, and mule rings",
        accent_color="#0047AB",
    )

    graph_stats = get_cached_subgraph(
        account_id, mtime, max_nodes, enable_physics, dark_mode, layout_mode, tx_df
    )
    in_deg = int(graph_stats.get("in_degree", 0))
    out_deg = int(graph_stats.get("out_degree", 0))
    asymmetry = float(graph_stats.get("degree_asymmetry", 0.0))
    topology = str(graph_stats.get("topology", "Standard Bilateral"))
    hr_count = int(graph_stats.get("high_risk_node_count", 0))
    hr_nodes = graph_stats.get("high_risk_nodes", [])

    g1, g2, g3, g4 = st.columns(4)
    with g1:
        render_kpi_card("Detected Topology", topology, f"In: {in_deg} · Out: {out_deg}", "#0047AB", delay_ms=0)
    with g2:
        render_kpi_card("Degree Asymmetry", f"{asymmetry:+.2f}", "(In - Out) / Total Degree", "#4F46E5", delay_ms=50)
    with g3:
        render_kpi_card("2-Hop High-Risk Nodes", f"{hr_count:,}", "Full 2-hop contagion count", "#6D28D9", delay_ms=100)
    with g4:
        render_kpi_card(
            "Subgraph Connectivity",
            f"{in_deg + out_deg} Edges",
            f"Rendered {graph_stats.get('rendered_nodes', 0)}/{graph_stats.get('num_nodes', 0)} nodes",
            "#98E6C3",
            delay_ms=150,
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
        ctrl_col, leg_col = st.columns([1.1, 1.35])
        with ctrl_col:
            layout_options = [GRAPH_LAYOUT_LABELS["force"], GRAPH_LAYOUT_LABELS["hierarchical"]]
            current_layout_label = GRAPH_LAYOUT_LABELS.get(layout_mode, GRAPH_LAYOUT_LABELS["force"])
            st.radio(
                "Graph Layout Mode",
                options=layout_options,
                index=layout_options.index(current_layout_label),
                horizontal=True,
                key="w_graph_layout_mode",
                on_change=_on_layout_mode_change,
            )
        with leg_col:
            st.markdown(
                "<div style='padding-top: 1.55rem; font-size: 0.82rem; display: flex; flex-wrap: wrap; gap: 0.7rem;'>"
                "<span>★ <strong style='color:#4F46E5;'>Focal Subject</strong></span>"
                "<span>◆ <strong style='color:#EF4444;'>HIGH Risk</strong></span>"
                "<span>● <strong style='color:#F59E0B;'>MEDIUM Risk</strong></span>"
                "<span>● <strong style='color:#98E6C3;'>LOW Risk</strong></span>"
                "<span>| Edges: <span style='color:#98E6C3;'>Inbound</span> · <span style='color:#6D28D9;'>Outbound</span></span>"
                "</div>",
                unsafe_allow_html=True,
            )

        physics_note = "Interactive physics ON" if enable_physics else "Stabilized (physics auto-paused)"
        pruned_note = (
            f"Showing top {graph_stats.get('rendered_nodes')} prioritized nodes out of {graph_stats.get('num_nodes')}."
            if graph_stats.get("pruned")
            else f"Showing all {graph_stats.get('rendered_nodes', 0)} nodes."
        )
        st.caption(
            f"💡 **Layout:** `{GRAPH_LAYOUT_LABELS.get(layout_mode)}` · {pruned_note} · {physics_note} · Drag nodes or hover edges for INR details."
        )
        html_content = graph_stats.get("html_content", "")
        if html_content:
            st.iframe(html_content, height=540, width="stretch")
        else:
            st.warning("PyVis graph HTML payload was empty for the selected account.")

    render_spacer()

    chart_left, chart_right = st.columns([1.05, 1.0])
    with chart_left:
        with st.container(border=True):
            st.subheader("Inbound-to-Outbound Fund-Flow Sankey")
            st.caption("Top senders → focal subject → top destination accounts, weighted by INR volume")
            sankey_data = graph_stats.get("sankey_data") or {}
            if sankey_data.get("inbound") or sankey_data.get("outbound"):
                sankey_fig = build_fund_flow_sankey(sankey_data, dark_mode)
                st.plotly_chart(sankey_fig, width="stretch", height=380, config={"displayModeBar": False})
            else:
                st.info("No direct inbound/outbound edges available for Sankey rendering.")

    with chart_right:
        with st.container(border=True):
            st.subheader("INR Structuring & Velocity Timeline")
            st.caption("Inbound credits vs. outbound debits against ₹50,000 PAN & ₹2,00,000 RTGS bands")
            timeline_data = graph_stats.get("timeline_data") or []
            if timeline_data:
                timeline_fig = build_structuring_timeline(timeline_data, account_id, dark_mode)
                st.plotly_chart(timeline_fig, width="stretch", height=360, config={"displayModeBar": False})
            else:
                st.info("No chronological transactions available for timeline plotting.")

    return graph_stats


# ---------------------------------------------------------------------------
# Tab 4: FIU-IND STR / SAR Narrative Generator
# ---------------------------------------------------------------------------
@st.fragment
def _render_sar_panel_fragment(
    analysis: dict[str, Any],
    graph_stats: dict[str, Any],
    mtime: float,
    compact_inr: bool,
) -> None:
    """Isolated fragment for STR/SAR generation, editing, and export without full-page reruns."""
    acc_id = str(analysis.get("account_id", "UNKNOWN"))
    risk_tier = str(analysis.get("risk_tier", "LOW")).upper()
    active_key, key_fp = _active_api_key()
    auto_generate = bool(st.session_state.get("cfg_sar_auto_generate", True))

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


def render_sar_workbench(
    analysis: dict[str, Any],
    graph_stats: dict[str, Any],
    mtime: float,
    compact_inr: bool,
) -> None:
    """Render PMLA 2002 / RBI KYC Suspicious Transaction Report generator and export tools."""
    acc_id = str(analysis.get("account_id", "UNKNOWN"))
    render_section_header(
        f"FIU-IND Suspicious Transaction Report (STR / SAR) — {acc_id}",
        f"Automated PMLA 2002 & RBI Master Direction on KYC synthesis ({GEMINI_MODEL_NAME})",
        accent_color="#6D28D9",
    )
    _render_sar_panel_fragment(analysis, graph_stats, mtime, compact_inr)


# ---------------------------------------------------------------------------
# Tab 5: Workbench Settings & Runtime Governance
# ---------------------------------------------------------------------------
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
            st.subheader("Appearance & Motion")
            st.toggle(
                "Dark Mode (Navy Blue #0A1931 / Light Mode #FFFFFF)",
                value=bool(st.session_state["cfg_dark_mode"]),
                key="w_dark_mode",
                on_change=_on_dark_mode_change,
            )
            motion_options = [MOTION_MODE_LABELS[True], MOTION_MODE_LABELS[False]]
            current_motion_label = MOTION_MODE_LABELS[bool(st.session_state["cfg_full_motion"])]
            st.radio(
                "Motion & Ambient Effects",
                options=motion_options,
                index=motion_options.index(current_motion_label),
                key="w_motion_mode",
                on_change=_on_motion_change,
                horizontal=True,
            )
            mode_label = (
                "Navy Blue Dark Mode (#0A1931)"
                if st.session_state["cfg_dark_mode"]
                else "White Light Mode (#FFFFFF)"
            )
            st.caption(f"Active canvas: **{mode_label}** · Motion: **{current_motion_label}**")

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
    _init_session_state("SAV_4405_SBI")
    _apply_pending_state()

    dark_mode = bool(st.session_state["cfg_dark_mode"])
    full_motion = bool(st.session_state["cfg_full_motion"])
    inject_custom_css(dark_mode, full_motion)

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

    active_nav = render_sidebar(presets, dark_mode)
    render_hero_banner()

    valid_accounts = set(acct_df["Account_ID"].astype(str))
    current_acc = str(st.session_state["selected_account"])
    if current_acc not in valid_accounts and not acct_df.empty:
        current_acc = str(acct_df["Account_ID"].iloc[0])
        st.session_state["selected_account"] = current_acc

    selector_options = _build_priority_selector_options(acct_df, presets, current_acc)
    if selector_options and st.session_state.get("global_account_selector") not in selector_options:
        st.session_state["global_account_selector"] = current_acc

    sel_col1, sel_col2, sel_col3 = st.columns([2.2, 1.3, 1.0])
    with sel_col1:
        st.selectbox(
            "Active Subject Account ID (Top 250 Priority & Presets — Search Full 18.6k in Triage)",
            options=selector_options,
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
    layout_mode = str(st.session_state.get("cfg_graph_layout", "force"))

    # Lazy tab execution: 2-hop graph runs only on graph/SAR tabs
    if active_nav == "Executive Triage":
        render_executive_triage(acct_df, compact_inr)
    elif active_nav == "Account Forensics":
        render_account_forensics(analysis, tx_df, mtime, compact_inr, dark_mode)
    elif active_nav == "2-Hop Topology":
        render_graph_topology(
            active_account, tx_df, mtime, max_nodes, enable_physics, dark_mode, layout_mode
        )
    elif active_nav == "FIU-IND STR/SAR":
        graph_stats = get_cached_subgraph(
            active_account, mtime, max_nodes, enable_physics, dark_mode, layout_mode, tx_df
        )
        render_sar_workbench(analysis, graph_stats, mtime, compact_inr)
    elif active_nav == "Settings":
        render_settings()


if __name__ == "__main__":
    main()
