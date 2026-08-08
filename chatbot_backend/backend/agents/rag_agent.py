"""
Document RAG agent.

Handles the questions the database cannot answer - policy, process, definitions
("what does ALC mean", "what is our LC retirement process"). The router sends
these here instead of down the SQL path.

Load company documents into the store with vector_tools.add_documents(kind="doc").
"""

from backend.config import RAG_TOP_K
from backend.tools import vector_tools


def rag_agent(state: dict) -> dict:
    question = state.get("rewritten_query") or state.get("user_query", "")

    documents = vector_tools.search(question, top_k=RAG_TOP_K)

    if not documents:
        return {
            "documents": [],
            "error": "No documents matched this question.",
        }

    return {"documents": documents}
