"""Features available before a transaction's fraud outcome is known."""

from __future__ import annotations

from collections import defaultdict

import networkx as nx
import numpy as np
import pandas as pd

TYPES = ("CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER")
BASE_COLUMNS = [
    "amount", "oldbalanceOrg", "oldbalanceDest", "amount_to_origin_balance",
    "amount_to_dest_balance", "hour_sin", "hour_cos", "dest_is_merchant",
    *[f"type_{kind}" for kind in TYPES],
]
GRAPH_COLUMNS = [
    "sender_degree", "receiver_degree", "sender_pagerank", "receiver_pagerank",
    "shared_counterparties", "ring_flag", "same_component_flag",
    "sender_component_size", "receiver_component_size", "sender_fraud_rate",
    "receiver_fraud_rate",
]


def base_features(data: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=data.index)
    amount = data.amount.astype(float)
    origin_balance = data.oldbalanceOrg.astype(float)
    dest_balance = data.oldbalanceDest.astype(float)
    out["amount"] = np.log1p(amount.clip(lower=0))
    out["oldbalanceOrg"] = np.log1p(origin_balance.clip(lower=0))
    out["oldbalanceDest"] = np.log1p(dest_balance.clip(lower=0))
    out["amount_to_origin_balance"] = np.minimum(amount / (origin_balance + 1), 1_000_000)
    out["amount_to_dest_balance"] = np.minimum(amount / (dest_balance + 1), 1_000_000)
    hour = data.step.astype(float) % 24
    out["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    out["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    out["dest_is_merchant"] = data.nameDest.str.startswith("M").astype(int)
    for kind in TYPES:
        out[f"type_{kind}"] = (data.type == kind).astype(int)
    return out[BASE_COLUMNS].astype("float32")


class TemporalGraph:
    """Build graph features from strictly earlier PaySim steps.

    Labels update neighborhood rates only for the training window. Structural snapshots
    for PageRank and components refresh periodically; degree and edge checks are live.
    """

    def __init__(self, snapshot_interval: int = 168) -> None:
        self.graph = nx.DiGraph()
        self.labeled_count: dict[str, int] = defaultdict(int)
        self.fraud_count: dict[str, int] = defaultdict(int)
        self.snapshot_interval = snapshot_interval
        self.snapshot_step = 0
        self.pagerank: dict[str, float] = {}
        self.component: dict[str, int] = {}
        self.component_size: dict[int, int] = {}

    def refresh(self, step: int) -> None:
        if self.graph.number_of_nodes():
            self.pagerank = nx.pagerank(self.graph, alpha=0.85, max_iter=30, tol=1e-3)
            self.component.clear()
            self.component_size.clear()
            for component_id, nodes in enumerate(nx.weakly_connected_components(self.graph)):
                size = len(nodes)
                self.component_size[component_id] = size
                self.component.update(dict.fromkeys(nodes, component_id))
        self.snapshot_step = step

    def _neighbors(self, node: str) -> set[str]:
        if node not in self.graph:
            return set()
        return set(self.graph.predecessors(node)) | set(self.graph.successors(node))

    def row_features(self, sender: str, receiver: str) -> tuple[float, ...]:
        g = self.graph
        sender_neighbors = self._neighbors(sender)
        receiver_neighbors = self._neighbors(receiver)
        shared = len(sender_neighbors & receiver_neighbors)
        sender_component = self.component.get(sender)
        receiver_component = self.component.get(receiver)
        return (
            float(g.degree(sender)) if sender in g else 0.0,
            float(g.degree(receiver)) if receiver in g else 0.0,
            self.pagerank.get(sender, 0.0), self.pagerank.get(receiver, 0.0),
            float(shared), float(shared > 0),
            float(sender_component is not None and sender_component == receiver_component),
            float(self.component_size.get(sender_component, 0)),
            float(self.component_size.get(receiver_component, 0)),
            self.fraud_count.get(sender, 0) / self.labeled_count[sender]
            if self.labeled_count.get(sender, 0) else 0.0,
            self.fraud_count.get(receiver, 0) / self.labeled_count[receiver]
            if self.labeled_count.get(receiver, 0) else 0.0,
        )

    def transform(self, data: pd.DataFrame, learn_labels: bool = False, update_graph: bool = True) -> pd.DataFrame:
        rows: list[tuple[float, ...]] = []
        order: list = []
        for step, batch in data.groupby("step", sort=True, observed=True):
            step = int(step)
            if step - self.snapshot_step >= self.snapshot_interval:
                self.refresh(step)
            senders = batch.nameOrig.astype(str).tolist()
            receivers = batch.nameDest.astype(str).tolist()
            rows.extend(self.row_features(sender, receiver) for sender, receiver in zip(senders, receivers))
            order.extend(batch.index)
            if update_graph:
                # All edges from the same step arrive after all predictions for that step.
                self.graph.add_edges_from(zip(senders, receivers))
                if learn_labels:
                    for sender, receiver, label in zip(senders, receivers, batch.isFraud):
                        for node in (sender, receiver):
                            self.labeled_count[node] += 1
                            self.fraud_count[node] += int(label)
        # Rows come out in step order; reindex so callers may pass unsorted frames.
        features = pd.DataFrame(rows, index=order, columns=GRAPH_COLUMNS, dtype="float32")
        return features.reindex(data.index)

    def score_rows(self, data: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame(
            [self.row_features(str(sender), str(receiver)) for sender, receiver in zip(data.nameOrig, data.nameDest)],
            index=data.index, columns=GRAPH_COLUMNS, dtype="float32",
        )
