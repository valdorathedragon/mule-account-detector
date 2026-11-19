"""2-hop transaction network extraction, topology metrics, visual pruning and PyVis HTML export."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import html
import json
import math
from pathlib import Path
from typing import TYPE_CHECKING
import numpy as np
import pandas as pd

if TYPE_CHECKING:
    import networkx as nx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FOCAL_NODE_COLOR = "#4F46E5"
HIGH_RISK_COLOR = "#EF4444"
MEDIUM_RISK_COLOR = "#F59E0B"
LOW_RISK_COLOR = "#98E6C3"
INBOUND_EDGE_COLOR = "#98E6C3"
OUTBOUND_EDGE_COLOR = "#6D28D9"
FOCAL_BORDER_DARK = "#98E6C3"
FOCAL_BORDER_LIGHT = "#6D28D9"
HIGH_RISK_THRESHOLD = 80.0
MEDIUM_RISK_THRESHOLD = 50.0
HOP_RADIUS = 2
EPSILON = 1e-5
MAX_VISUAL_NODES = 65
STABILIZATION_ITERATIONS = 80
GRAPH_CACHE_MAXSIZE = 4
MAX_SANKEY_BRANCHES = 12
MAX_TIMELINE_EVENTS = 500


@dataclass(frozen=True)
class _GraphCacheEntry:
    """Cached full transaction graph and precomputed per-account lookups."""

    graph: nx.DiGraph
    undirected: nx.Graph
    node_risk_scores: dict[str, float]
    node_risk_tiers: dict[str, str]
    high_risk_accounts: set[str]
    node_volumes: dict[str, float]
    orig_rows: dict[str, np.ndarray]
    dest_rows: dict[str, np.ndarray]


_GRAPH_CACHE: OrderedDict[object, _GraphCacheEntry] = OrderedDict()


def _degree_asymmetry(in_deg: int, out_deg: int) -> float:
    """(in - out) / (in + out + eps): +1 pure fan-in, -1 pure fan-out, ~0 balanced relay."""
    return round((in_deg - out_deg) / (in_deg + out_deg + EPSILON), 4)


def _topology_label(in_deg: int, out_deg: int, asymmetry: float) -> str:
    """Classify the focal account's flow topology."""
    if asymmetry >= 0.5:
        return "FAN-IN AGGREGATOR"
    if asymmetry <= -0.5:
        return "FAN-OUT DISTRIBUTOR"
    if in_deg > 0 and out_deg > 0:
        return "PASS-THROUGH RELAY"
    return "ISOLATED"


def _tier_from_score(score: float) -> str:
    if score >= HIGH_RISK_THRESHOLD:
        return "HIGH"
    if score >= MEDIUM_RISK_THRESHOLD:
        return "MEDIUM"
    return "LOW"


def _compute_node_risk_maps(df: pd.DataFrame) -> tuple[dict[str, float], dict[str, str], set[str]]:
    """Compute effective account risk scores and tiers mirroring analyze_account()."""
    if "Risk_Score" in df.columns:
        orig_scores = df.groupby(df["nameOrig"].astype(str), sort=False)["Risk_Score"].max()
        dest_scores = df.groupby(df["nameDest"].astype(str), sort=False)["Risk_Score"].max()
        combined = pd.concat([orig_scores, dest_scores.drop(labels=orig_scores.index, errors="ignore")])
        scores = {str(k): float(v) for k, v in combined.items()}
        tiers = {k: _tier_from_score(v) for k, v in scores.items()}
        high_risk = {k for k, v in scores.items() if v >= HIGH_RISK_THRESHOLD}
        return scores, tiers, high_risk

    if "is_mule_label" in df.columns:
        flagged = df[df["is_mule_label"] == 1]
        orig_nodes = set(flagged["nameOrig"].astype(str))
        receive_only_nodes = set(flagged["nameDest"].astype(str)) - set(df["nameOrig"].astype(str))
        high_risk = orig_nodes | receive_only_nodes
        scores = {n: 100.0 for n in high_risk}
        tiers = {n: "HIGH" for n in high_risk}
        return scores, tiers, high_risk

    return {}, {}, set()


