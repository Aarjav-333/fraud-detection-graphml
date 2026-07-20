from sqlalchemy import Column, Integer, String, Float
from app.database import Base


class GraphMetric(Base):
    __tablename__ = "graph_metrics"

    id = Column(Integer, primary_key=True, index=True)
    account_uid = Column(String, unique=True, index=True, nullable=False)
    in_degree = Column(Integer, default=0)          # distinct senders paying this account
    out_degree = Column(Integer, default=0)         # distinct receivers this account pays
    total_received = Column(Float, default=0.0)
    total_sent = Column(Float, default=0.0)
    degree_centrality = Column(Float, default=0.0)
    pagerank = Column(Float, default=0.0)
    component_id = Column(Integer, default=-1)
    component_size = Column(Integer, default=0)
    community_id = Column(Integer, default=-1)
    community_size = Column(Integer, default=0)
    in_cycle = Column(Integer, default=0)           # part of a short directed cycle
