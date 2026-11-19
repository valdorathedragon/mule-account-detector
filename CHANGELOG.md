# Changelog

All notable changes to **FINSIGHT: Mule Account Detection & FIU-IND Compliance Workbench** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Earlier phase-by-phase build history (Phases 1–6) is archived in [docs/CHANGELOG.md](docs/CHANGELOG.md).

## [2026-11-20]

### Added
- **Interactive Plotly Forensic Visualizations**: Added an Inbound-to-Outbound Fund-Flow Sankey Diagram (`height=380`) and an INR Structuring & Velocity Timeline (`height=360`) featuring ₹50,000 PAN and ₹2,00,000 RTGS regulatory threshold markers in both **2-Hop Topology** and **Account Forensics**.
- **2-Hop PyVis Topology Enhancements (`src/graph_engine.py`)**: Added Hierarchical Left-to-Right (`L→R`) vs. Force-Directed Cluster layout toggle, logarithmic INR volume-scaled nodes, curved directional edges, focal star / HIGH-risk diamond encoding, and HTML-escaped hover tooltips.
- **Motion & Tactile UI Polish (`ui/app.py`)**: Added GPU-composited continuous idle ambient effects (`ambientFloat`, `bannerSheen`, `livePulse`, `logoGlow`) and tactile reactive card/button micro-interactions, paired with a **Motion & Ambient Effects** accessibility toggle in **Settings**.
- **Reverse-Proxy Compression & Tunnel Delivery (`deploy/`)**: Added local Gzip/Brotli compression, immutable `/static/*` caching headers, WebSocket passthrough, and bundled `Source` `@font-face` `font-display: swap` configurations in `deploy/gzip_proxy.py`, `deploy/Caddyfile`, and `deploy/nginx.conf` for port `8080` and Cloudflare Tunnel sharing.
- **Project Documentation**: Three-page project documentation (`finsight_project_documentation.pdf`).

### Changed & Optimized
- **6-Color Institutional Palette & Light Mode Overhaul (`ui/app.py`)**: Enforced the 6-color FINSIGHT palette (`#0A1931` Navy Blue, `#0047AB` Blue, `#4F46E5` Blue-Violet, `#6D28D9` Violet, `#98E6C3` Mint Green, `#FFFFFF` White) across Dark Mode and Light Mode, adding crisp `1.5px solid #0A1931` architectural borders and a white SaaS navigation panel in Light Mode.
- **LCP, CLS & Bundle Payload Optimization**: Cut initial render delay and layout shifts by adopting CSS-styled native `st.radio` sidebar navigation (eliminating third-party Vue iframe and icon font overhead), optimizing `assets/finsight_logo.jpeg` to `440px`, lazily importing heavy libraries (`plotly.graph_objects`, `networkx`, `pyvis`, `sklearn.ensemble.IsolationForest`, `joblib`, `google.genai`), adding `.finsight-mono` styling (`ui-monospace`) to prevent initial `SourceCodeVF` blocking, gating the 100-row `st.dataframe` behind an interactive toggle in favor of a lightweight top-25 HTML ledger table, and separating `inject_custom_css()` cleanly from hero banner HTML.
- **Streamlit Server & Telemetry Tuning (`.streamlit/config.toml`)**: Enabled `enableWebsocketCompression = true` under `[server]` and disabled `gatherUsageStats = false` under `[browser]`.

### Fixed
- **Sidebar Preset & Dropdown Synchronization**: Bound Quick Benchmark Presets active blue highlights to `selected_account` and synchronized preset buttons with `global_account_selector` via two-way `on_click` / `on_change` session callbacks.
- **Vertical Scrolling & Material Icon Ligatures**: Removed fixed viewport/containment locks in `ui/app.py` to restore smooth native vertical scrolling across all 5 modules, and excluded `[data-testid="stIconMaterial"]` from global system font overrides while restoring `"Material Symbols Rounded"` ligatures on the sidebar collapse/expand control.
- **Settings Streamlining**: Removed the redundant color palette swatch grid from **Settings**.
