"""
Query Understanding agent - the entry node of the graph.

Rewrites the latest message into a standalone question using the conversation
history, then classifies it: which path it should take, what the user wants,
and which business entities were named.

It answers nothing. Everything downstream reads `rewritten_query`, so a failure
here quietly degrades to using the raw question rather than breaking the graph.
"""

from typing import Dict, List, Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from backend.agents.item_resolution_agent import _we_asked_this
from backend.config import EFFORT_FAST, structured_llm
from backend.prompts.query_prompt import QUERY_SYSTEM_PROMPT, build_query_prompt
from backend.state import fresh_turn

HISTORY_TURNS = 6  # enough for follow-ups, short enough to stay cheap


class QueryUnderstanding(BaseModel):
    """Structured result the router and SQL agent depend on."""

    rewritten_query: str = Field(
        description="The question rewritten to stand alone, with pronouns resolved."
    )
    route: Literal["data", "docs", "smalltalk", "clarify", "teach"] = Field(
        description="Which path this question should take."
    )
    intent: str = Field(description="Short phrase describing what the user wants.")
    domain: str = Field(description="Business domain the question belongs to.")
    entities: Dict[str, str] = Field(
        default_factory=dict,
        description="Business entities named in the question. Only what was said.",
    )
    clarification_question: Optional[str] = Field(
        default=None,
        description="Set only when route is 'clarify'.",
    )
    clarification_options: List[str] = Field(
        default_factory=list,
        description=(
            "Tappable answer choices for the clarification, when there is a small "
            "fixed set (e.g. date-scope or Imports/Exports). Empty for free-text."
        ),
    )


def _format_history(messages: List, limit: int = HISTORY_TURNS) -> str:
    """Render the recent turns as plain text for the prompt."""
    recent = messages[-limit:] if messages else []
    lines = []
    for message in recent:
        role = "User" if message.type == "human" else "Assistant"
        lines.append(f"{role}: {message.content}")
    return "\n".join(lines)


def query_agent(state: dict) -> dict:
    user_query = state.get("user_query", "")

    # The current turn is already in messages; drop it so it is not shown twice.
    history = _format_history(state.get("messages", [])[:-1])

    # A bare reply like "11997-60" or "all of them" carries no information of
    # its own - recognising it as an answer to item_resolution_agent's "which
    # one did you mean" question requires seeing THAT question and the item
    # name it was about, which only lives in the previous turn's state, not in
    # this message. Asking the LLM to notice this connection on its own proved
    # unreliable in testing (it re-asked instead of resolving), stranding the
    # conversation right after the user did exactly what was asked. Detect it
    # deterministically instead - same check item_resolution_agent uses to
    # confirm it was ITS question being answered - and force the turn back
    # onto the "data" path with the original item name restored; the actual
    # exact/"all"/descriptive-reply resolution is unchanged, still done by
    # item_resolution_agent itself.
    prior_item = (state.get("entities") or {}).get("item")
    answering_item_clarify = bool(
        prior_item and state.get("route") == "clarify" and _we_asked_this(state, prior_item)
    )

    try:
        llm = structured_llm(QueryUnderstanding, effort=EFFORT_FAST)
        result = llm.invoke(
            [
                SystemMessage(content=QUERY_SYSTEM_PROMPT),
                HumanMessage(content=build_query_prompt(user_query, history)),
            ]
        )
    except Exception as exc:
        # Understanding is an optimisation, not a requirement - fall through to
        # the data path with the raw question rather than failing the turn.
        return {
            **fresh_turn(),
            "rewritten_query": user_query,
            "route": "data",
            "domain": "General",
            "entities": {"item": prior_item} if answering_item_clarify else {},
            "error": f"Query understanding failed: {exc}",
        }

    route = result.route
    entities = dict(result.entities)
    if answering_item_clarify:
        route = "data"
        entities.setdefault("item", prior_item)

    # This is the first node of every turn, so it is where the previous turn's
    # scratch state gets wiped. See state.fresh_turn().
    return {
        **fresh_turn(),
        "rewritten_query": result.rewritten_query or user_query,
        "route": route,
        "intent": result.intent,
        "domain": result.domain,
        "entities": entities,
        "clarification_question": result.clarification_question or "",
        # Only meaningful on the clarify route; harmless otherwise.
        "clarification_options": result.clarification_options if route == "clarify" else [],
    }
