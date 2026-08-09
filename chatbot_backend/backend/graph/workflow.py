"""
The LangGraph workflow.

    understand ─┬─ smalltalk ──────────────────────► respond
                ├─ clarify ────────────────────────► respond
                ├─ docs ──► retrieve_docs ─────────► respond
                └─ data ──► resolve_item ──► same-name item(s)?
                                                │  ambiguous
                                                │  └─► respond (clarify + table)
                                                │  resolved / none
                                                └──► context ──► knowledge found?
                                                                   │  no
                                                                   │  └─► knowledge ──► confident?
                                                                   │  yes                │  no
                                                                   │                      │  └─► respond (clarify)
                                                                   │                      │  yes
                                                                   └──────────────────────┴─► generate_sql
                                                                                                  │
                                                              ┌── retry ×N ───────────────────────┤
                                                              ▼                                    ▼
                                                         generate_sql ◄───────────────────────execute_sql
                                                                                                  │ ok
                                                                                                  ▼
                                                                        analyze ──► forecast ──► respond
                                                                               └──────────────► respond

Five things worth noting:

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
* execute_sql loops back to generate_sql on failure, up to SQL_MAX_RETRIES,
  feeding the database's own error message back to the model. This is what
  makes text-to-SQL usable against a real schema.
* The forecast node only runs when the analytics agent says the data actually
  supports one - a trend line on "current stock of item X" is meaningless.
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
from backend.agents.query_agent import query_agent
from backend.agents.rag_agent import rag_agent
from backend.agents.response_agent import response_agent
from backend.agents.sql_agent import execute_sql, generate_sql
from backend.config import SQL_MAX_RETRIES
from backend.state import ChatState


# --- routing ---------------------------------------------------------
def route_after_understanding(state: ChatState) -> str:
    """Send the question down one of the four paths."""
    route = state.get("route", "data")

    if route == "docs":
        return "retrieve_docs"
    if route == "teach":
        return "learn"
    if route == "clarify":
        return "respond"
    if state.get("error"):
        # Understanding failed outright - do not attempt SQL on a question we
        # did not parse.
        return "respond"
    if route == "smalltalk":
        # Smalltalk only goes through context to pick up taught facts about the
        # assistant itself ("who created you"); it never writes SQL, so it has
        # no item to resolve.
        return "context"
    # data: check for a same-name/different-item_code item before context, so
    # an ambiguous item is caught before the term lookup or SQL is written.
    return "resolve_item"


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
    """Retry the query, give up, or move on to analysis."""
    if state.get("error"):
        # generate_sql decided the schema cannot answer this.
        return "respond"

    if state.get("sql_error"):
        if state.get("sql_attempts", 0) <= SQL_MAX_RETRIES:
            return "generate_sql"
        return "respond"

    # The query ran fine but returned nothing, and the zero-row guard wants one
    # more attempt with the empty result as evidence. execute_sql sets this at
    # most once per turn and generate_sql clears it, so this cannot loop.
    if state.get("zero_row_hint"):
        return "generate_sql"

    return "analyze"


def route_after_analysis(state: ChatState) -> str:
    """Forecast, run a generated computation, or answer directly."""
    # The forecast node also owns the reorder / purchase-timing calculation,
    # which does not need a projection to be possible - so a "when must I buy
    # this" question routes here even when the series is too short to forecast.
    if state.get("forecast_needed") or (state.get("forecast_spec") or {}).get("reorder_analysis"):
        return "forecast"
    if state.get("needs_computation"):
        return "compute"
    return "respond"


# --- graph -----------------------------------------------------------
def build_graph(checkpointer=None):
    """
    Compile the workflow.

    Pass a checkpointer to get conversation memory. The API passes an
    InMemorySaver today; swap it for a Postgres saver to survive restarts
    (see backend/graph/memory.py).
    """
    workflow = StateGraph(ChatState)

    workflow.add_node("understand", query_agent)
    workflow.add_node("resolve_item", item_resolution_agent)
    workflow.add_node("context", context_agent)
    workflow.add_node("knowledge", knowledge_agent)
    workflow.add_node("generate_sql", generate_sql)
    workflow.add_node("execute_sql", execute_sql)
    workflow.add_node("analyze", analytics_agent)
    workflow.add_node("forecast", forecast_agent)
    workflow.add_node("compute", compute_agent)
    workflow.add_node("retrieve_docs", rag_agent)
    workflow.add_node("learn", learn_agent)
    workflow.add_node("respond", response_agent)

    workflow.set_entry_point("understand")

    workflow.add_conditional_edges(
        "understand",
        route_after_understanding,
        {
            "context": "context",
            "resolve_item": "resolve_item",
            "retrieve_docs": "retrieve_docs",
            "learn": "learn",
            "respond": "respond",
        },
    )

    workflow.add_edge("learn", "respond")

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
        {"generate_sql": "generate_sql", "analyze": "analyze", "respond": "respond"},
    )

    workflow.add_conditional_edges(
        "analyze",
        route_after_analysis,
        {"forecast": "forecast", "compute": "compute", "respond": "respond"},
    )

    workflow.add_edge("forecast", "respond")
    workflow.add_edge("compute", "respond")
    workflow.add_edge("retrieve_docs", "respond")
    workflow.add_edge("respond", END)

    return workflow.compile(checkpointer=checkpointer)


# Compiled without memory - fine for scripts and tests. The API builds its own
# with a checkpointer attached.
graph = build_graph()
