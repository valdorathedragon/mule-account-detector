# Changelog - FINSIGHT: Mule Account Detection

All notable step-by-step architectural, backend, ML pipeline, UI, and documentation changes to this project are documented in this file for inclusion in the final PDF report.

## Phase 6: FINSIGHT Rebrand, Multi-Account Generalization & IBM AML Integration

**Version:** `[0.6.0] - 2026-11-18`

### Rebrand & Terminology Normalization
- Rebranded project identity across documentation, backend modules, and dashboard UI to **FINSIGHT: Mule Account Detection**, normalizing the brand graphic at `assets/finsight_logo.jpeg`.
- Renamed dataset artifacts from legacy rail-specific naming to multi-account banking paths: `data/bank_mule_features.csv` and `data/scored_bank_data.csv`, removing legacy files and stale `models/` cache manifests.
- Purged all legacy rail strings across `src/`, `ui/`, `docs/`, `README.md`, and live outputs so reporting covers multi-category Indian bank accounts (**Savings**, **Current**, and **Corporate/Shell** accounts operating across **NEFT**, **RTGS**, and **IMPS** rails).

### IBM AML Benchmark Integration (`src/data_pipeline.py`)
- Replaced synthetic transaction generation with real-world ingestion of `data/raw/HI-Small_Trans.csv` (`5,078,345` raw records) using vectorized NumPy boolean index selection (`~8s` ingest).
- Extracted all **`5,177`** confirmed laundering transactions (`Is Laundering == 1`), **`3,500`** 1-hop placement/dispersion neighbors, **`2,323`** 2-hop counterparty neighborhood edges, and **`4,000`** stratified legitimate records across `Payment Format` strata into a **`15,000`-row** benchmark (`data/bank_mule_features.csv`: `5,177` laundering / `34.51%`, `9,823` normal / `65.49%`).
- Mapped raw bank/account pairs deterministically into realistic Indian bank identifiers:
  - Savings: `SAV_XXXX_SBI`, `SAV_XXXX_HDFC`
  - Current: `CUR_XXXX_ICICI`, `CUR_XXXX_AXIS`
  - Corporate: `CORP_XXXX_KOTAK`
- Converted amounts monotonically to INR (`₹`) anchored to Indian AML structuring regimes and generalized `Near_Limit_Velocity` to flag transfers within **`₹45,000–₹50,000`** (PAN reporting threshold structuring band) and **`₹1,80,000–₹2,00,000`** (RTGS structuring band).
- Mapped transaction timestamps monotonically onto a 24-hour investigation window (`2026-11-18 00:00:00` to `23:59:59`, validating partial/empty parses without cross-year distortion) preserving placement-to-laundering rapid turnaround (`2–45` min) while keeping normal accounts cleanly bounded (`Pass_Through_Ratio` max `0.6188` for normal traffic vs. `0.9593` median for laundering rows).

### Backend, SAR & UI Updates
- **`src/ml_engine.py`**: Updated artifact paths to `data/bank_mule_features.csv` and `data/scored_bank_data.csv`, generalized `Near_Limit_Velocity` driver descriptions to cite PAN/RTGS structuring thresholds, and removed static legacy presets. Scoring run across `15,000` IBM AML rows yielded **LOW `11,713` · MEDIUM `2,537` · HIGH `750`**. Benchmark alignment vs `is_mule_label` is **precision `0.8867`** and **recall `0.1285`** (`contamination=0.05`); explicitly documented as synthetic label-calibrated alignment because INR PAN/RTGS projection conditions thresholds on `Is Laundering`.
- **`src/sar_generator.py`**: Updated system instructions, prompt templates, and deterministic fallbacks to derive Subject Bank Account type (`Savings` / `Current` / `Corporate`) directly from canonical ID prefixes (`SAV_`, `CUR_`, `CORP_`) under PMLA 2002 and RBI KYC Master Directions without making unsupported transfer-rail assertions.
- **`ui/app.py`**: Updated page title to *FINSIGHT: Mule Account Detection*, added `assets/finsight_logo.jpeg` to the header and sidebar, wired `get_dynamic_presets()` directly to `data/scored_bank_data.csv` (loading **`SAV_4405_SBI`** [HIGH, `100.00`], **`SAV_3416_HDFC`** [MEDIUM, `76.00`], and **`SAV_3100_HDFC`** [LOW, `33.75`]), and rebuilt `data/network.html` around `SAV_4405_SBI` (`305` nodes, `304` edges).
- **Documentation & PDF Packaging**: Consolidated release history and Phase 6 IBM AML benchmark metrics into `docs/FINSIGHT_v1_Changelog.pdf`.