def _high_risk_accounts(df: pd.DataFrame) -> set[str]:
    """Identify HIGH-risk accounts using the same rule as analyze_account():
    max outgoing Risk_Score, falling back to max incoming Risk_Score for receive-only accounts.
    """
    _, _, high_risk = _compute_node_risk_maps(df)
    return high_risk


def _build_full_graph(df: pd.DataFrame) -> nx.DiGraph:
    """Aggregate parallel transactions into weighted directed edges."""
    import networkx as nx

    agg_spec = {"total_amount": ("amount", "sum"), "txn_count": ("amount", "size")}
    if "Risk_Score" in df.columns:
        agg_spec["max_risk"] = ("Risk_Score", "max")
    edges = df.groupby(["nameOrig", "nameDest"], sort=False, as_index=False).agg(**agg_spec)

    graph = nx.DiGraph()
    has_risk = "max_risk" in edges.columns
    for row in edges.itertuples(index=False):
        graph.add_edge(
            str(row.nameOrig),
            str(row.nameDest),
            total_amount=float(row.total_amount),
            txn_count=int(row.txn_count),
            max_risk=float(row.max_risk) if has_risk else 0.0,
        )
    return graph


def _compute_node_volumes(graph: nx.DiGraph) -> dict[str, float]:
    """Sum total incident INR volume (in + out) per node."""
    volumes: dict[str, float] = {}
    for src, dst, attrs in graph.edges(data=True):
        amt = float(attrs.get("total_amount", 0.0))
        volumes[src] = volumes.get(src, 0.0) + amt
        volumes[dst] = volumes.get(dst, 0.0) + amt
    return volumes


def _df_cache_key(df: pd.DataFrame, cache_key: object | None = None) -> object:
    if cache_key is not None:
        return ("key", cache_key, len(df))
    if df.empty:
        return ("empty", tuple(df.columns))
    first_txn = str(df["txn_id"].iloc[0]) if "txn_id" in df.columns else ""
    last_txn = str(df["txn_id"].iloc[-1]) if "txn_id" in df.columns else ""
    amt_sum = float(df["amount"].sum()) if "amount" in df.columns else 0.0
    risk_sum = float(df["Risk_Score"].sum()) if "Risk_Score" in df.columns else 0.0
    return ("sig", len(df), tuple(df.columns), amt_sum, risk_sum, first_txn, last_txn)


def _get_graph_entry(df: pd.DataFrame, cache_key: object | None = None) -> _GraphCacheEntry:
    """Return cached full DiGraph + undirected view + node risk/volume/row maps."""
    key = _df_cache_key(df, cache_key=cache_key)
    cached = _GRAPH_CACHE.get(key)
    if cached is not None:
        _GRAPH_CACHE.move_to_end(key)
        return cached

    graph = _build_full_graph(df)
    undirected = graph.to_undirected()
    scores, tiers, high_risk = _compute_node_risk_maps(df)
    node_volumes = _compute_node_volumes(graph)

    orig_rows = {
        str(k): np.asarray(v, dtype=np.intp)
        for k, v in df.groupby(df["nameOrig"].astype(str), sort=False).indices.items()
    }
    dest_rows = {
        str(k): np.asarray(v, dtype=np.intp)
        for k, v in df.groupby(df["nameDest"].astype(str), sort=False).indices.items()
    }

    entry = _GraphCacheEntry(
        graph=graph,
        undirected=undirected,
        node_risk_scores=scores,
        node_risk_tiers=tiers,
        high_risk_accounts=high_risk,
        node_volumes=node_volumes,
        orig_rows=orig_rows,
        dest_rows=dest_rows,
    )
    _GRAPH_CACHE[key] = entry
    while len(_GRAPH_CACHE) > GRAPH_CACHE_MAXSIZE:
        _GRAPH_CACHE.popitem(last=False)
    return entry


