"""
The LangGraph workflow.

    plan ────────┬─ smalltalk ──────────────────────► respond
                ├─ clarify ────────────────────────► respond
                ├─ docs ──► retrieve_docs ─────────► respond
                └─ data ──► dispatch_subtask ◄──────────────────────────────┐
                               │        ▲                                   │
                               │        └── more subtasks? ─────────────────┤
                               │ next subtask                     collect_subtask_result
                               ▼                                            ▲
                          resolve_item ──► same-name item(s)?               │
                                              │  ambiguous                  │
                                              │  └─► respond (clarify+table)│
                                              │  resolved / none            │
                                              └──► context ──► knowledge found?
                                                                 │  no      │
                                                                 │  └─► knowledge ──► confident?
                                                                 │  yes                │  no
                                                                 │                      │  └─► respond (clarify)
                                                                 │                      │  yes
                                                                 └──────────────────────┴─► generate_sql
                                                                                                │
                                                            ┌── retry ×N ─────────────────────┤
                                                            ▼                                  ▼
                                                       generate_sql ◄─────────────────────execute_sql
                                                                                                │ ok / hard failure
                                                                                                ▼
                                                    analyze ──► forecast ──► collect_subtask_result
                                                           └─────────────────────► collect_subtask_result
                          once the subtask queue is empty: dispatch_subtask ──► respond

Six things worth noting:

* Every "data" turn runs through the subtask loop, even a single-item one.
  `plan` (backend/agents/planning_agent.py) always populates `subtasks` with
  at least one entry - most questions decompose to exactly one; a compound
  one ("forecast A and B separately") can decompose to several, per
  planning_prompt.py's DECOMPOSITION rules. dispatch_subtask pops one subtask
  at a time, resets the per-subtask scratch fields (state.fresh_subtask()),
  and rebuilds `entities` from the turn-level dict rather than merely
  overwriting entities["item"] - a prior subtask's resolved item_code must
  never leak into the next subtask's resolution or SQL.
* A CLARIFY (ambiguous item, low-confidence term mapping) short-circuits the
  WHOLE TURN straight to respond, not just the current subtask - deliberately.
  planning_agent.py's follow-up-answer detection only understands one flat,
  turn-level `entities["item"]` list (the union of every subtask's items), not
  "which subtask was mid-flight", so a mid-loop clarify discards any already-
  finished subtasks for this turn; they're simply recomputed fresh once the
  user answers - the same stateless pattern item resolution already used
  before subtasks existed, and the reason a partial multi-subtask turn is not
  resumed.
* A hard SQL failure for ONE subtask (SQL_MAX_RETRIES exhausted, or
  generate_sql declining outright) does NOT abort the turn - it's recorded via
  collect_subtask_result and the loop continues, so one unanswerable part
  doesn't cost the user the other subtasks' answers.
* resolve_item catches items whose name is shared by more than one item_code
  (different specs). It asks which one(s) are wanted - via the same clarify
  route as any other confirmation - with the matching rows attached so the
  normal table rendering shows them right away. A follow-up reply is resolved
  fresh each turn, the same stateless pattern as the date-scope gate below.
* When the knowledge base has nothing on the question, the knowledge node
  derives the term-to-column mapping from the raw schema. A CONFIDENT
  derivation rejoins generate_sql; anything less (a guess, or nothing derivable
  at all) asks the user to confirm rather than quietly guessing - the graph
  would rather ask than answer on a shaky assumption.
* SQL_ROW_LIMIT defaults to 0 (no cap) - the user sees every matching row in a
  scrollable, sortable, searchable table rather than a silent top-100.

Conversation memory is the checkpointer: pass a thread_id in the config and
LangGraph reloads that thread's `messages` automatically.
"""

from langgraph.graph import END, StateGraph

