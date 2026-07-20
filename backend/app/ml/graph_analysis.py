"""Analyze the transaction network (workflow Step 8).

Computes per-account:
  degree centrality, PageRank, in/out degree, totals,
  weakly-connected component id/size, Louvain community id/size,
  and membership in short directed cycles (length <= 3).
Persists everything into the graph_metrics table.
"""
import networkx as nx
from sqlalchemy.orm import Session

from app.ml.graph_build import build_graph
from app.models.graph_metric import GraphMetric

CYCLE_LENGTH_BOUND = 3


def analyze(db: Session) -> dict:
    G = build_graph(db)
    n, m = G.number_of_nodes(), G.number_of_edges()

    degree_centrality = nx.degree_centrality(G)
    pagerank = nx.pagerank(G, weight="amount")

    # weakly connected components
    comp_id, comp_size = {}, {}
    for i, comp in enumerate(nx.weakly_connected_components(G)):
        for node in comp:
            comp_id[node] = i
            comp_size[node] = len(comp)
    n_components = i + 1 if n else 0

    # Louvain communities (on the undirected projection)
    community_id, community_size = {}, {}
    communities = nx.community.louvain_communities(G.to_undirected(), seed=42)
    for i, com in enumerate(communities):
        for node in com:
            community_id[node] = i
            community_size[node] = len(com)

    # short directed cycles (money loops): 2-cycles and 3-cycles via set intersection.
    # (nx.simple_cycles is far too slow on ~80k edges; this is equivalent for length <= 3)
    succ = {u: set(G.successors(u)) for u in G.nodes}
    pred = {u: set(G.predecessors(u)) for u in G.nodes}
    cycle_nodes = set()
    n_cycles = 0
    for u, v in G.edges:
        if u < v and u in succ[v]:          # 2-cycle u <-> v (count once)
            n_cycles += 1
            cycle_nodes.update((u, v))
    triangle_count = 0
    for u, v in G.edges:
        common = succ[v] & pred[u]
        common.discard(u); common.discard(v)
        if common:
            cycle_nodes.add(u); cycle_nodes.add(v)
            cycle_nodes.update(common)
            triangle_count += len(common)
    n_cycles += triangle_count // 3         # each triangle seen once per edge

    # per-node money totals
    total_sent = {u: 0.0 for u in G.nodes}
    total_received = {u: 0.0 for u in G.nodes}
    for u, v, data in G.edges(data=True):
        total_sent[u] += data["amount"]
        total_received[v] += data["amount"]

    # persist
    db.query(GraphMetric).delete()
    rows = [
        dict(
            account_uid=node,
            in_degree=G.in_degree(node),
            out_degree=G.out_degree(node),
            total_received=round(total_received[node], 2),
            total_sent=round(total_sent[node], 2),
            degree_centrality=round(degree_centrality.get(node, 0.0), 6),
            pagerank=round(pagerank.get(node, 0.0), 8),
            component_id=comp_id.get(node, -1),
            component_size=comp_size.get(node, 0),
            community_id=community_id.get(node, -1),
            community_size=community_size.get(node, 0),
            in_cycle=1 if node in cycle_nodes else 0,
        )
        for node in G.nodes
    ]
    for i in range(0, len(rows), 1000):
        db.bulk_insert_mappings(GraphMetric, rows[i:i + 1000])
    db.commit()

    return {
        "nodes": n,
        "edges": m,
        "components": n_components,
        "largest_component": max(comp_size.values()) if comp_size else 0,
        "communities": len(communities),
        "cycles_found": n_cycles,
        "accounts_in_cycles": len(cycle_nodes),
    }


def neighborhood(db: Session, account_uid: str, hops: int = 1, max_nodes: int = 60) -> dict:
    """Return the local subgraph around an account for visualization."""
    G = build_graph(db)
    if account_uid not in G:
        return {"nodes": [], "links": [], "found": False}

    UG = G.to_undirected()
    nodes = {account_uid}
    frontier = {account_uid}
    for _ in range(hops):
        nxt = set()
        for u in frontier:
            nxt.update(UG.neighbors(u))
        nodes |= nxt
        frontier = nxt
        if len(nodes) > max_nodes:
            break
    nodes = set(list(nodes)[:max_nodes]) | {account_uid}

    sub = G.subgraph(nodes)
    return {
        "found": True,
        "center": account_uid,
        "nodes": [
            {"id": u, "name": G.nodes[u].get("name", u), "risk": G.nodes[u].get("risk", "Low"),
             "is_center": u == account_uid}
            for u in sub.nodes
        ],
        "links": [
            {"source": u, "target": v, "amount": round(d["amount"], 2), "count": d["count"]}
            for u, v, d in sub.edges(data=True)
        ],
    }
