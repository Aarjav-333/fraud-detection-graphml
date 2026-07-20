"""Build the transaction network (workflow Step 7).

Accounts = nodes. Transactions = directed edges, aggregated per (sender, receiver)
with total amount and count, so the graph stays compact even with many transactions.
"""
import networkx as nx
from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.models.account import Account


def build_graph(db: Session) -> nx.DiGraph:
    G = nx.DiGraph()
    for uid, name, risk in db.query(Account.account_uid, Account.customer_name, Account.risk_level):
        G.add_node(uid, name=name, risk=risk)

    rows = db.query(
        Transaction.sender_uid, Transaction.receiver_uid, Transaction.amount,
    ).all()
    for sender, receiver, amount in rows:
        if G.has_edge(sender, receiver):
            e = G[sender][receiver]
            e["amount"] += amount
            e["count"] += 1
        else:
            G.add_edge(sender, receiver, amount=float(amount), count=1)
    return G