## Phase 4: Single-Page Streamlit Investigator Dashboard

**Version:** `[0.4.0] - 2026-11-18`

### Added
- `ui/app.py` — single-page investigator workbench for *FINSIGHT: Mule Account Detection*, launched with `streamlit run ui/app.py` from the project root.
- `.streamlit/config.toml` — native dark theme (`#05060f` background, `#0b0d1e` secondary, `#22d3ee` primary) so Streamlit-rendered widgets (dataframe, inputs) match the custom CSS.
- `python-dotenv` added to `requirements.txt`.

### UI Architecture
- **Backend contract** (confirmed against the refreshed graphify graph): `analyze_account(account_id) -> dict` (`account_id, risk_score, risk_tier, total_inflow, total_outflow, pass_through_ratio, top_drivers, counterparties`); `build_account_subgraph(account_id, df) -> dict` (`in_degree, out_degree, degree_asymmetry, topology, high_risk_node_count, high_risk_nodes, output_path, …`); `generate_rbi_sar(payload, graph_stats) -> str`; `format_inr()` for Indian number formatting.
- **Path resolution:** `ui/app.py` inserts the project root (and `src/`) onto `sys.path` from `Path(__file__).resolve().parents[1]`, so imports work regardless of launch directory.
- **Palette:** background `#05060f`, cards `#0b0d1e`, cyan `#22d3ee`, violet `#8b5cf6`, amber `#f59e0b`, high-risk red `#ef4444`; tier badges map HIGH→red, MEDIUM→amber, LOW→cyan.
- **Layout:** Row 1 four KPI cards (Risk Score + tier badge, 24h inflow, 24h outflow in `INR XX,XX,XXX.XX`, Pass-Through Ratio %); Row 2 split `1.2 : 1` (network | drivers + SAR); Row 3 account ledger (`txn_id, timestamp, nameOrig, nameDest, amount, Pass_Through_Ratio, Risk_Score`).
- **Safety:** every dynamic string rendered through `unsafe_allow_html` is passed through `html.escape()`; analysis results are cached in `st.session_state` so widget reruns do not regenerate the SAR.

### Sidebar Controls & Demo Presets
- `.env` is loaded with `python-dotenv` (`override=False`) so `GEMINI_API_KEY` is picked up automatically; an optional password-masked *Gemini API Key (Optional Override)* input is scoped strictly to the investigator's Streamlit session (`api_key` parameter on `generate_rbi_sar()`) rather than mutating process-wide `os.environ["GEMINI_API_KEY"]` (CWE-668 mitigation).
- Preset buttons dynamically highlight representative **[HIGH]**, **[MEDIUM]**, and **[LOW]** bank accounts alongside a searchable selector covering all unique accounts in `data/scored_bank_data.csv`.
- *Run Forensic Analysis* triggers analysis; the first page load auto-runs the top **HIGH** preset account. Presets select and run in one click; changing the selector alone prompts the user to press Run.

### PyVis HTML Embedding & Session Isolation
- Each forensic run passes a unique per-run temporary file (`data/.network_*.html`, cleaned up in `finally:`) to `build_account_subgraph()`, fits the PyVis canvas (`430px`) into the `460px` iframe (`streamlit.components.v1.html(..., height=460, scrolling=False)`), and binds `analyze_account(account_id, df=df)`, graph extraction, and the ledger table to the same scored DataFrame snapshot.
- Compact metrics below the graph show Role, In-Degree, Out-Degree, Degree Asymmetry and connected high-risk neighbours (focal account excluded). HTML read failures preserve computed `graph_stats`, while graph build failures suppress SAR synthesis/download so missing topology is never reported as zero activity.

### SAR Export Workflow
- The two-paragraph report from `generate_rbi_sar()` renders inside a compliance card (paragraphs HTML-escaped) and is exported via `st.download_button` as `SAR_<account_id>.txt` (filename sanitised to `[A-Za-z0-9._@-]`). Without a Gemini key, or on any API failure, the deterministic tier-calibrated fallback is shown and exported.

## Phase 3: ML Anomaly Scoring, Graph Topology & SAR Synthesis

**Version:** `[0.3.0] - 2026-11-18`

### Added
- `src/ml_engine.py` — IsolationForest training, Risk_Score normalisation, artifact persistence and the `analyze_account()` API.
- `src/graph_engine.py` — 2-hop NetworkX/PyVis transaction network extraction with topology metrics (`build_account_subgraph()`).
- `src/sar_generator.py` — Gemini-powered RBI/FIU-IND Suspicious Activity Report synthesis with deterministic offline fallback (`generate_rbi_sar()`).
- Artifacts: `models/iso_forest.joblib` (model bundle with feature list and hyperparameters), `data/scored_bank_data.csv` (input schema + `Anomaly_Score_Raw`, `Risk_Score`, `Risk_Tier`, `Is_Anomaly`), `data/network.html` (interactive subgraph).

