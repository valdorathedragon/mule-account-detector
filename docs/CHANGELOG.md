# Changelog - Mule Account Detector Prototype

All notable step-by-step architectural, backend, ML pipeline, UI, and documentation changes to this project will be documented in this file for inclusion in the final PDF report.

## Phase 3: ML Anomaly Scoring, Graph Topology & SAR Synthesis

**Version:** `[0.3.0] - 2026-11-18`

### Added
- `src/ml_engine.py` — IsolationForest training, Risk_Score normalisation, artifact persistence and the `analyze_account()` API.
- `src/graph_engine.py` — 2-hop NetworkX/PyVis transaction network extraction with topology metrics (`build_account_subgraph()`).
- `src/sar_generator.py` — Gemini-powered RBI/FIU-IND Suspicious Activity Report synthesis with deterministic offline fallback (`generate_rbi_sar()`).
- Artifacts: `models/iso_forest.joblib` (model bundle with feature list and hyperparameters), `data/scored_upi_data.csv` (input schema + `Anomaly_Score_Raw`, `Risk_Score`, `Risk_Tier`, `Is_Anomaly`), `data/network.html` (interactive subgraph).

### IsolationForest Configuration
| Hyperparameter | Value | Rationale |
| :--- | :--- | :--- |
| `n_estimators` | `100` | Stable path-length estimates at low cost |
| `contamination` | `0.05` | Matches the injected 5% mule prevalence |
| `random_state` | `42` | Reproducible scoring for audit |
| Features | `amount`, `Pass_Through_Ratio`, `Near_Limit_Velocity` | Value, layering speed, structuring |

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

**Scoring run results (10,000 transactions):** LOW 8,485 · MEDIUM 1,015 · HIGH 500. HIGH-tier precision and recall against `is_mule_label` are both **0.956**.

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
- `top_drivers` are rule-derived explanations: pass-through ≥ 80%, near-limit structuring count, credit-to-debit turnaround ≤ 60 min, fan-in/fan-out ≥ 5 unique counterparties, transfers above the dataset 95th percentile.
- Example (`mule_c1_hub01@ybl`): Risk 92.88 (HIGH), inflow INR 24,35,946.51, outflow INR 23,89,741.89, pass-through 98.10%, first debit 2 min after first credit.

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
- **Generation Safeguards (Bugfix):** Explicitly configured `max_output_tokens=1024` and `thinking_config=types.ThinkingConfig(thinking_level="MINIMAL")` within `types.GenerateContentConfig` in `src/sar_generator.py` to prevent token exhaustion and ensure 2-paragraph FIU-IND SAR responses never truncate mid-sentence.
- **Fallback:** if `GEMINI_API_KEY` is unset, or on any exception (offline, rate limit, invalid key, empty response), `generate_rbi_sar()` returns a deterministic two-paragraph template with Indian-format INR amounts (e.g. `INR 24,35,946.51`), so the demo never crashes.

### CodeRabbit Audit & Hardening
- **`src/sar_generator.py`**:
  - Switched `thinking_level` from `"MINIMAL"` to `"LOW"` and raised `max_output_tokens=2048` inside `types.GenerateContentConfig` to ensure Gemini 3.8 Flash API compatibility and prevent output truncation.
  - Added completion and structural guards (`_is_complete_two_paragraph_sar()`) verifying `finish_reason == STOP` and two complete punctuated prose paragraphs before accepting LLM output.
  - Enforced evidence-grounded, tier-calibrated conclusions and policy actions in `_tier_guidance()`, `_build_prompt()`, `_fallback_sar()`, `_contains_policy_action()`, and `_figures_match_evidence()`: `HIGH` risk triggers expedited compliance review, Enhanced Due Diligence (RBI KYC Master Directions), and FIU-IND STR evaluation/filing (with debit restriction subject to independent verification); `MEDIUM` risk recommends step-up transaction monitoring; `LOW` risk notes the model did not establish layering and recommends standard monitoring only.
  - Added `_linked_high_risk_count()` to exclude the focal `account_id` from `high_risk_node_count` and wrapped `genai.Client` in a context manager (`with genai.Client(...) as client:`) to close connections on all exit paths.
- **`src/graph_engine.py`**:
  - Updated `_high_risk_accounts()` to mirror `analyze_account()` (max outgoing `Risk_Score`, falling back to max incoming `Risk_Score` for receive-only accounts such as cash-out mules), ensuring receive-only high-risk nodes render in red (`#ef4444`).
  - Applied `html.escape()` to account identifiers in PyVis node tooltips (`title`) to mitigate CWE-79 HTML/XSS injection.
- **`src/ml_engine.py`**:
  - Replaced `@lru_cache` with SHA-256 snapshot binding (`_manifest_path_for()`, `_resolve_valid_generation()`, and immutable `_CacheRecord`), automatically retraining when `upi_mule_features.csv` changes and returning `.copy()` frames to prevent caller mutation of cached data.
  - Staged immutable generation artifacts under `models/generations/` and published via temporary files + `os.replace()` so failed writes never expose partial or mismatched scores.
  - Deduplicated `pd.concat([incoming, outgoing])` by `txn_id` in `_build_top_drivers()` so self-transfers (`A -> A`) are counted once, refined near-limit driver phrasing to avoid inferring structuring from a single transfer, used strict `>` against the 95th percentile, and guarded `main()` demo account lookup.
