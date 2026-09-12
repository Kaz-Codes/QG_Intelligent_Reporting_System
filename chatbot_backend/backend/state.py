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

    # --- planning ---
    # The WHOLE-TURN standalone question, set ONCE by planning_agent and never
    # touched again - used for response_agent's "User question" framing and
    # anything else that needs "what did the user actually ask this turn",
    # regardless of which subtask is currently in flight.
    turn_query: str
    # The CURRENT question in flight - for a single-subtask turn this equals
    # turn_query, but dispatch_subtask overwrites it with each subtask's own
    # `description` as it dispatches them, so resolve_item/context/knowledge/
    # generate_sql/analytics_agent - everything that reads "the question to
    # work on right now" - see only that subtask's own narrower question, not
    # the whole compound one. Without this, a subtask scoped to "resin" would
    # still be handed "compare resin and hardener" as its literal business
    # question, and a SQL model asked that question reasonably writes a query
    # comparing both - exactly the bug this field exists to prevent.
    rewritten_query: str
    route: str                  # data | docs | smalltalk | clarify
    intent: str
    domain: str
    entities: Dict[str, Any]
    clarification_question: str
    clarification_options: List[str]

    # --- subtask planning ---
    # A turn can name more than one thing to analyse ("forecast cast iron NA
    # and shell scrap separately"). `subtasks` is the planner's ordered
    # decomposition (each {"description": str, "items": List[str]}), set once
    # per turn by the planner node and consumed by dispatch_subtask, which
    # pops one at a time and drives the SAME resolve_item -> ... -> forecast
    # chain used for a single-item turn, once per subtask. `subtask_results`
    # accumulates one snapshot per finished subtask (its own sql/rows/
    # forecast_result/item_context/etc., written by collect_subtask_result)
    # for response_agent to synthesise into ONE final answer. Both are
    # turn-level - they persist across the whole loop and are wiped only by
    # fresh_turn(), never by fresh_subtask().
    subtasks: List[Dict[str, Any]]
    subtask_results: List[Dict[str, Any]]
    # The ONE subtask currently in flight (popped off `subtasks` by
    # dispatch_subtask), so collect_subtask_result knows what description to
    # label its snapshot with. Like `entities`, set directly by
    # dispatch_subtask - not part of fresh_subtask()'s blanket reset.
    current_subtask: Dict[str, Any]

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

    # Raw analysis_type/forecast_needed/period_column/value_column/.../charts
    # decision, made in the SAME call that writes the SQL (see sql_agent.py's
    # GeneratedSQL) - or, on a cache hit, restored from the cached entry (see
    # query_cache.py). analytics_agent reads this and VALIDATES it against the
    # rows the query actually returned rather than calling the LLM again; only
    # falls back to a fresh call when this is empty (e.g. a pre-merge cache
    # entry with no analysis fields stored) or the prediction can't be
    # repaired. Per-subtask scratch, like `sql`/`retrieved_data`.
    predicted_analysis: Dict[str, Any]

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
        "turn_query": "",
        "rewritten_query": "",
        "route": "",
        "intent": "",
        "domain": "",
        "entities": {},
        "clarification_question": "",
        "clarification_options": [],
        "subtasks": [],
        "subtask_results": [],
        "current_subtask": {},
        "predicted_analysis": {},
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


def fresh_subtask() -> Dict[str, Any]:
    """
    Per-SUBTASK scratch fields, cleared at the start of every loop iteration
    inside dispatch_subtask (see graph/workflow.py) - the same idea as
    fresh_turn() one level down.

    Without this, subtask 2 would inherit subtask 1's SQL, rows, forecast
    result, item_context etc. and either silently answer with stale data or
    have analytics/forecast decisions contaminated by the previous subtask's
    shape. `subtasks` and `subtask_results` are NOT here on purpose - they are
    turn-level accumulators that must survive the whole loop, reset only by
    fresh_turn(). `entities` and `current_subtask` are ALSO deliberately not
    here: dispatch_subtask sets both itself - entities rebuilt as
    {**turn_level_entities, "item": subtask["items"]}, because a blanket reset
    here cannot know the turn-level entities or which subtask is next (see
    workflow.py's dispatch_subtask for why a plain entities["item"] overwrite
    is not enough - a prior subtask's resolved entities["item_code"] would
    otherwise leak into the next one), and current_subtask set to whichever
    subtask was just popped, for collect_subtask_result to label its snapshot.
    """
    return {
        "predicted_analysis": {},
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
        "context": [],
        "knowledge_inferred": False,
        "knowledge_confident": False,
        "knowledge_notes": [],
        "item_context": [],
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
        # Set by generate_sql when it declines a subtask outright ("the
        # schema cannot answer this"). NOT the same lifetime as the OTHER use
        # of this field - planning_agent's own understanding failure, which sets
        # it before dispatch_subtask/fresh_subtask ever runs and is caught by
        # route_after_understanding immediately, never reaching this reset.
        # Safe to clear here: a subtask-1 failure must not leak into
        # response_agent's view of subtask 2/3 succeeding.
        "error": "",
    }