### IsolationForest Configuration
| Hyperparameter | Value | Rationale |
| :--- | :--- | :--- |
| `n_estimators` | `100` | Stable path-length estimates at low cost |
| `contamination` | `0.05` | Isolates top 5% highest-severity anomalous flows |
| `random_state` | `42` | Reproducible scoring for audit |
| Features | `amount`, `Pass_Through_Ratio`, `Near_Limit_Velocity` | Value, layering speed, regulatory structuring |

### Risk_Score Normalisation
The raw `decision_function` score \(s\) is negative for anomalies and positive for inliers, with the contamination boundary at \(s = 0\). A piecewise linear map anchors that boundary at the HIGH threshold, so the HIGH tier coincides with the model's own anomaly decision:

$$
\text{Risk} =
\begin{cases}
80 + 20 \cdot \dfrac{s}{s_{\min}} & s < 0 \\[6pt]
79.99 \cdot \left(1 - \dfrac{s}{s_{\max}}\right) & s \ge 0
\end{cases}
$$

Tiers: **HIGH** ≥ 80, **MEDIUM** 50–79.99, **LOW** < 50.

**Phase 3 baseline validation (10,000 rows):** LOW 8,485 · MEDIUM 1,015 · HIGH 500 (precision and recall 0.956 on Phase 2 synthetic baseline prior to Phase 6 IBM AML integration).

### `analyze_account()` Data Contract
```json
{
  "account_id": "str",
  "risk_score": "float (0-100)",
  "risk_tier": "HIGH | MEDIUM | LOW",
  "total_inflow": "float (INR)",
  "total_outflow": "float (INR)",
  "pass_through_ratio": "float (outflow / inflow)",
  "top_drivers": "list[str] (max 5)",
  "counterparties": "list[str]"
}
```
- `risk_score` = max `Risk_Score` among transactions the account originated; receive-only accounts (e.g. cash-out endpoints) take the max of their received transactions.
- `top_drivers` are rule-derived explanations: pass-through ≥ 80%, regulatory threshold structuring count, credit-to-debit turnaround ≤ 60 min, fan-in/fan-out ≥ 5 unique counterparties, transfers above the dataset 95th percentile.

### Graph Topology Metrics
- Parallel transactions are aggregated into weighted `networkx.DiGraph` edges (`total_amount`, `txn_count`, `max_risk`); the 2-hop neighbourhood is taken via `ego_graph(radius=2)` on the undirected view so both upstream and downstream flows are included.
- Per node: `in_degree`, `out_degree` and
  $$\text{degree\_asymmetry} = \frac{\text{in\_deg} - \text{out\_deg}}{\text{in\_deg} + \text{out\_deg} + 10^{-5}}$$
  (+1 pure fan-in, −1 pure fan-out, ≈0 balanced relay).
- Focal topology label: FAN-IN AGGREGATOR (≥ 0.5), FAN-OUT DISTRIBUTOR (≤ −0.5), otherwise PASS-THROUGH RELAY.
- Rendering: high-risk nodes (any originated `Risk_Score` ≥ 80 or mule label) in red `#ef4444`, normal nodes in cyan `#22d3ee`, focal account outlined in yellow; edge width scales with `log10(amount)`. Exported as static HTML to `data/network.html`.

### SAR Synthesis & Fallback Architecture
- Uses `google-genai` (`genai.Client`) with `model="gemini-3.8-flash"`, `temperature=0.2`, and a system instruction casting the model as an Indian bank AML Compliance Officer reporting to FIU-IND under PMLA 2002 and RBI KYC Master Directions.
- The prompt supplies the `analyze_account()` payload and graph metrics as JSON and requires exactly two paragraphs: (1) INR flows, Pass-Through Ratio and red flags; (2) fan-in/fan-out topology, typology and recommended action.
- **Generation Safeguards (Bugfix):** Explicitly configured `max_output_tokens=1024` within `types.GenerateContentConfig` in `src/sar_generator.py` to prevent token exhaustion and ensure 2-paragraph FIU-IND SAR responses never truncate mid-sentence.
- **Fallback:** if `GEMINI_API_KEY` is unset, or on any exception (offline, rate limit, invalid key, empty response), `generate_rbi_sar()` returns a deterministic two-paragraph template with Indian-format INR amounts (e.g. `INR 24,35,946.51`), so the demo never crashes.