def _select_visual_nodes(
    account_id: str,
    full_sub: nx.DiGraph,
    undirected: nx.Graph,
    entry: _GraphCacheEntry,
    max_nodes: int = MAX_VISUAL_NODES,
) -> set[str]:
    """Prune oversized super-hub 2-hop neighborhoods while retaining focal & highest-risk nodes."""
    all_nodes = set(full_sub.nodes)
    if len(all_nodes) <= max_nodes:
        return all_nodes

    direct_neighbors = set(undirected.neighbors(account_id))
    incident_vol: dict[str, float] = {}
    for src, dst, attrs in full_sub.edges(data=True):
        amt = float(attrs.get("total_amount", 0.0))
        incident_vol[src] = incident_vol.get(src, 0.0) + amt
        incident_vol[dst] = incident_vol.get(dst, 0.0) + amt

    others = [n for n in all_nodes if n != account_id]
    others.sort(
        key=lambda n: (
            -(1 if (n in direct_neighbors and n in entry.high_risk_accounts) else 0),
            -(1 if n in entry.high_risk_accounts else 0),
            -(1 if n in direct_neighbors else 0),
            -entry.node_risk_scores.get(n, 0.0),
            -incident_vol.get(n, 0.0),
            str(n),
        )
    )
    kept = {account_id}
    kept.update(others[: max(0, max_nodes - 1)])
    return kept


def _build_sankey_data(account_id: str, entry: _GraphCacheEntry) -> dict:
    """Build lightweight top-N inbound and outbound flow summaries for Plotly Sankey."""
    graph = entry.graph
    inbound: list[dict] = []
    for src, _, attrs in graph.in_edges(account_id, data=True):
        inbound.append(
            {
                "account_id": str(src),
                "amount": round(float(attrs.get("total_amount", 0.0)), 2),
                "txn_count": int(attrs.get("txn_count", 1)),
                "risk_tier": entry.node_risk_tiers.get(str(src), "LOW"),
                "risk_score": round(entry.node_risk_scores.get(str(src), 0.0), 2),
            }
        )
    inbound.sort(key=lambda r: r["amount"], reverse=True)

    outbound: list[dict] = []
    for _, dst, attrs in graph.out_edges(account_id, data=True):
        outbound.append(
            {
                "account_id": str(dst),
                "amount": round(float(attrs.get("total_amount", 0.0)), 2),
                "txn_count": int(attrs.get("txn_count", 1)),
                "risk_tier": entry.node_risk_tiers.get(str(dst), "LOW"),
                "risk_score": round(entry.node_risk_scores.get(str(dst), 0.0), 2),
            }
        )
    outbound.sort(key=lambda r: r["amount"], reverse=True)

    return {
        "focal_account": str(account_id),
        "focal_tier": entry.node_risk_tiers.get(str(account_id), "LOW"),
        "inbound": inbound[:MAX_SANKEY_BRANCHES],
        "outbound": outbound[:MAX_SANKEY_BRANCHES],
    }