from backend.agents.analytics_agent import analytics_agent, forecast_agent
from backend.agents.compute_agent import compute_agent
from backend.agents.context_agent import context_agent
from backend.agents.item_resolution_agent import item_resolution_agent
from backend.agents.knowledge_agent import knowledge_agent
from backend.agents.learn_agent import learn_agent
from backend.agents.planning_agent import planning_agent
from backend.agents.rag_agent import rag_agent
from backend.agents.response_agent import response_agent
from backend.agents.sql_agent import execute_sql, generate_sql
from backend.config import SQL_MAX_RETRIES
from backend.observability import log_plan_complete, log_subtask_done, log_subtask_start
from backend.state import ChatState, fresh_subtask


# --- subtask loop ------------------------------------------------------
# A turn can name more than one thing to analyse. `plan` always populates
# `subtasks` with at least one entry - most questions decompose to exactly
# one; see planning_agent.py / planning_prompt.py for when a compound one
# decomposes to several. dispatch_subtask pops one at a time and sends it
# through the SAME resolve_item -> ... -> forecast/compute chain a single-item
# turn always used; collect_subtask_result snapshots what that chain produced
# and loops back for the next one, or on to respond once the queue is empty.
def dispatch_subtask(state: ChatState) -> dict:
    """
    Load the next subtask into the per-subtask scratch fields, or signal an
    empty queue (current_subtask == {}) so route_after_dispatch sends the turn
    on to respond.

    Rebuilds `entities` from the turn-level dict rather than merely
    overwriting entities["item"] - a prior subtask's resolved entities
    ["item_code"] must not leak into the next subtask's resolution or SQL.
    See state.fresh_subtask()'s docstring for why this can't be folded into
    that blanket reset.

    ALSO overwrites `rewritten_query` AND `intent` with this subtask's own
    values. Without this, resolve_item/context/knowledge/generate_sql/
    analytics_agent - everything downstream that reads "the question to work
    on right now" - kept seeing the WHOLE compound question and its intent for
    every subtask, never the narrower ones it was actually dispatched for.
    That is exactly how "forecast resin next quarter" (a subtask scoped to
    entities["item"]=["resin"]) still got handed "Compare the forecasted
    demand for resin and hardener next quarter" as its literal business
    question AND "compare forecasted demand" as its intent, and reasonably
    wrote a query comparing both categories - the entities were scoped, the
    QUESTION TEXT AND INTENT were not. `turn_query` (set once by
    planning_agent, untouched here) keeps the true whole-turn question
    available for response_agent's framing.

    `entities["comparison"]` is dropped for a subtask with fewer than 2 items
    of its own, for the same reason: a "comparison" entity is definitionally
    about MULTIPLE things set against each other, and only makes sense on a
    subtask that itself KEPT multiple items together (see planning_prompt.py's
    DECOMPOSITION) - one split apart to stand alone must not carry the
    original multi-item framing forward into its own, single-item SQL.
    """
    subtasks = list(state.get("subtasks") or [])
    if not subtasks:
        done = len(state.get("subtask_results") or [])
        if done:
            log_plan_complete(done)
        return {"current_subtask": {}}

    next_subtask, remaining = subtasks[0], subtasks[1:]
    subtask_items = next_subtask.get("items") or []

    turn_entities = dict(state.get("entities") or {})
    turn_entities.pop("item_code", None)
    if len(subtask_items) < 2:
        turn_entities.pop("comparison", None)
    entities = {**turn_entities, "item": subtask_items}

    total = len(state.get("subtask_results") or []) + len(subtasks)
    index = len(state.get("subtask_results") or []) + 1
    log_subtask_start(index, total, next_subtask)

    return {
        **fresh_subtask(),
        "subtasks": remaining,
        "current_subtask": next_subtask,
        "entities": entities,
        "rewritten_query": next_subtask.get("description") or state.get("turn_query", ""),
        "intent": next_subtask.get("intent") or state.get("intent", ""),
    }


def route_after_dispatch(state: ChatState) -> str:
    """Start the subtask chain, or finish the loop once nothing is left."""
    return "resolve_item" if state.get("current_subtask") else "respond"