### CodeRabbit Audit & Hardening
- **`src/sar_generator.py`**:
  - Switched `thinking_level` to `"LOW"` and raised `max_output_tokens=2048` inside `types.GenerateContentConfig` to ensure Gemini 3.8 Flash API compatibility and prevent output truncation.
  - Added completion and structural guards (`_is_complete_two_paragraph_sar()`) verifying `finish_reason == STOP` and two complete punctuated prose paragraphs before accepting LLM output.
  - Enforced evidence-grounded, tier-calibrated conclusions and policy actions in `_tier_guidance()`, `_build_prompt()`, `_fallback_sar()`, `_contains_policy_action()`, and `_figures_match_evidence()`: `HIGH` risk triggers expedited compliance review, Enhanced Due Diligence (RBI KYC Master Directions), and FIU-IND STR evaluation/filing (with debit restriction subject to independent verification); `MEDIUM` risk recommends step-up transaction monitoring; `LOW` risk notes the model did not establish layering and recommends standard monitoring only.
  - Added `_linked_high_risk_count()` to exclude the focal `account_id` from `high_risk_node_count` and wrapped `genai.Client` in a context manager (`with genai.Client(...) as client:`) to close connections on all exit paths.
- **`src/graph_engine.py`**:
  - Updated `_high_risk_accounts()` to mirror `analyze_account()` (max outgoing `Risk_Score`, falling back to max incoming `Risk_Score` for receive-only accounts such as cash-out mules), ensuring receive-only high-risk nodes render in red (`#ef4444`).
  - Applied `html.escape()` to account identifiers in PyVis node tooltips (`title`) to mitigate CWE-79 HTML/XSS injection.
- **`src/ml_engine.py`**:
  - Replaced `@lru_cache` with SHA-256 snapshot binding (`_manifest_path_for()`, `_resolve_valid_generation()`, and immutable `_CacheRecord`), automatically retraining when `bank_mule_features.csv` changes and returning `.copy()` frames to prevent caller mutation of cached data.
  - Staged immutable generation artifacts under `models/generations/` and published via temporary files + `os.replace()` so failed writes never expose partial or mismatched scores.
  - Deduplicated `pd.concat([incoming, outgoing])` by `txn_id` in `_build_top_drivers()` so self-transfers (`A -> A`) are counted once, refined structuring driver phrasing, used strict `>` against the 95th percentile, and selected dynamic sample accounts cleanly.
- **`src/data_pipeline.py`**:
  - Used isolated local `np.random.default_rng(seed)` generation without global RNG mutation.
  - Resolved `OUTPUT_PATH` relative to `PROJECT_ROOT` (`Path(__file__).resolve().parents[1] / "data" / "bank_mule_features.csv"`) and switched CSV export to atomic `tempfile` + `os.replace()`.
- **Verification**:
  - Verified `0` findings from Snyk Code (`src/`), Snyk SCA (`requirements.txt`), and Semgrep (`auto` ruleset across source modules).

## [0.2.0] - 2026-11-18 - Phase 2: Data Engineering & Feature Pipeline

### Added
- Built `src/data_pipeline.py` with deterministic seeding (`seed=42`) to construct an Indian banking transaction dataset over a 24-hour investigation window (`2026-11-18 00:00:00` to `2026-11-18 23:59:59`).
- Engineered core behavioral schema: `txn_id`, `nameOrig`, `nameDest`, `amount`, `timestamp`, `is_mule_label`, `Pass_Through_Ratio`, `Near_Limit_Velocity`.

### Feature Engineering & Compliance Rationale
- **`Pass_Through_Ratio` (`Outflow / Inflow`)**: Aggregated per-account total outflow (`groupby("nameOrig")["amount"].sum()`) divided by total inflow (`groupby("nameDest")["amount"].sum()`), mapped onto `nameOrig` (`0.0` when `Inflow == 0`, rounded to 4 decimals) to capture rapid balance depletion across pass-through mule accounts.
- **`Near_Limit_Velocity`**: Binary structuring indicator (`1` for transfers within threshold monitoring bands — generalized in Phase 6 to PAN `₹45,000–₹50,000` and RTGS `₹1,80,000–₹2,00,000` bands — else `0`).

## [0.1.0] - 2026-11-18 - Project Initialization & Scaffolding

### Added
- Created `docs/` directory and initialized `docs/CHANGELOG.md` to track step-by-step development milestones for the final PDF report.
- Created `src/` directory reserved for backend logic and ML anomaly detection components.
- Created `ui/` directory reserved for the Streamlit interface and graph visualization layer.
- Created `requirements.txt` with core dependencies: `pandas`, `scikit-learn`, `streamlit`, `networkx`, `pyvis`, `google-genai`.
