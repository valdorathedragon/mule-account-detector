# Graph Report - Mule account prototype ver 1(test case)  (2026-11-18)

## Corpus Check
- 9 files · ~5,186 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 2 file(s) not represented in the graph (top: (none) 2)

## Summary
- 120 nodes · 195 edges · 12 communities (8 shown, 4 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 7 edges (avg confidence: 0.94)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `47e2b351`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- data_pipeline.py
- [0.2.0] - 2026-11-18 - Phase 2: Data Engineering & Feature Pipeline
- ml_engine.py
- 🛡️Mule Account Detection Engine
- sar_generator.py
- graph_engine.py
- analyze_account
- load_scored_data
- train_and_score
- _resolve_valid_generation
- normalize_risk_scores

## God Nodes (most connected - your core abstractions)
1. `train_and_score()` - 13 edges
2. `generate_rbi_sar()` - 11 edges
3. `build_account_subgraph()` - 11 edges
4. `analyze_account()` - 9 edges
5. `build_upi_dataset()` - 8 edges
6. `_resolve_valid_generation()` - 7 edges
7. `load_scored_data()` - 7 edges
8. `_build_prompt()` - 7 edges
9. `Phase 3: ML Anomaly Scoring, Graph Topology & SAR Synthesis` - 7 edges
10. `_fallback_sar()` - 6 edges

## Surprising Connections (you probably didn't know these)
- ``analyze_account()` Data Contract` --references--> `analyze_account()`  [INFERRED]
  docs/CHANGELOG.md → src/ml_engine.py
- `Added` --references--> `generate_rbi_sar()`  [INFERRED]
  docs/CHANGELOG.md → src/sar_generator.py
- `SAR Synthesis & Fallback Architecture` --references--> `generate_rbi_sar()`  [INFERRED]
  docs/CHANGELOG.md → src/sar_generator.py
- `Added` --references--> `build_account_subgraph()`  [INFERRED]
  docs/CHANGELOG.md → src/graph_engine.py
- `Added` --references--> `analyze_account()`  [INFERRED]
  docs/CHANGELOG.md → src/ml_engine.py

## Import Cycles
- None detected.

## Communities (12 total, 4 thin omitted)

### Community 0 - "data_pipeline.py"
Cohesion: 0.16
Nodes (7): build_upi_dataset(), engineer_features(), _format_timestamp(), generate_mule_clusters(), generate_normal_traffic(), main(), _split_amount_exactly()

### Community 1 - "[0.2.0] - 2026-11-18 - Phase 2: Data Engineering & Feature Pipeline"
Cohesion: 0.25
Nodes (7): [0.1.0] - 2026-11-18 - Project Initialization & Scaffolding, [0.2.0] - 2026-11-18 - Phase 2: Data Engineering & Feature Pipeline, Added, Added, Changelog - Mule Account Detector Prototype, Feature Engineering & Compliance Rationale, Technical Architecture & Anomaly Injection

### Community 3 - "🛡️Mule Account Detection Engine"
Cohesion: 0.33
Nodes (5): 🛠️ Development Pipeline, 🛡️Mule Account Detection Engine, 📌 Overview, ⚡ System Architecture, 🧰 Tech Stack & Environment

### Community 4 - "sar_generator.py"
Cohesion: 0.17
Nodes (9): _build_prompt(), _contains_policy_action(), _fallback_sar(), _figures_match_evidence(), format_inr(), generate_rbi_sar(), _is_complete_two_paragraph_sar(), _linked_high_risk_count() (+1 more)

### Community 5 - "graph_engine.py"
Cohesion: 0.18
Nodes (5): build_account_subgraph(), _build_full_graph(), _degree_asymmetry(), _high_risk_accounts(), _topology_label()

### Community 6 - "analyze_account"
Cohesion: 0.22
Nodes (9): Added, `analyze_account()` Data Contract, Graph Topology Metrics, IsolationForest Configuration, Phase 3: ML Anomaly Scoring, Graph Topology & SAR Synthesis, Risk_Score Normalisation, SAR Synthesis & Fallback Architecture, analyze_account() (+1 more)

### Community 7 - "load_scored_data"
Cohesion: 0.29
Nodes (3): _build_top_drivers(), _CacheRecord, load_scored_data()

### Community 8 - "train_and_score"
Cohesion: 0.31
Nodes (4): _create_temp_path(), _manifest_path_for(), _sha256_file(), train_and_score()

## Knowledge Gaps
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Added` connect `analyze_account` to `sar_generator.py`, `graph_engine.py`?**
  _High betweenness centrality (0.170) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `generate_rbi_sar()` (e.g. with `Added` and `SAR Synthesis & Fallback Architecture`) actually correct?**
  _`generate_rbi_sar()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Why does `Phase 3: ML Anomaly Scoring, Graph Topology & SAR Synthesis` connect `analyze_account` to `[0.2.0] - 2026-11-18 - Phase 2: Data Engineering & Feature Pipeline`?**
  _High betweenness centrality (0.166) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `analyze_account()` (e.g. with `Added` and ``analyze_account()` Data Contract`) actually correct?**
  _`analyze_account()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Why does `analyze_account()` connect `analyze_account` to `ml_engine.py`, `load_scored_data`?**
  _High betweenness centrality (0.160) - this node is a cross-community bridge._