def collect_subtask_result(state: ChatState) -> dict:
    """
    Snapshot the just-finished subtask's scratch fields into subtask_results,
    then hand control back to dispatch_subtask for the next one.

    A hard SQL failure (SQL_MAX_RETRIES exhausted, or generate_sql declining
    outright) still lands here rather than aborting the whole turn - one
    subtask failing is recorded and explained, it doesn't cost the user the
    other subtasks' answers. A CLARIFY (ambiguous item, low-confidence term
    mapping) is different and deliberately NOT routed here - see
    route_after_item_resolution/route_after_knowledge: it short-circuits
    straight to respond for the whole turn, because the follow-up-answer
    detection in planning_agent.py only understands one flat, turn-level item
    list, not which subtask was mid-flight.
    """
    subtask = state.get("current_subtask") or {}
    snapshot = {
        "description": subtask.get("description", ""),
        "items": subtask.get("items", []),
        "sql": state.get("sql", ""),
        "sql_explanation": state.get("sql_explanation", ""),
        "sql_error": state.get("sql_error", ""),
        "retrieved_data": state.get("retrieved_data", []),
        "columns": state.get("columns", []),
        "row_count": state.get("row_count", 0),
        "truncated": state.get("truncated", False),
        "item_context": state.get("item_context", []),
        "context": state.get("context", []),
        "analysis_type": state.get("analysis_type", ""),
        "focus_points": state.get("focus_points", []),
        "charts": state.get("charts", []),
        "forecast_result": state.get("forecast_result", {}),
        "forecast_skipped_reason": state.get("forecast_skipped_reason", ""),
        "reorder_result": state.get("reorder_result", {}),
        "computation_result": state.get("computation_result"),
        "computation_explanation": state.get("computation_explanation", ""),
        "computation_error": state.get("computation_error", ""),
        "error": state.get("error", ""),
    }
    results = state.get("subtask_results") or []
    total = len(results) + 1 + len(state.get("subtasks") or [])
    log_subtask_done(len(results) + 1, total, snapshot)
    return {"subtask_results": [*results, snapshot]}


# --- routing ---------------------------------------------------------
def route_after_planning(state: ChatState) -> str:
    """Send the question down one of the four paths."""
    route = state.get("route", "data")

    if route == "docs":
        return "retrieve_docs"
    if route == "teach":
        return "learn"
    if route == "clarify":
        return "respond"
    if state.get("error"):
        # Planning failed outright - do not attempt SQL on a question we did
        # not parse.
        return "respond"
    if route == "smalltalk":
        # Smalltalk only goes through context to pick up taught facts about the
        # assistant itself ("who created you"); it never writes SQL, so it has
        # no item to resolve.
        return "context"
    # data: `plan` always populates `subtasks` with at least one entry for
    # this route, so hand off to the subtask loop rather than resolve_item
    # directly - dispatch_subtask loads the first (often only) subtask's item
    # list and starts the same resolve_item -> ... chain a single-item turn
    # always used.
    return "dispatch_subtask"


def route_after_item_resolution(state: ChatState) -> str:
    """Ask about the item (clarify), or continue on to the term lookup."""
    if state.get("route") == "clarify":
        return "respond"
    return "context"


def route_after_context(state: ChatState) -> str:
    """
    Knowledge found? (data path) - or just answer (smalltalk).

    Smalltalk only came through context to pick up taught facts; it never writes
    SQL, so it goes straight on to respond. For the data path, an empty context
    means nothing documented cleared the relevance threshold, so derive the
    mapping with the Knowledge Agent instead of writing SQL blind.
    """
    if state.get("route") == "smalltalk":
        return "respond"
    return "generate_sql" if state.get("context") else "knowledge"


def route_after_knowledge(state: ChatState) -> str:
    """Ask about the uncertain mapping (clarify), or proceed to write SQL."""
    if state.get("route") == "clarify":
        return "respond"
    return "generate_sql"