def _extract_timeline_events(
    account_id: str,
    df: pd.DataFrame,
    entry: _GraphCacheEntry,
) -> list[dict]:
    """Slice chronologically ordered inbound/outbound transactions for `account_id`."""
    key = str(account_id)
    in_pos = entry.dest_rows.get(key)
    out_pos = entry.orig_rows.get(key)

    frames: list[pd.DataFrame] = []
    if in_pos is not None and len(in_pos):
        sub_in = df.iloc[in_pos].copy()
        sub_in["direction"] = "INBOUND"
        sub_in["counterparty"] = sub_in["nameOrig"].astype(str)
        frames.append(sub_in)
    if out_pos is not None and len(out_pos):
        sub_out = df.iloc[out_pos].copy()
        sub_out["direction"] = "OUTBOUND"
        sub_out["counterparty"] = sub_out["nameDest"].astype(str)
        frames.append(sub_out)

    if not frames:
        return []

    combined = pd.concat(frames, ignore_index=True)
    if "timestamp" in combined.columns:
        combined = combined.sort_values("timestamp", kind="mergesort")
    if len(combined) > MAX_TIMELINE_EVENTS:
        combined = combined.tail(MAX_TIMELINE_EVENTS)

    directions = combined["direction"].astype(str).tolist()
    counterparties = combined["counterparty"].astype(str).tolist()
    amounts = combined["amount"].astype(float).tolist()
    timestamps = (
        combined["timestamp"].astype(str).tolist()
        if "timestamp" in combined.columns
        else [str(i + 1) for i in range(len(combined))]
    )
    txn_ids = (
        combined["txn_id"].astype(str).tolist()
        if "txn_id" in combined.columns
        else [f"STEP-{i + 1}" for i in range(len(combined))]
    )
    risk_tiers = (
        combined["Risk_Tier"].astype(str).str.upper().tolist()
        if "Risk_Tier" in combined.columns
        else [entry.node_risk_tiers.get(cp, "LOW") for cp in counterparties]
    )
    risk_scores = (
        combined["Risk_Score"].astype(float).tolist()
        if "Risk_Score" in combined.columns
        else [entry.node_risk_scores.get(cp, 0.0) for cp in counterparties]
    )

    events: list[dict] = []
    for step_idx, (direction, cp, amt, ts, tid, tier, score) in enumerate(
        zip(directions, counterparties, amounts, timestamps, txn_ids, risk_tiers, risk_scores),
        start=1,
    ):
        events.append(
            {
                "step": step_idx,
                "timestamp": ts,
                "direction": direction,
                "counterparty": cp,
                "amount": round(amt, 2),
                "txn_id": tid,
                "risk_tier": tier,
                "risk_score": round(score, 2),
            }
        )
    return events


def get_account_timeline_data(
    account_id: str,
    df: pd.DataFrame,
    cache_key: object | None = None,
) -> list[dict]:
    """Return ordered inbound/outbound timeline events for single-account Plotly charts."""
    entry = _get_graph_entry(df, cache_key=cache_key)
    if account_id not in entry.graph:
        return []
    return _extract_timeline_events(account_id, df, entry)


def _edge_visual_style(
    src: str,
    dst: str,
    attrs: dict,
    account_id: str,
    direct_in: set[str],
    direct_out: set[str],
    entry: _GraphCacheEntry,
) -> tuple[str, str]:
    """Return (edge_color, hop_direction_label) for inbound, outbound, or 2-hop layering."""
    max_risk = float(attrs.get("max_risk", 0.0))
    if dst == account_id:
        hop_label = "1-Hop Inbound Credit"
        color = HIGH_RISK_COLOR if max_risk >= HIGH_RISK_THRESHOLD else INBOUND_EDGE_COLOR
    elif src == account_id:
        hop_label = "1-Hop Outbound Debit"
        color = HIGH_RISK_COLOR if max_risk >= HIGH_RISK_THRESHOLD else OUTBOUND_EDGE_COLOR
    elif src in direct_in or dst in direct_in:
        hop_label = "2-Hop Upstream Feed"
        color = (
            HIGH_RISK_COLOR
            if (max_risk >= HIGH_RISK_THRESHOLD or src in entry.high_risk_accounts)
            else INBOUND_EDGE_COLOR
        )
    else:
        hop_label = "2-Hop Downstream Layering"
        color = (
            HIGH_RISK_COLOR
            if (max_risk >= HIGH_RISK_THRESHOLD or dst in entry.high_risk_accounts)
            else OUTBOUND_EDGE_COLOR
        )
    return color, hop_label


