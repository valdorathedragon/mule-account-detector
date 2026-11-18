"""2-hop transaction network extraction, topology metrics and PyVis HTML export."""

import html
import math
from pathlib import Path
import networkx as nx
import pandas as pd
from pyvis.network import Network

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HIGH_RISK_COLOR = "#ef4444"
NORMAL_COLOR = "#22d3ee"
HIGH_RISK_THRESHOLD = 80.0
HOP_RADIUS = 2
EPSILON = 1e-5


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


def _high_risk_accounts(df: pd.DataFrame) -> set[str]:
    """Identify HIGH-risk accounts using the same rule as analyze_account():
    max outgoing Risk_Score, falling back to max incoming Risk_Score for receive-only accounts.
    """
    if "Risk_Score" in df.columns:
        orig_scores = df.groupby(df["nameOrig"].astype(str))["Risk_Score"].max()
        dest_scores = df.groupby(df["nameDest"].astype(str))["Risk_Score"].max()
        receive_only = dest_scores.drop(labels=orig_scores.index, errors="ignore")
        return set(orig_scores[orig_scores >= HIGH_RISK_THRESHOLD].index) | set(
            receive_only[receive_only >= HIGH_RISK_THRESHOLD].index
        )

    if "is_mule_label" in df.columns:
        flagged = df[df["is_mule_label"] == 1]
        orig_nodes = set(flagged["nameOrig"].astype(str))
        receive_only_nodes = set(flagged["nameDest"].astype(str)) - set(df["nameOrig"].astype(str))
        return orig_nodes | receive_only_nodes

    return set()


def _build_full_graph(df: pd.DataFrame) -> nx.DiGraph:
    """Aggregate parallel transactions into weighted directed edges."""
    agg_spec = {"total_amount": ("amount", "sum"), "txn_count": ("amount", "size")}
    if "Risk_Score" in df.columns:
        agg_spec["max_risk"] = ("Risk_Score", "max")
    edges = df.groupby(["nameOrig", "nameDest"], as_index=False).agg(**agg_spec)

    graph = nx.DiGraph()
    for row in edges.itertuples(index=False):
        graph.add_edge(
            str(row.nameOrig),
            str(row.nameDest),
            total_amount=float(row.total_amount),
            txn_count=int(row.txn_count),
            max_risk=float(getattr(row, "max_risk", 0.0)),
        )
    return graph


def build_account_subgraph(
    account_id: str, df: pd.DataFrame, output_path: str = "data/network.html"
) -> dict:
    """Extract the 2-hop neighbourhood of `account_id`, compute metrics and export HTML."""
    graph = _build_full_graph(df)
    if account_id not in graph:
        raise ValueError(f"Account not found in transaction graph: {account_id}")

    hop_nodes = nx.ego_graph(graph.to_undirected(as_view=True), account_id, radius=HOP_RADIUS).nodes
    subgraph = graph.subgraph(hop_nodes).copy()
    high_risk = _high_risk_accounts(df)

    net = Network(
        height="650px",
        width="100%",
        directed=True,
        bgcolor="#0f172a",
        font_color="#e2e8f0",
        cdn_resources="remote",
    )
    net.barnes_hut(gravity=-6000, spring_length=140)

    node_metrics: dict[str, dict] = {}
    for node in subgraph.nodes:
        in_deg, out_deg = graph.in_degree(node), graph.out_degree(node)
        asymmetry = _degree_asymmetry(in_deg, out_deg)
        is_high = node in high_risk
        node_metrics[node] = {
            "in_degree": in_deg,
            "out_degree": out_deg,
            "degree_asymmetry": asymmetry,
            "high_risk": is_high,
        }
        is_focus = node == account_id
        safe_node = html.escape(str(node))
        net.add_node(
            node,
            label=node,
            color={"background": HIGH_RISK_COLOR if is_high else NORMAL_COLOR,
                   "border": "#facc15" if is_focus else "#1e293b"},
            borderWidth=4 if is_focus else 1,
            size=(34 if is_focus else 12) + 2 * min(in_deg + out_deg, 10),
            title=(
                f"{safe_node}\nRisk: {'HIGH' if is_high else 'NORMAL'}\n"
                f"In-degree: {in_deg} | Out-degree: {out_deg}\n"
                f"Degree asymmetry: {asymmetry:+.4f}"
            ),
        )

    for src, dst, attrs in subgraph.edges(data=True):
        net.add_edge(
            src,
            dst,
            value=math.log10(attrs["total_amount"] + 1.0),
            color=HIGH_RISK_COLOR if attrs["max_risk"] >= HIGH_RISK_THRESHOLD else "#475569",
            title=f"INR {attrs['total_amount']:,.2f} across {attrs['txn_count']} txn(s)",
        )

    out_file = Path(output_path)
    if not out_file.is_absolute():
        out_file = PROJECT_ROOT / out_file
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(net.generate_html(), encoding="utf-8")

    focus = node_metrics[account_id]
    return {
        "account_id": account_id,
        "num_nodes": subgraph.number_of_nodes(),
        "num_edges": subgraph.number_of_edges(),
        "in_degree": focus["in_degree"],
        "out_degree": focus["out_degree"],
        "degree_asymmetry": focus["degree_asymmetry"],
        "topology": _topology_label(focus["in_degree"], focus["out_degree"], focus["degree_asymmetry"]),
        "high_risk_node_count": sum(1 for m in node_metrics.values() if m["high_risk"]),
        "high_risk_nodes": sorted(n for n, m in node_metrics.items() if m["high_risk"]),
        "output_path": str(out_file),
    }
