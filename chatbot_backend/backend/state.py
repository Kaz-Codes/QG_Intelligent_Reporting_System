"""
Shared state passed between every node in the LangGraph workflow.

One TypedDict written by many nodes. `total=False` means a node only returns
the keys it actually changed and LangGraph merges the rest, so nodes never
have to carry the whole state forward.

`messages` uses LangGraph's add_messages reducer, so returning new messages
appends to the conversation instead of replacing it.
"""

from typing import Optional, Annotated, Any, Dict, List, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class ChatState(TypedDict, total=False):
    # --- conversation ---
    messages: Annotated[List[AnyMessage], add_messages]
    user_query: str

    # --- query understanding ---
    rewritten_query: str        # follow-ups resolved against history
    route: str                  # data | docs | smalltalk | clarify
    intent: str
    domain: str
    entities: Dict[str, Any]
    clarification_question: str
    clarification_options: List[str]

    # --- business context (schema + terminology retrieval) ---
    # Who is asking. Set by the API from the session cookie, and used to
    # scope learned terms: one user's teaching must not answer another
    # user's question.
    user_id: Optional[int]

    context: List[str]
    knowledge_inferred: bool    # True when the Knowledge Agent had to derive it
    knowledge_confident: bool
    knowledge_notes: List[str]  # raw inferred mapping notes, for persistence

    # --- item resolution (which item_code(s) a named item resolved to) ---
    # Deliberately separate from `context`: route_after_context uses whether
    # `context` is non-empty to decide if the Knowledge Agent's schema-derivation
    # fallback is needed. If item_resolution_agent's pin note lived in `context`
    # too, resolving an unambiguous item would make that check pass even when no
    # business terminology was actually found, silently skipping the fallback.
    item_context: List[str]

    # --- teaching (user defines a term) ---
    taught_ok: bool
    taught_term: Dict[str, Any]
    taught_confirmation: str

    # --- SQL path ---
    sql: str
    sql_explanation: str
    tables_used: List[str]
    limit_is_user_requested: bool  # True only when a LIMIT reflects an explicit top-N ask
    sql_error: str
    sql_attempts: int
    retrieved_data: List[Dict[str, Any]]
    columns: List[str]
    row_count: int
    truncated: bool
    # True when the query was replayed from the query cache rather than written
    # fresh - a repeat question then cannot drift, and the SQL call is skipped.
    sql_from_cache: bool
    # Which cache entry was replayed. Carried so the zero-row guard can evict
    # THAT entry precisely: the cache can hit via the embedding near-match path,
    # where the stored question is worded differently from this turn's, so
    # forgetting by question text silently removes nothing (and, when it does
    # match, ignores entities and can remove a different item's entry).
    sql_cache_fingerprint: str
    # The zero-row guard. `zero_row_hint` carries the feedback for one more
    # attempt and is cleared by generate_sql; `zero_row_retried` makes sure that
    # second chance is only ever given once per turn.
    zero_row_hint: str
    zero_row_retried: bool

    # --- document RAG path ---
    documents: List[str]

    # --- analytics / forecasting ---
    analysis_type: str          # reporting | aggregation | trend | forecast | recommendation
    focus_points: List[str]     # specific things the answer should call out
    charts: List[Dict[str, Any]]  # list of {type, x, y[], title} for the UI, or []
    forecast_needed: bool
    forecast_skipped_reason: str
    forecast_spec: Dict[str, Any]   # period_column / value_column / periods_ahead
    forecast_result: Dict[str, Any]
    reorder_result: Dict[str, Any]  # when to reorder / projected stockout date

    # --- dynamic computation (code interpreter) ---
    needs_computation: bool
    computation_task: str
    computation_code: str           # the Python the model wrote and ran
    computation_explanation: str
    computation_result: Any         # whatever the code produced (JSON-safe)
    computation_error: str
    computation_attempts: int

    # --- output ---
    final_response: str
    error: str


def fresh_turn() -> Dict[str, Any]:
    """
    Per-turn scratch fields, cleared at the start of every turn.

    The checkpointer keeps the whole state alive across turns so `messages`
    survives. Everything else is scratch: without this reset a follow-up
    question inherits the previous turn's rows, SQL and errors, and the
    response agent answers the new question using the old data.

    `messages` and `user_query` are deliberately not in here.
    """
    return {
        "rewritten_query": "",
        "route": "",
        "intent": "",
        "domain": "",
        "entities": {},
        "clarification_question": "",
        "clarification_options": [],
        "context": [],
        "knowledge_inferred": False,
        "knowledge_confident": False,
        "knowledge_notes": [],
        "item_context": [],
        "taught_ok": False,
        "taught_term": {},
        "taught_confirmation": "",
        "sql": "",
        "sql_explanation": "",
        "tables_used": [],
        "limit_is_user_requested": False,
        "sql_error": "",
        "sql_attempts": 0,
        "retrieved_data": [],
        "columns": [],
        "row_count": 0,
        "truncated": False,
        "sql_from_cache": False,
        "sql_cache_fingerprint": "",
        "zero_row_hint": "",
        "zero_row_retried": False,
        "documents": [],
        "analysis_type": "",
        "focus_points": [],
        "charts": [],
        "forecast_needed": False,
        "forecast_skipped_reason": "",
        "forecast_spec": {},
        "forecast_result": {},
        "reorder_result": {},
        "needs_computation": False,
        "computation_task": "",
        "computation_code": "",
        "computation_explanation": "",
        "computation_result": None,
        "computation_error": "",
        "computation_attempts": 0,
        "final_response": "",
        "error": "",
    }
