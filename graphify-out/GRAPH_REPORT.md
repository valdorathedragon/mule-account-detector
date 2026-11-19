# Graph Report - Mule account prototype ver 1(test case)  (2026-11-19)

## Corpus Check
- 8 files · ~14,023 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 2 file(s) not represented in the graph (top: (none) 1, .toml 1)

## Summary
- 253 nodes · 504 edges · 16 communities (11 shown, 5 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 31 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `87cfebe1`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- data_pipeline.py
- analyze_account
- 🛡️ Indian UPI Mule Account Anomaly & FIU-IND Compliance Workbench
- generate_rbi_sar
- graph_engine.py
- get_cached_subgraph
- ml_engine.py
- render_account_forensics
- render_sidebar
- main
- app.py
- render_sar_workbench

## God Nodes (most connected - your core abstractions)
1. `main()` - 21 edges
2. `generate_rbi_sar()` - 16 edges
3. `render_sar_workbench()` - 15 edges
4. `analyze_account()` - 15 edges
5. `train_and_score()` - 14 edges
6. `CodeRabbit Audit & Hardening` - 14 edges
7. `render_account_forensics()` - 13 edges
8. `render_settings()` - 13 edges
9. `build_account_subgraph()` - 13 edges
10. `render_graph_topology()` - 11 edges

## Surprising Connections (you probably didn't know these)
- `Backend, SAR & UI Updates` --references--> `get_dynamic_presets()`  [INFERRED]
  docs/CHANGELOG.md → ui/app.py
- `PyVis HTML Embedding & Session Isolation` --references--> `build_account_subgraph()`  [INFERRED]
  docs/CHANGELOG.md → src/graph_engine.py
- ``analyze_account()` Data Contract` --references--> `analyze_account()`  [INFERRED]
  docs/CHANGELOG.md → src/ml_engine.py
- `CodeRabbit Audit & Hardening` --references--> `analyze_account()`  [INFERRED]
  docs/CHANGELOG.md → src/ml_engine.py
- `CodeRabbit Audit & Hardening` --references--> `_build_top_drivers()`  [INFERRED]
  docs/CHANGELOG.md → src/ml_engine.py

## Import Cycles
- None detected.

## Communities (16 total, 5 thin omitted)

### Community 0 - "data_pipeline.py"
Cohesion: 0.13
Nodes (10): build_bank_dataset(), _calibrate_hub_placements(), _convert_amounts_to_inr(), engineer_features(), _keep_outside_structuring(), main(), _map_indian_bank_accounts(), _map_timestamps_to_window() (+2 more)

### Community 2 - "analyze_account"
Cohesion: 0.11
Nodes (16): Added, `analyze_account()` Data Contract, Graph Topology Metrics, IsolationForest Configuration, Phase 3: ML Anomaly Scoring, Graph Topology & SAR Synthesis, Risk_Score Normalisation, SAR Synthesis & Fallback Architecture, _AccountIndex (+8 more)

### Community 3 - "🛡️ Indian UPI Mule Account Anomaly & FIU-IND Compliance Workbench"
Cohesion: 0.08
Nodes (22): [0.1.0] - 2026-11-18 - Project Initialization & Scaffolding, [0.2.0] - 2026-11-18 - Phase 2: Data Engineering & Feature Pipeline, Added, Added, Backend, SAR & UI Updates, Changelog - FINSIGHT: Mule Account Detection, Feature Engineering & Compliance Rationale, IBM AML Benchmark Integration (`src/data_pipeline.py`) (+14 more)

### Community 4 - "generate_rbi_sar"
Cohesion: 0.11
Nodes (17): Added, Phase 4: Single-Page Streamlit Investigator Dashboard, PyVis HTML Embedding & Session Isolation, SAR Export Workflow, Sidebar Controls & Demo Presets, UI Architecture, _account_category_label(), _build_prompt() (+9 more)

### Community 5 - "graph_engine.py"
Cohesion: 0.09
Nodes (12): build_account_subgraph(), _build_full_graph(), _compute_node_risk_maps(), _degree_asymmetry(), _df_cache_key(), _get_graph_entry(), _GraphCacheEntry, _high_risk_accounts() (+4 more)

### Community 6 - "get_cached_subgraph"
Cohesion: 0.24
Nodes (4): get_cached_analysis(), get_cached_scored_data(), get_cached_subgraph(), load_logo_bytes()

### Community 8 - "ml_engine.py"
Cohesion: 0.12
Nodes (12): CodeRabbit Audit & Hardening, _artifact_stat_key(), _CacheRecord, _create_temp_path(), load_scored_data(), main(), _manifest_path_for(), normalize_risk_scores() (+4 more)

### Community 9 - "render_account_forensics"
Cohesion: 0.17
Nodes (9): format_inr(), inject_custom_css(), render_account_forensics(), render_executive_triage(), render_graph_topology(), render_kpi_card(), _render_palette_swatches(), render_section_header() (+1 more)

### Community 11 - "main"
Cohesion: 0.18
Nodes (6): get_scored_mtime(), _apply_pending_state(), get_dynamic_presets(), _init_session_state(), main(), _sync_selected_account()

### Community 12 - "app.py"
Cohesion: 0.16
Nodes (8): _active_api_key(), gemini_status_badge_html(), _on_currency_change(), _on_dark_mode_change(), _on_max_nodes_change(), _on_physics_change(), _on_sar_mode_change(), render_settings()

### Community 13 - "render_sar_workbench"
Cohesion: 0.20
Nodes (5): classify_account_segment(), extract_bank_code(), get_cached_sar(), render_sar_workbench(), risk_badge_html()

## Knowledge Gaps
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Changelog - FINSIGHT: Mule Account Detection` connect `🛡️ Indian UPI Mule Account Anomaly & FIU-IND Compliance Workbench` to `analyze_account`, `generate_rbi_sar`?**
  _High betweenness centrality (0.148) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `generate_rbi_sar()` (e.g. with `Added` and `SAR Export Workflow`) actually correct?**
  _`generate_rbi_sar()` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Should `data_pipeline.py` be split into smaller, more focused modules?**
  _Cohesion score 0.13054187192118227 - nodes in this community are weakly interconnected._
- **Why does `Phase 3: ML Anomaly Scoring, Graph Topology & SAR Synthesis` connect `analyze_account` to `ml_engine.py`, `🛡️ Indian UPI Mule Account Anomaly & FIU-IND Compliance Workbench`?**
  _High betweenness centrality (0.131) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `analyze_account()` (e.g. with `Added` and ``analyze_account()` Data Contract`) actually correct?**
  _`analyze_account()` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Should `analyze_account` be split into smaller, more focused modules?**
  _Cohesion score 0.10541310541310542 - nodes in this community are weakly interconnected._
- **Why does `CodeRabbit Audit & Hardening` connect `ml_engine.py` to `analyze_account`, `generate_rbi_sar`, `graph_engine.py`?**
  _High betweenness centrality (0.097) - this node is a cross-community bridge._