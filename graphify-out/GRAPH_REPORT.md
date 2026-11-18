# Graph Report - Mule account prototype ver 1(test case)  (2026-11-18)

## Corpus Check
- 10 files · ~7,371 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 3 file(s) not represented in the graph (top: (none) 2, .toml 1)

## Summary
- 148 nodes · 270 edges · 10 communities (8 shown, 2 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 25 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `696feffc`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- data_pipeline.py
- Phase 4: Single-Page Streamlit Investigator Dashboard
- 🛡️Mule Account Detection Engine
- sar_generator.py
- graph_engine.py
- analyze_account
- ml_engine.py
- app.py

## God Nodes (most connected - your core abstractions)
1. `CodeRabbit Audit & Hardening` - 15 edges
2. `generate_rbi_sar()` - 15 edges
3. `build_account_subgraph()` - 14 edges
4. `train_and_score()` - 13 edges
5. `analyze_account()` - 13 edges
6. `run_analysis()` - 9 edges
7. `load_scored_data()` - 9 edges
8. `Phase 3: ML Anomaly Scoring, Graph Topology & SAR Synthesis` - 8 edges
9. `build_upi_dataset()` - 8 edges
10. `_build_prompt()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `UI Architecture` --references--> `format_inr()`  [INFERRED]
  docs/CHANGELOG.md → src/sar_generator.py
- `Sidebar Controls & Demo Presets` --references--> `generate_rbi_sar()`  [INFERRED]
  docs/CHANGELOG.md → src/sar_generator.py
- `PyVis HTML Embedding & Session Isolation` --references--> `build_account_subgraph()`  [INFERRED]
  docs/CHANGELOG.md → src/graph_engine.py
- `SAR Export Workflow` --references--> `generate_rbi_sar()`  [INFERRED]
  docs/CHANGELOG.md → src/sar_generator.py
- `Added` --references--> `build_account_subgraph()`  [INFERRED]
  docs/CHANGELOG.md → src/graph_engine.py

## Import Cycles
- None detected.

## Communities (10 total, 2 thin omitted)

### Community 0 - "data_pipeline.py"
Cohesion: 0.21
Nodes (6): build_upi_dataset(), engineer_features(), _format_timestamp(), generate_mule_clusters(), generate_normal_traffic(), _split_amount_exactly()

### Community 1 - "Phase 4: Single-Page Streamlit Investigator Dashboard"
Cohesion: 0.14
Nodes (13): [0.1.0] - 2026-11-18 - Project Initialization & Scaffolding, [0.2.0] - 2026-11-18 - Phase 2: Data Engineering & Feature Pipeline, Added, Added, Added, Changelog - Mule Account Detector Prototype, Feature Engineering & Compliance Rationale, Phase 4: Single-Page Streamlit Investigator Dashboard (+5 more)

### Community 3 - "🛡️Mule Account Detection Engine"
Cohesion: 0.33
Nodes (5): 🛠️ Development Pipeline, 🛡️Mule Account Detection Engine, 📌 Overview, ⚡ System Architecture, 🧰 Tech Stack & Environment

### Community 4 - "sar_generator.py"
Cohesion: 0.19
Nodes (10): CodeRabbit Audit & Hardening, _build_prompt(), _contains_policy_action(), _fallback_sar(), _figures_match_evidence(), format_inr(), generate_rbi_sar(), _is_complete_two_paragraph_sar() (+2 more)

### Community 5 - "graph_engine.py"
Cohesion: 0.17
Nodes (5): build_account_subgraph(), _build_full_graph(), _degree_asymmetry(), _high_risk_accounts(), _topology_label()

### Community 6 - "analyze_account"
Cohesion: 0.28
Nodes (8): Added, `analyze_account()` Data Contract, Graph Topology Metrics, IsolationForest Configuration, Phase 3: ML Anomaly Scoring, Graph Topology & SAR Synthesis, Risk_Score Normalisation, SAR Synthesis & Fallback Architecture, analyze_account()

### Community 8 - "ml_engine.py"
Cohesion: 0.09
Nodes (12): assign_risk_tier(), _build_top_drivers(), _CacheRecord, _create_temp_path(), load_scored_data(), main(), _manifest_path_for(), normalize_risk_scores() (+4 more)

### Community 12 - "app.py"
Cohesion: 0.12
Nodes (10): main(), _compute_24h_totals(), esc(), _fit_graph_html(), get_accounts(), get_scored_df(), graph_metric(), kpi_card() (+2 more)

## Knowledge Gaps
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `CodeRabbit Audit & Hardening` connect `sar_generator.py` to `ml_engine.py`, `graph_engine.py`, `analyze_account`?**
  _High betweenness centrality (0.144) - this node is a cross-community bridge._
- **Are the 14 inferred relationships involving `CodeRabbit Audit & Hardening` (e.g. with `_high_risk_accounts()` and `analyze_account()`) actually correct?**
  _`CodeRabbit Audit & Hardening` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Should `Phase 4: Single-Page Streamlit Investigator Dashboard` be split into smaller, more focused modules?**
  _Cohesion score 0.14285714285714285 - nodes in this community are weakly interconnected._
- **Why does `Phase 3: ML Anomaly Scoring, Graph Topology & SAR Synthesis` connect `analyze_account` to `Phase 4: Single-Page Streamlit Investigator Dashboard`, `sar_generator.py`?**
  _High betweenness centrality (0.119) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `generate_rbi_sar()` (e.g. with `Added` and `SAR Export Workflow`) actually correct?**
  _`generate_rbi_sar()` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Should `ml_engine.py` be split into smaller, more focused modules?**
  _Cohesion score 0.0944741532976827 - nodes in this community are weakly interconnected._
- **Why does `build_account_subgraph()` connect `graph_engine.py` to `Phase 4: Single-Page Streamlit Investigator Dashboard`, `app.py`, `analyze_account`?**
  _High betweenness centrality (0.102) - this node is a cross-community bridge._