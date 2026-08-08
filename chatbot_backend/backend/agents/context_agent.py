"""
Business Context agent.

Sits between understanding and SQL generation. Its only job is to find what the
user's words *mean here* - that "consumption" means issuance.quantity over
from_date, that "reorder level" is calculated and not stored - and hand those
mappings to the SQL agent.

This is the retrieval that feeds SQL. The separate RAG agent
(backend/agents/rag_agent.py) answers document questions instead.
"""

from backend.config import RAG_TOP_K
from backend.tools import vector_tools


def context_agent(state: dict) -> dict:
    question = state.get("rewritten_query") or state.get("user_query", "")

    # Search on the question plus the extracted entities, so an item or status
    # name pulls in its own terminology entry too.
    entities = state.get("entities") or {}
    search_text = " ".join([question, *(str(v) for v in entities.values())])

    # Search curated terms AND previously-learned mappings, so a mapping the
    # Knowledge Agent inferred earlier is reused instead of re-derived.
    # search_context() ranks by trust, not raw distance: a curated term always
    # wins over a user-taught mapping, which always wins over a machine-inferred
    # one, so a noisy inferred guess cannot crowd out a documented answer just by
    # sitting closer in embedding space. Falls back to keyword matching over the
    # curated terms when the vector store is unavailable.
    context = vector_tools.search_context(search_text, top_k=RAG_TOP_K)

    return {"context": context}
