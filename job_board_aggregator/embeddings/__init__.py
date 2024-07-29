"""Embeddings package for job board aggregator."""

# Pinecone integrated embedding (production system)
from job_board_aggregator.embeddings.vector_store_integrated import VectorStoreIntegrated

__all__ = ["VectorStoreIntegrated"]