- **`src/data_pipeline.py`**:
  - Removed global `np.random.seed(seed)` in favor of the local `np.random.default_rng(seed)` generator.
  - Resolved `OUTPUT_PATH` relative to `PROJECT_ROOT` (`Path(__file__).resolve().parents[1] / "data" / "upi_mule_features.csv"`), restricted synthetic retail user debits to top-up credits received by the debit timestamp, and switched CSV export to atomic `tempfile` + `os.replace()`.
- **Verification**:
  - Re-ran `src/data_pipeline.py` (`10,000` rows: `500` mule, `9,500` normal) and `src/ml_engine.py` (LOW `8,251`, MEDIUM `1,249`, HIGH `500`; HIGH-tier precision/recall `0.9500`); all `5` hardening unit/smoke checks passed.
  - Confirmed `0` findings from Snyk Code (`src/`), Snyk SCA (`requirements.txt`, `all_projects=false, skip_unresolved=true`), and Semgrep (`290` rules across `4` files).
  - Latest CodeRabbit CLI review (`--agent --uncommitted --include-untracked --dir src`) completed with `0` critical findings and `0` findings in `src/data_pipeline.py`; `5` major and `5` minor follow-up architectural/concurrency suggestions remain documented for Phase 4/production hardening (cross-process publication locking, generation retention/GC, mixed-dtype graph ID coercion, non-finite float guard in `format_inr`, and strict per-field JSON validation for LLM prose).

## [0.2.0] - 2026-11-18 - Phase 2: Data Engineering & Feature Pipeline

### Added
- Created `src/data_pipeline.py` using deterministic simulation (`seed=42`) to synthesize a 10,000-row Indian UPI transaction dataset over a 24-hour window (`2026-11-18 00:00:00` to `2026-11-18 23:59:59`).
- Generated `data/upi_mule_features.csv` containing 10,000 chronologically sorted transactions (`txn_id` `UPI20261118000001` through `UPI20261118010000`) with schema: `txn_id`, `nameOrig`, `nameDest`, `amount`, `timestamp`, `is_mule_label`, `Pass_Through_Ratio`, `Near_Limit_Velocity`.

### Technical Architecture & Anomaly Injection
- **Baseline Retail UPI Traffic (9,500 rows / 95.00%, `is_mule_label = 0`)**:
  - **Employer/Top-Up Inflows (1,500 rows)**: Transfers from `employer_XX@sbi` to `user_XXXX@okaxis` (`₹20,000–₹85,000`).
  - **Everyday Retail & P2P Spends (7,600 rows)**: Transfers from `user_XXXX@okaxis` and `payer_XXXX@okicici` to `merchant_XXXX@paytm` (`₹50–₹15,000`), capping each user's cumulative outflow below `34%` of total inflow (`Pass_Through_Ratio` range `0.0000–0.3399`).
  - **Victim Placement Inflows (400 rows)**: Legitimate originators (`payer_XXXX@okicici`) funding mule collectors 5–20 minutes prior to illicit sweeps (`< ₹90,000` per transfer).
- **Mule Ring Anomaly Topology (500 rows / 5.00%, `is_mule_label = 1`)**:
  - Simulated 5 independent mule rings (`c1`–`c5`), each comprising 10 Collector Mules (`mule_c{k}_col01@okaxis`–`col10@okaxis`), 2 Aggregator Hub Mules (`mule_c{k}_hub01@ybl`, `mule_c{k}_hub02@ybl`), and 2 downstream cash-out endpoints (`cashout_c{k}_01@oksbi`, `cashout_c{k}_02@oksbi`).
  - **Fan-In Layering (50 rows/cluster = 250 rows)**: Each collector executes 5 rapid near-limit bursts (`₹95,500–₹99,900`) into its assigned hub mule, draining `95.5%–99.0%` of placement inflow.
  - **Pass-Through Layering (50 rows/cluster = 250 rows)**: Within 1–5 minutes of Fan-In arrival, each hub passes through `95.5%–98.5%` of received funds in structured near-limit transfers (`₹90,500–₹99,500`) to cash-out accounts.

### Feature Engineering & Compliance Rationale
- **`Pass_Through_Ratio` (`Outflow / Inflow`)**: Aggregated per-account total outflow (`groupby("nameOrig")["amount"].sum()`) divided by total inflow (`groupby("nameDest")["amount"].sum()`), mapped onto `nameOrig` (`0.0` when `Inflow == 0`, rounded to 4 decimals). Captures rapid balance depletion typical of pass-through mule accounts (`0.9559–0.9899` for labeled mule transactions vs. `0.0000–0.3399` for normal transactions).
- **`Near_Limit_Velocity`**: Binary flag (`1` when `₹90,000 <= amount <= ₹100,000`, else `0`) capturing structured smurfing just beneath the standard ₹1,00,000 Indian UPI per-transaction cap (`500` flagged rows among mule transactions, `0` among normal traffic).

## [0.1.0] - 2026-11-18 - Project Initialization & Scaffolding

### Added
- Created `docs/` directory and initialized `docs/CHANGELOG.md` to track step-by-step development milestones for the final PDF report.
- Created empty `src/` directory reserved for backend logic and ML anomaly detection components.
- Created empty `ui/` directory reserved for the Streamlit interface and graph visualization layer.
- Created `requirements.txt` with core dependencies: `pandas`, `scikit-learn`, `streamlit`, `networkx`, `pyvis`, `google-genai`.
