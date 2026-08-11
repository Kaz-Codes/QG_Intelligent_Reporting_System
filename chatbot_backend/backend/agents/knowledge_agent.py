"""
Knowledge agent - the recovery path when the knowledge base comes up empty.

The Context Resolver looks the user's terms up in the vector store. When nothing
relevant comes back, the SQL agent would otherwise write its query with no idea
what the words mean here. This agent fills that gap by deriving the mapping from
the raw schema, writing it into `context` exactly as the resolver would have, and
handing control back to Generate SQL.

When it cannot derive a mapping at all, or can only guess between a few plausible
ones (confident=False), it does NOT quietly hand a guess to the SQL agent - it
asks the user to confirm, via the same clarify route as any other confirmation.
A confirmed reply on the next turn carries the clarification through the
rewritten question, which is usually enough for a second pass to be confident (and
if the resulting query then succeeds, the API persists it as a learned mapping -
so the same term is not re-asked next time). Only a CONFIDENT inference rejoins
Generate SQL directly.

Terms that land here repeatedly are the ones worth adding to
backend/metadata/business_terms.py - `knowledge_inferred` in the state marks them.
"""

from typing import List

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from backend.config import EFFORT_ACCURATE, structured_llm
from backend.metadata.schema import get_schema_text
from backend.tools.postgres_tools import find_items_by_name
from backend.prompts.knowledge_prompt import (
    KNOWLEDGE_SYSTEM_PROMPT,
    build_knowledge_prompt,
)


class InferredKnowledge(BaseModel):
    mapping_notes: List[str] = Field(
        default_factory=list,
        description="One note per business term: what it means and which column holds it.",
    )
    confident: bool = Field(
        default=False,
        description="False when the schema does not support the question or the mapping is a guess.",
    )


def knowledge_agent(state: dict) -> dict:
    question = state.get("rewritten_query") or state.get("user_query", "")
    entities = state.get("entities") or {}

    system_prompt = KNOWLEDGE_SYSTEM_PROMPT.format(schema=get_schema_text())

    try:
        llm = structured_llm(InferredKnowledge, effort=EFFORT_ACCURATE)
        result = llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(
                    content=build_knowledge_prompt(
                        question, state.get("intent", ""), state.get("entities", {})
                    )
                ),
            ]
        )
    except Exception:
        # Fall through to SQL generation with no context rather than failing the
        # turn - the SQL agent still has the full schema to work from.
        return {"context": [], "knowledge_inferred": True}

    notes = [note for note in result.mapping_notes if note.strip()]

    if not notes:
        return {
            "route": "clarify",
            "clarification_question": (
                "I couldn't find anything in our data that matches what you're "
                "asking. Could you rephrase it, or tell me which term or area "
                "you mean?"
            ),
            "context": [],
            "knowledge_inferred": True,
            "knowledge_confident": False,
        }

    if not result.confident:
        # Only a guess, not a documented or confident mapping - confirm before
        # spending a SQL attempt on it, rather than silently picking one.
        #
        # The notes must NOT go in the question. They are schema mapping notes
        # written for the SQL agent - full of table and column names, ILIKE
        # patterns and view names - and the clarify route short-circuits the
        # response agent, so whatever is put here reaches the user verbatim,
        # never passing the "never show SQL, table or column names" rule. This
        # shipped one asking the user to confirm
        # "items.name (likely with ILIKE '%hardner%') ... join
        # v_item_consumption_monthly.item_code". The notes still travel in
        # `knowledge_notes` for the SQL agent and for persistence.
        term = (entities.get("item") or entities.get("metric") or "").strip()

        # NEVER ASK THE USER TO DEFINE A MATERIAL WE STOCK. The model's
        # confidence is about the SCHEMA MAPPING, not about whether the thing
        # exists - and it cannot see the item master from here. Asking "what
        # does lime stone refer to?" for an item with 16,340 kg on hand and an
        # open requisition makes the assistant look like it does not know its
        # own inventory. It happened on 1 run in 3 for the same question, which
        # is worse than always: the user cannot predict it.
        # One cheap lookup settles it, and the answer is the same every run.
        if term:
            try:
                matches = (find_items_by_name(term, limit=5) or {}).get("rows") or []
            except Exception:
                matches = []
            if matches:
                codes = [m.get("item_code") for m in matches if m.get("item_code")]
                return {
                    "context": [
                        f"'{term}' IS a real material in the item master "
                        f"({len(codes)} matching item code(s): "
                        f"{', '.join(str(c) for c in codes[:5])}). Do not ask "
                        f"the user what it means. Answer it as an item "
                        f"question: v_item_demand_picture carries its stock, "
                        f"3-month issuance, days of cover, open demand and "
                        f"their statuses, inbound ETA and the shortfall. "
                        f"Match with item_name ~* '[[:<:]]<word>s?[[:>:]]'.",
                        *(result.mapping_notes or []),
                    ],
                    "knowledge_notes": result.mapping_notes,
                    "knowledge_inferred": True,
                    "knowledge_confident": True,
                }

        subject = f'"{term}"' if term else "one of the terms in your question"
        return {
            "route": "clarify",
            "clarification_question": (
                f"I don't have a documented definition for {subject} in our data, "
                "so I'd be guessing at where to look. Could you tell me what it "
                "refers to - for example which records it lives in, or which "
                "figure you'd expect the answer to come from?"
            ),
            "clarification_options": [],
            "context": [],
            "knowledge_inferred": True,
            "knowledge_confident": False,
            "knowledge_notes": notes,
        }

    # Label the block so the SQL agent knows this was derived, not documented.
    header = (
        "The following mappings were inferred from the database schema because no "
        "documented company terminology matched this question. Treat them as "
        "working assumptions:"
    )

    return {
        "context": [header, *notes],
        "knowledge_inferred": True,
        "knowledge_confident": True,
        # Raw notes (no header) so the API can persist them if the query works.
        "knowledge_notes": notes,
    }
