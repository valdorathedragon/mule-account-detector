"""2-hop transaction network extraction, topology metrics, visual pruning and PyVis HTML export."""

from collections import OrderedDict
from dataclasses import dataclass
import html
import json
import math
from pathlib import Path
import networkx as nx
import pandas as pd
from pyvis.network import Network

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HIGH_RISK_COLOR = "#ef4444"
MEDIUM_RISK_COLOR = "#6D28D9"
NORMAL_COLOR = "#0047AB"
FOCAL_BORDER_DARK = "#98E6C3"
FOCAL_BORDER_LIGHT = "#4F46E5"
HIGH_RISK_THRESHOLD = 80.0
MEDIUM_RISK_THRESHOLD = 50.0
HOP_RADIUS = 2
EPSILON = 1e-5
MAX_VISUAL_NODES = 65
STABILIZATION_ITERATIONS = 80
GRAPH_CACHE_MAXSIZE = 4


@dataclass(frozen=True)
class _GraphCacheEntry:
    """Cached full transaction graph and precomputed per-account risk scores/tiers."""

    graph: nx.DiGraph
    undirected: nx.Graph
    node_risk_scores: dict[str, float]
    node_risk_tiers: dict[str, str]
    high_risk_accounts: set[str]


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
    """Return cached full DiGraph + undirected view + node risk maps, or build once."""
    key = _df_cache_key(df, cache_key=cache_key)
    cached = _GRAPH_CACHE.get(key)
    if cached is not None:
        _GRAPH_CACHE.move_to_end(key)
        return cached

    graph = _build_full_graph(df)
    undirected = graph.to_undirected()
    scores, tiers, high_risk = _compute_node_risk_maps(df)
    entry = _GraphCacheEntry(
        graph=graph,
        undirected=undirected,
        node_risk_scores=scores,
        node_risk_tiers=tiers,
        high_risk_accounts=high_risk,
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


def _render_pyvis_html(
    account_id: str,
    visual_sub: nx.DiGraph,
    full_graph: nx.DiGraph,
    entry: _GraphCacheEntry,
    enable_physics: bool = False,
    dark_mode: bool = True,
) -> str:
    """Render PyVis HTML directly in memory with configurable physics and 6-color theme."""
    bg_color = "#0A1931" if dark_mode else "#FFFFFF"
    font_color = "#FFFFFF" if dark_mode else "#0A1931"
    edge_default_color = "#4F46E5" if dark_mode else "#94A3B8"
    focal_border = FOCAL_BORDER_DARK if dark_mode else FOCAL_BORDER_LIGHT

    net = Network(
        height="500px",
        width="100%",
        directed=True,
        bgcolor=bg_color,
        font_color=font_color,
        cdn_resources="remote",
    )
    options = {
        "physics": {
            "enabled": True,
            "barnesHut": {
                "gravitationalConstant": -6000,
                "centralGravity": 0.3,
                "springLength": 140,
                "springConstant": 0.04,
                "damping": 0.15,
            },
            "stabilization": {
                "enabled": True,
                "iterations": STABILIZATION_ITERATIONS,
                "updateInterval": 25,
                "fit": True,
            },
        },
        "interaction": {"hideEdgesOnDrag": True, "tooltipDelay": 100},
    }
    net.set_options(json.dumps(options))

    for node in visual_sub.nodes:
        in_deg = full_graph.in_degree(node)
        out_deg = full_graph.out_degree(node)
        asymmetry = _degree_asymmetry(in_deg, out_deg)
        is_high = node in entry.high_risk_accounts
        tier = entry.node_risk_tiers.get(node, "HIGH" if is_high else "LOW")
        is_focus = node == account_id
        safe_node = html.escape(str(node))

        if is_high:
            node_bg = HIGH_RISK_COLOR
        elif tier == "MEDIUM":
            node_bg = MEDIUM_RISK_COLOR
        else:
            node_bg = NORMAL_COLOR

        if is_focus:
            node_border = focal_border
        elif dark_mode and not is_high:
            node_border = "#98E6C3"
        else:
            node_border = "#4F46E5"

        net.add_node(
            node,
            label=node,
            color={
                "background": node_bg,
                "border": node_border,
            },
            borderWidth=4 if is_focus else 1,
            size=(34 if is_focus else 12) + 2 * min(in_deg + out_deg, 10),
            title=(
                f"{safe_node}\nRisk: {tier}\n"
                f"In-degree: {in_deg} | Out-degree: {out_deg}\n"
                f"Degree asymmetry: {asymmetry:+.4f}"
            ),
        )

    for src, dst, attrs in visual_sub.edges(data=True):
        net.add_edge(
            src,
            dst,
            value=math.log10(attrs["total_amount"] + 1.0),
            color=HIGH_RISK_COLOR if attrs["max_risk"] >= HIGH_RISK_THRESHOLD else edge_default_color,
            title=f"INR {attrs['total_amount']:,.2f} across {attrs['txn_count']} txn(s)",
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
) -> dict:
    """Extract the 2-hop neighbourhood of `account_id`, compute metrics and render PyVis HTML."""
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
    html_content = _render_pyvis_html(
        account_id,
        visual_sub,
        graph,
        entry,
        enable_physics=enable_physics,
        dark_mode=dark_mode,
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
    }
