"""
Planning agent - the entry node of the graph.

Rewrites the latest message into a standalone question using the conversation
history, classifies it (route, intent, domain, entities), and - the part that
used to be a fixed one-subtask stub - DECOMPOSES it into `subtasks`: an
ordered list of independent parts, each with its own description and item
list, that the graph's subtask loop (dispatch_subtask/collect_subtask_result
in graph/workflow.py) runs one at a time through the SAME resolve_item -> ...
-> forecast chain a single-item turn always used. Most questions decompose to
exactly one subtask; see planning_prompt.py's DECOMPOSITION section for when
and why a compound question splits into more.

It answers nothing. Everything downstream reads `rewritten_query`/`subtasks`,
so a failure here quietly degrades to a single stub subtask covering the raw
question rather than breaking the graph.
"""

from typing import Dict, List, Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from backend.agents.item_resolution_agent import _as_item_list, _we_asked_this
from backend.config import EFFORT_FAST, structured_llm
from backend.observability import log_plan
from backend.prompts.planning_prompt import PLANNING_SYSTEM_PROMPT, build_planning_prompt
from backend.state import fresh_turn

HISTORY_TURNS = 6  # enough for follow-ups, short enough to stay cheap


class Subtask(BaseModel):
    description: str = Field(
        description=(
            "A standalone sub-question covering just this part - specific enough "
            "that a separate call, with no memory of the rest of the "
            "conversation, could act on it alone."
        )
    )
    intent: str = Field(
        default="",
        description=(
            "This subtask's OWN standalone intent, in a few words - e.g. "
            "'forecast resin demand', never 'compare forecasted demand'. A "
            "subtask that was SPLIT apart from a multi-item question is "
            "answered entirely on its own; its intent must not carry a "
            "comparison/combination framing that only made sense for the "
            "original, whole question. Only a subtask that KEEPS multiple "
            "items together (see DECOMPOSITION) may legitimately have a "
            "comparison-shaped intent."
        ),
    )
    items: List[str] = Field(
        default_factory=list,
        description=(
            "Item/material name(s) THIS subtask is about, one entry per item, "
            "never joined into a single combined string. Empty if this subtask "
            "names no specific item."
        ),
    )


class PlanningResult(BaseModel):
    """Structured result the router and every downstream agent depends on."""

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
    subtasks: List[Subtask] = Field(
        default_factory=list,
        description=(
            "The question decomposed into independent parts - see the "
            "DECOMPOSITION section. Never empty on the 'data' route, even for a "
            "question naming no item at all."
        ),
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


def _dedup_union(lists: List[List[str]]) -> List[str]:
    """Flatten several item lists into one, preserving first-seen order."""
    seen: List[str] = []
    for items in lists:
        for name in items:
            if name not in seen:
                seen.append(name)
    return seen


def planning_agent(state: dict) -> dict:
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
    # onto the "data" path with the original item name(s) restored; the actual
    # exact/"all"/descriptive-reply resolution is unchanged, still done by
    # item_resolution_agent itself.
    #
    # entities["item"] is a flat, turn-level LIST (the union of every
    # subtask's items - see below), but item_resolution_agent only ever asks
    # about ONE of them per turn - so find the one the prior clarify question
    # actually named, out of however many were on the table that turn.
    prior_items = _as_item_list((state.get("entities") or {}).get("item"))
    asked_item = next(
        (name for name in prior_items if _we_asked_this(state, name)), None
    )
    answering_item_clarify = bool(asked_item and state.get("route") == "clarify")

    try:
        llm = structured_llm(PlanningResult, effort=EFFORT_FAST)
        result = llm.invoke(
            [
                SystemMessage(content=PLANNING_SYSTEM_PROMPT),
                HumanMessage(content=build_planning_prompt(user_query, history)),
            ]
        )
    except Exception as exc:
        # Planning is an optimisation, not a requirement - fall through to the
        # data path with the raw question rather than failing the turn.
        fallback_items = prior_items if answering_item_clarify else []
        return {
            **fresh_turn(),
            "turn_query": user_query,
            "rewritten_query": user_query,
            "route": "data",
            "domain": "General",
            "entities": {"item": fallback_items} if fallback_items else {},
            "subtasks": [{"description": user_query, "items": fallback_items}],
            "error": f"Planning failed: {exc}",
        }

    route = result.route
    final_rewritten = result.rewritten_query or user_query
    subtasks = [
        {
            "description": s.description or final_rewritten,
            "items": _as_item_list(s.items),
            "intent": s.intent or result.intent,
        }
        for s in result.subtasks
    ]

    # entities["item"] stays a single FLAT list for the whole turn - the union
    # of every subtask's items - purely so the follow-up-answer detection
    # above (which has no notion of "which subtask") keeps working unchanged.
    entities = dict(result.entities)
    all_items = _dedup_union([st["items"] for st in subtasks])
    if all_items:
        entities["item"] = all_items

    if answering_item_clarify:
        route = "data"
        current = _as_item_list(entities.get("item"))
        if asked_item not in current:
            # The model's own rewrite/decomposition did not carry the item
            # being answered forward - force it back in, the same safety net
            # the single-item version always had, so the turn that just
            # resolved this ambiguity can never silently lose it. Added as
            # its own subtask rather than guessing which existing one it
            # belongs to.
            entities["item"] = [*current, asked_item] if current else prior_items
            subtasks.append({
                "description": final_rewritten,
                "items": [asked_item],
                "intent": result.intent,
            })

    # Never empty on the data route - even a question naming no item at all
    # still gets exactly one subtask covering the whole thing.
    if route == "data" and not subtasks:
        subtasks = [{
            "description": final_rewritten,
            "items": _as_item_list(entities.get("item")),
            "intent": result.intent,
        }]
    elif route != "data":
        subtasks = []

    log_plan(final_rewritten, route, subtasks)

    # This is the first node of every turn, so it is where the previous turn's
    # scratch state gets wiped. See state.fresh_turn().
    return {
        **fresh_turn(),
        "turn_query": final_rewritten,
        "rewritten_query": final_rewritten,
        "route": route,
        "intent": result.intent,
        "domain": result.domain,
        "entities": entities,
        "subtasks": subtasks,
        "clarification_question": result.clarification_question or "",
        # Only meaningful on the clarify route; harmless otherwise.
        "clarification_options": result.clarification_options if route == "clarify" else [],
    }