def route_after_execution(state: ChatState) -> str:
    """Retry the query, give up on THIS subtask, or move on to analysis."""
    if state.get("error"):
        # generate_sql decided the schema cannot answer this subtask - record
        # it and let the loop try any remaining subtasks rather than losing
        # the whole turn over one unanswerable part.
        return "collect_subtask_result"

    if state.get("sql_error"):
        if state.get("sql_attempts", 0) <= SQL_MAX_RETRIES:
            return "generate_sql"
        return "collect_subtask_result"

    # The query ran fine but returned nothing, and the zero-row guard wants one
    # more attempt with the empty result as evidence. execute_sql sets this at
    # most once per turn and generate_sql clears it, so this cannot loop.
    if state.get("zero_row_hint"):
        return "generate_sql"

    return "analyze"


def route_after_analysis(state: ChatState) -> str:
    """Forecast, run a generated computation, or this subtask is done."""
    # The forecast node also owns the reorder / purchase-timing calculation,
    # which does not need a projection to be possible - so a "when must I buy
    # this" question routes here even when the series is too short to forecast.
    if state.get("forecast_needed") or (state.get("forecast_spec") or {}).get("reorder_analysis"):
        return "forecast"
    if state.get("needs_computation"):
        return "compute"
    return "collect_subtask_result"


# --- graph -----------------------------------------------------------
def build_graph(checkpointer=None):
    """
    Compile the workflow.

    Pass a checkpointer to get conversation memory. The API passes an
    InMemorySaver today; swap it for a Postgres saver to survive restarts
    (see backend/graph/memory.py).
    """
    workflow = StateGraph(ChatState)

    workflow.add_node("plan", planning_agent)
    workflow.add_node("dispatch_subtask", dispatch_subtask)
    workflow.add_node("resolve_item", item_resolution_agent)
    workflow.add_node("context", context_agent)
    workflow.add_node("knowledge", knowledge_agent)
    workflow.add_node("generate_sql", generate_sql)
    workflow.add_node("execute_sql", execute_sql)
    workflow.add_node("analyze", analytics_agent)
    workflow.add_node("forecast", forecast_agent)
    workflow.add_node("compute", compute_agent)
    workflow.add_node("collect_subtask_result", collect_subtask_result)
    workflow.add_node("retrieve_docs", rag_agent)
    workflow.add_node("learn", learn_agent)
    workflow.add_node("respond", response_agent)

    workflow.set_entry_point("plan")

    workflow.add_conditional_edges(
        "plan",
        route_after_planning,
        {
            "context": "context",
            "dispatch_subtask": "dispatch_subtask",
            "retrieve_docs": "retrieve_docs",
            "learn": "learn",
            "respond": "respond",
        },
    )

    workflow.add_edge("learn", "respond")

    workflow.add_conditional_edges(
        "dispatch_subtask",
        route_after_dispatch,
        {"resolve_item": "resolve_item", "respond": "respond"},
    )

    workflow.add_conditional_edges(
        "resolve_item",
        route_after_item_resolution,
        {"respond": "respond", "context": "context"},
    )

    workflow.add_conditional_edges(
        "context",
        route_after_context,
        {"generate_sql": "generate_sql", "knowledge": "knowledge", "respond": "respond"},
    )

    workflow.add_conditional_edges(
        "knowledge",
        route_after_knowledge,
        {"respond": "respond", "generate_sql": "generate_sql"},
    )
    workflow.add_edge("generate_sql", "execute_sql")

    workflow.add_conditional_edges(
        "execute_sql",
        route_after_execution,
        {
            "generate_sql": "generate_sql",
            "analyze": "analyze",
            "collect_subtask_result": "collect_subtask_result",
        },
    )

    workflow.add_conditional_edges(
        "analyze",
        route_after_analysis,
        {
            "forecast": "forecast",
            "compute": "compute",
            "collect_subtask_result": "collect_subtask_result",
        },
    )

    workflow.add_edge("forecast", "collect_subtask_result")
    workflow.add_edge("compute", "collect_subtask_result")
    workflow.add_edge("collect_subtask_result", "dispatch_subtask")
    workflow.add_edge("retrieve_docs", "respond")
    workflow.add_edge("respond", END)

    return workflow.compile(checkpointer=checkpointer)


# Compiled without memory - fine for scripts and tests. The API builds its own
# with a checkpointer attached.
graph = build_graph()
