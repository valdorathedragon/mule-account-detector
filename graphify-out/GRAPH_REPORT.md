# Graph Report - Mule account prototype ver 1(test case)  (2026-11-20)

## Corpus Check
- 9 files · ~18,413 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: (none) 2, .toml 1, .conf 1)

## Summary
- 309 nodes · 609 edges · 17 communities (13 shown, 4 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 38 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `8e3bb981`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- data_pipeline.py
- Phase 3: ML Anomaly Scoring, Graph Topology & SAR Synthesis
- render_account_forensics
- generate_rbi_sar
- graph_engine.py
- Any
- ml_engine.py
- render_graph_topology
- _render_sar_panel_fragment
- main
- app.py
- inject_custom_css
- render_sidebar
- gzip_proxy.py

## God Nodes (most connected - your core abstractions)
1. `main()` - 23 edges
2. `render_account_forensics()` - 16 edges
3. `generate_rbi_sar()` - 16 edges
4. `_render_sar_panel_fragment()` - 15 edges
5. `analyze_account()` - 15 edges
6. `build_account_subgraph()` - 14 edges
7. `render_graph_topology()` - 14 edges
8. `train_and_score()` - 14 edges
9. `CodeRabbit Audit & Hardening` - 14 edges
10. `render_settings()` - 13 edges

## Surprising Connections (you probably didn't know these)
- `PyVis HTML Embedding & Session Isolation` --references--> `build_account_subgraph()`  [INFERRED]
  docs/CHANGELOG.md → src/graph_engine.py
- `Backend, SAR & UI Updates` --references--> `get_dynamic_presets()`  [INFERRED]
  docs/CHANGELOG.md → ui/app.py
- ``analyze_account()` Data Contract` --references--> `analyze_account()`  [INFERRED]
  docs/CHANGELOG.md → src/ml_engine.py
- `CodeRabbit Audit & Hardening` --references--> `_high_risk_accounts()`  [INFERRED]
  docs/CHANGELOG.md → src/graph_engine.py
- `Added` --references--> `build_account_subgraph()`  [INFERRED]
  docs/CHANGELOG.md → src/graph_engine.py

## Import Cycles
- None detected.

## Communities (17 total, 4 thin omitted)

### Community 0 - "data_pipeline.py"
Cohesion: 0.13
Nodes (10): build_bank_dataset(), _calibrate_hub_placements(), _convert_amounts_to_inr(), engineer_features(), _keep_outside_structuring(), main(), _map_indian_bank_accounts(), _map_timestamps_to_window() (+2 more)

### Community 2 - "Phase 3: ML Anomaly Scoring, Graph Topology & SAR Synthesis"
Cohesion: 0.06
Nodes (29): [0.1.0] - 2026-11-18 - Project Initialization & Scaffolding, [0.2.0] - 2026-11-18 - Phase 2: Data Engineering & Feature Pipeline, Added, Added, Added, `analyze_account()` Data Contract, Backend, SAR & UI Updates, Changelog - FINSIGHT: Mule Account Detection (+21 more)

### Community 3 - "render_account_forensics"
Cohesion: 0.18
Nodes (6): build_fund_flow_sankey(), build_structuring_timeline(), classify_account_segment(), extract_bank_code(), format_inr(), render_account_forensics()

### Community 4 - "generate_rbi_sar"
Cohesion: 0.11
Nodes (17): Added, Phase 4: Single-Page Streamlit Investigator Dashboard, PyVis HTML Embedding & Session Isolation, SAR Export Workflow, Sidebar Controls & Demo Presets, UI Architecture, _account_category_label(), _build_prompt() (+9 more)

### Community 5 - "graph_engine.py"
Cohesion: 0.09
Nodes (17): build_account_subgraph(), _build_full_graph(), _build_sankey_data(), _compute_node_risk_maps(), _compute_node_volumes(), _degree_asymmetry(), _df_cache_key(), _edge_visual_style() (+9 more)

### Community 6 - "Any"
Cohesion: 0.17
Nodes (7): _build_priority_selector_options(), get_cached_analysis(), get_cached_sar(), get_cached_scored_data(), get_cached_subgraph(), get_cached_timeline(), get_dynamic_presets()

### Community 8 - "ml_engine.py"
Cohesion: 0.08
Nodes (21): CodeRabbit Audit & Hardening, _AccountIndex, analyze_account(), _artifact_stat_key(), assign_risk_tier(), _build_top_drivers(), _CacheRecord, _create_temp_path() (+13 more)

### Community 9 - "render_graph_topology"
Cohesion: 0.21
Nodes (7): _on_layout_mode_change(), render_executive_triage(), render_graph_topology(), render_hero_banner(), render_kpi_card(), render_section_header(), render_spacer()

### Community 10 - "_render_sar_panel_fragment"
Cohesion: 0.27
Nodes (4): _render_html_alert_table(), _render_sar_panel_fragment(), _render_triage_queue_fragment(), risk_badge_html()

### Community 11 - "main"
Cohesion: 0.18
Nodes (6): get_scored_mtime(), _apply_pending_state(), _init_session_state(), main(), render_sar_workbench(), _sync_selected_account()

### Community 12 - "app.py"
Cohesion: 0.15
Nodes (9): _active_api_key(), gemini_status_badge_html(), _on_currency_change(), _on_dark_mode_change(), _on_max_nodes_change(), _on_motion_change(), _on_physics_change(), _on_sar_mode_change() (+1 more)

### Community 14 - "render_sidebar"
Cohesion: 0.22
Nodes (4): load_logo_data_uri(), _on_sidebar_nav_change(), render_sidebar(), _select_preset()

### Community 15 - "gzip_proxy.py"
Cohesion: 0.08
Nodes (5): create_proxy_app(), proxy_http(), proxy_ws(), _rewrite_bundled_css(), _upstream_ws_url()

## Knowledge Gaps
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Changelog - FINSIGHT: Mule Account Detection` connect `Phase 3: ML Anomaly Scoring, Graph Topology & SAR Synthesis` to `generate_rbi_sar`?**
  _High betweenness centrality (0.123) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `generate_rbi_sar()` (e.g. with `Added` and `SAR Export Workflow`) actually correct?**
  _`generate_rbi_sar()` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Should `data_pipeline.py` be split into smaller, more focused modules?**
  _Cohesion score 0.13054187192118227 - nodes in this community are weakly interconnected._
- **Why does `Phase 3: ML Anomaly Scoring, Graph Topology & SAR Synthesis` connect `Phase 3: ML Anomaly Scoring, Graph Topology & SAR Synthesis` to `ml_engine.py`?**
  _High betweenness centrality (0.107) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `analyze_account()` (e.g. with `Added` and ``analyze_account()` Data Contract`) actually correct?**
  _`analyze_account()` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Should `Phase 3: ML Anomaly Scoring, Graph Topology & SAR Synthesis` be split into smaller, more focused modules?**
  _Cohesion score 0.06451612903225806 - nodes in this community are weakly interconnected._
- **Why does `build_account_subgraph()` connect `graph_engine.py` to `Phase 3: ML Anomaly Scoring, Graph Topology & SAR Synthesis`, `generate_rbi_sar`, `app.py`, `Any`?**
  _High betweenness centrality (0.091) - this node is a cross-community bridge._