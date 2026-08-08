"""
Learn agent - captures a term the user teaches.

When the user states a definition rather than asking a question ("round bar and
steel bar items are called shafts"), the understanding agent routes here. This
agent turns the statement into a structured term + its schema mapping and
persists it to the learned store, so every later question can use it. It then
hands a confirmation to the response agent.

User-taught terms are higher-trust than machine-inferred ones (a person stated
them), so they are saved immediately - no query-succeeded gate.
"""

from typing import List

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from backend.config import EFFORT_ACCURATE, structured_llm
from backend.metadata.schema import get_schema_text
from backend.prompts.learn_prompt import LEARN_SYSTEM_PROMPT, build_learn_prompt
from backend.tools import vector_tools


class TaughtTerm(BaseModel):
    is_definition: bool = Field(
        description="False if the message is not actually teaching a term."
    )
    term: str = Field(description="The word/phrase being defined.")
    meaning: str = Field(description="What it means, in plain language.")
    maps_to: str = Field(
        default="", description="Database columns/expression it maps to, from the schema."
    )
    aliases: List[str] = Field(
        default_factory=list, description="Other words for the same thing."
    )


def learn_agent(state: dict) -> dict:
    statement = state.get("rewritten_query") or state.get("user_query", "")

    try:
        llm = structured_llm(TaughtTerm, effort=EFFORT_ACCURATE)
        result = llm.invoke(
            [
                SystemMessage(content=LEARN_SYSTEM_PROMPT.format(schema=get_schema_text())),
                HumanMessage(content=build_learn_prompt(statement)),
            ]
        )
    except Exception as exc:
        return {
            "taught_ok": False,
            "taught_confirmation": (
                "Sorry, I couldn't save that term just now. Please try again."
            ),
            "error": f"Learn agent failed: {exc}",
        }

    if not result.is_definition or not result.term.strip() or not result.meaning.strip():
        return {
            "taught_ok": False,
            "taught_confirmation": (
                "I didn't catch a clear term to remember. Try phrasing it as "
                "\"X means Y\" or \"we call A as B\"."
            ),
        }

    # Fold any aliases into the meaning so retrieval and SQL both see them.
    meaning = result.meaning.strip()
    if result.aliases:
        meaning += f" (also: {', '.join(result.aliases)})"

    saved = vector_tools.persist_taught_term(
        term=result.term.strip(),
        meaning=meaning,
        maps_to=result.maps_to.strip(),
        notes="Defined by the user.",
    )

    if not saved:
        return {
            "taught_ok": False,
            "taught_confirmation": "I understood the term but couldn't save it. Please try again.",
        }

    confirmation = f"Got it — I'll remember that **{result.term.strip()}** means {meaning}."
    if result.maps_to.strip():
        confirmation += " I'll use it when answering related questions."

    return {
        "taught_ok": True,
        "taught_term": {
            "term": result.term.strip(),
            "meaning": meaning,
            "maps_to": result.maps_to.strip(),
        },
        "taught_confirmation": confirmation,
    }