def _render_pyvis_html(
    account_id: str,
    visual_sub: nx.DiGraph,
    full_graph: nx.DiGraph,
    entry: _GraphCacheEntry,
    enable_physics: bool = False,
    dark_mode: bool = True,
    layout_mode: str = "force",
) -> str:
    """Render PyVis HTML directly in memory with star/diamond hierarchy, curved edges, and 6-color theme."""
    from pyvis.network import Network

    bg_color = "#071226" if dark_mode else "#F8FAFC"
    font_color = "#FFFFFF" if dark_mode else "#0A1931"
    focal_border = FOCAL_BORDER_DARK if dark_mode else FOCAL_BORDER_LIGHT
    norm_layout = "hierarchical" if str(layout_mode).lower() == "hierarchical" else "force"

    net = Network(
        height="530px",
        width="100%",
        directed=True,
        bgcolor=bg_color,
        font_color=font_color,
        cdn_resources="remote",
    )

    options: dict = {
        "edges": {
            "smooth": {"enabled": True, "type": "dynamic", "roundness": 0.45},
            "arrows": {"to": {"enabled": True, "scaleFactor": 0.7}},
        },
        "interaction": {"hideEdgesOnDrag": True, "tooltipDelay": 80, "hover": True},
    }
    if norm_layout == "hierarchical":
        options["layout"] = {
            "hierarchical": {
                "enabled": True,
                "direction": "LR",
                "sortMethod": "directed",
                "levelSeparation": 220,
                "nodeSpacing": 125,
                "treeSpacing": 150,
            }
        }
        options["physics"] = {
            "enabled": True,
            "hierarchicalRepulsion": {
                "nodeDistance": 140,
                "springLength": 145,
                "damping": 0.2,
            },
            "stabilization": {
                "enabled": True,
                "iterations": STABILIZATION_ITERATIONS,
                "updateInterval": 25,
                "fit": True,
            },
        }
    else:
        options["physics"] = {
            "enabled": True,
            "barnesHut": {
                "gravitationalConstant": -6200,
                "centralGravity": 0.28,
                "springLength": 145,
                "springConstant": 0.04,
                "damping": 0.16,
            },
            "stabilization": {
                "enabled": True,
                "iterations": STABILIZATION_ITERATIONS,
                "updateInterval": 25,
                "fit": True,
            },
        }
    net.set_options(json.dumps(options))

    direct_in = set(full_graph.predecessors(account_id))
    direct_out = set(full_graph.successors(account_id))
    hop1_nodes = direct_in | direct_out

    for node in visual_sub.nodes:
        in_deg = full_graph.in_degree(node)
        out_deg = full_graph.out_degree(node)
        asymmetry = _degree_asymmetry(in_deg, out_deg)
        is_high = node in entry.high_risk_accounts
        tier = entry.node_risk_tiers.get(node, "HIGH" if is_high else "LOW")
        is_focus = node == account_id
        vol = entry.node_volumes.get(node, 0.0)
        safe_node = html.escape(str(node))
        hop_dist = 0 if is_focus else (1 if node in hop1_nodes else 2)

        if is_focus:
            node_bg = FOCAL_NODE_COLOR
            node_border = focal_border
            shape = "star"
            size = max(32.0, min(48.0, 22.0 + 3.2 * math.log10(vol + 1.0)))
            shadow = {
                "enabled": True,
                "color": "rgba(79, 70, 229, 0.78)",
                "size": 18,
                "x": 0,
                "y": 0,
            }
        else:
            if is_high:
                node_bg = HIGH_RISK_COLOR
                node_border = "#FCA5A5" if dark_mode else "#991B1B"
                shape = "diamond"
            elif tier == "MEDIUM":
                node_bg = MEDIUM_RISK_COLOR
                node_border = "#FDE68A" if dark_mode else "#B45309"
                shape = "dot"
            else:
                node_bg = LOW_RISK_COLOR
                node_border = "#FFFFFF" if dark_mode else "#0047AB"
                shape = "dot"
            size = max(11.0, min(32.0, 8.0 + 2.6 * math.log10(vol + 1.0)))
            shadow = {"enabled": False}

        net.add_node(
            node,
            label=node,
            shape=shape,
            color={
                "background": node_bg,
                "border": node_border,
                "highlight": {"background": FOCAL_NODE_COLOR, "border": "#FFFFFF"},
            },
            borderWidth=4 if is_focus else 2,
            size=size,
            shadow=shadow,
            title=(
                f"{safe_node}\n"
                f"Role: {'Focal Subject' if is_focus else f'{hop_dist}-Hop Neighbor'}\n"
                f"Risk Tier: {tier}\n"
                f"Total INR Volume: INR {vol:,.2f}\n"
                f"In-Degree: {in_deg} | Out-Degree: {out_deg} ({asymmetry:+.2f})"
            ),
        )

    for src, dst, attrs in visual_sub.edges(data=True):
        amt = float(attrs.get("total_amount", 0.0))
        cnt = int(attrs.get("txn_count", 1))
        edge_color, hop_label = _edge_visual_style(
            src, dst, attrs, account_id, direct_in, direct_out, entry
        )
        edge_tier = _tier_from_score(float(attrs.get("max_risk", 0.0)))
        edge_width = max(1.3, min(7.5, 1.0 + 0.85 * math.log10(amt + 1.0)))
        net.add_edge(
            src,
            dst,
            width=edge_width,
            color={"color": edge_color, "highlight": "#98E6C3"},
            title=(
                f"{html.escape(str(src))} -> {html.escape(str(dst))}\n"
                f"INR Amount: INR {amt:,.2f} ({cnt} txn)\n"
                f"Risk Tier: {edge_tier}\n"
                f"Path: {hop_label}"
            ),
        )

    raw_html = net.generate_html()
    if not enable_physics:
        marker = "network = new vis.Network(container, data, options);"
        static_hook = (
            f"{marker}\n"
            '                  network.once("stabilizationIterationsDone", function() { network.setOptions({ physics: false }); });'
        )
        if marker in raw_html:
            return raw_html.replace(marker, static_hook, 1)
    return raw_html


