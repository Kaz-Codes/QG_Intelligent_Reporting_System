"""
Conversation memory.

LangGraph stores conversation state in a checkpointer, keyed by thread_id. Send
the same thread_id with every message from a chat session and the graph reloads
that thread's history automatically - that is what makes follow-ups like
"what about last month" work.

Today this is in-process memory, which is lost on restart and not shared across
workers. To persist, install langgraph-checkpoint-postgres and swap
get_checkpointer() over to PostgresSaver using config.DATABASE_URL - nothing
else in the codebase has to change.
"""

from functools import lru_cache

try:  # langgraph >= 0.2 renamed MemorySaver
    from langgraph.checkpoint.memory import InMemorySaver as _Saver
except ImportError:  # pragma: no cover - older langgraph
    from langgraph.checkpoint.memory import MemorySaver as _Saver


@lru_cache(maxsize=1)
def get_checkpointer():
    """Process-wide checkpointer. Cached so every request shares one store."""
    return _Saver()