def build_account_subgraph(
    account_id: str,
    df: pd.DataFrame,
    output_path: str = "data/network.html",
    save_html: bool = False,
    cache_key: object | None = None,
    max_nodes: int = MAX_VISUAL_NODES,
    enable_physics: bool = False,
    dark_mode: bool = True,
    layout_mode: str = "force",
) -> dict:
    """Extract 2-hop neighbourhood of `account_id`, compute metrics, Sankey/timeline data, and PyVis HTML."""
    import networkx as nx

    entry = _get_graph_entry(df, cache_key=cache_key)
    graph = entry.graph
    if account_id not in graph:
        raise ValueError(f"Account not found in transaction graph: {account_id}")

    ego_nodes = set(nx.ego_graph(entry.undirected, account_id, radius=HOP_RADIUS).nodes)
    full_sub = graph.subgraph(ego_nodes)

    in_deg = graph.in_degree(account_id)
    out_deg = graph.out_degree(account_id)
    asymmetry = _degree_asymmetry(in_deg, out_deg)
    full_high_risk = sorted(n for n in ego_nodes if n in entry.high_risk_accounts)

    effective_max_nodes = max(5, int(max_nodes))
    visual_nodes = _select_visual_nodes(
        account_id, full_sub, entry.undirected, entry, effective_max_nodes
    )
    visual_sub = full_sub.subgraph(visual_nodes)
    norm_layout = "hierarchical" if str(layout_mode).lower() == "hierarchical" else "force"

    html_content = _render_pyvis_html(
        account_id,
        visual_sub,
        graph,
        entry,
        enable_physics=enable_physics,
        dark_mode=dark_mode,
        layout_mode=norm_layout,
    )

    resolved_out = ""
    if save_html:
        out_file = Path(output_path)
        if not out_file.is_absolute():
            out_file = PROJECT_ROOT / out_file
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(html_content, encoding="utf-8")
        resolved_out = str(out_file)

    return {
        "account_id": account_id,
        "num_nodes": full_sub.number_of_nodes(),
        "num_edges": full_sub.number_of_edges(),
        "in_degree": in_deg,
        "out_degree": out_deg,
        "degree_asymmetry": asymmetry,
        "topology": _topology_label(in_deg, out_deg, asymmetry),
        "high_risk_node_count": len(full_high_risk),
        "high_risk_nodes": full_high_risk,
        "output_path": resolved_out,
        "html_content": html_content,
        "rendered_nodes": visual_sub.number_of_nodes(),
        "rendered_edges": visual_sub.number_of_edges(),
        "pruned": visual_sub.number_of_nodes() < full_sub.number_of_nodes(),
        "layout_mode": norm_layout,
        "sankey_data": _build_sankey_data(account_id, entry),
        "timeline_data": _extract_timeline_events(account_id, df, entry),
    }
