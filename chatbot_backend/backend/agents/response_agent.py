"""
Response agent - the last node, and the only one the user hears from.

Every path in the graph ends here: data answers, document answers, small talk,
clarification requests and failures. It turns whatever the state holds into one
business-readable reply and appends it to the conversation.
"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.config import get_llm
from backend.prompts.response_prompt import (
    RESPONSE_SYSTEM_PROMPT,
    build_response_prompt,
)

FALLBACK_REPLY = (
    "Sorry, I could not put together an answer for that just now. "
    "Please try rephrasing the question."
)


def _extract_text(message) -> str:
    """
    Pull the plain answer out of the reply.

    The Responses API returns a list of content blocks - reasoning, text,
    annotations - so `.content` is not a string. We want the text blocks only;
    reasoning must never reach the user.
    """
    text = getattr(message, "text", None)
    if isinstance(text, str):
        if text.strip():
            return text.strip()
    elif callable(text):  # older langchain-core exposed text() as a method
        value = text()
        if isinstance(value, str) and value.strip():
            return value.strip()

    content = message.content
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(part for part in parts if part).strip()

    return ""


def response_agent(state: dict) -> dict:
    route = state.get("route")

    # A clarification is already written and specific - sending it through the
    # LLM only risks it being softened into something vaguer. Options ride
    # through in state for the UI; the message text is the question itself.
    if route == "clarify" and state.get("clarification_question"):
        reply = state["clarification_question"]
        return {"final_response": reply, "messages": [AIMessage(content=reply)]}

    # Teaching produced a ready confirmation - return it as-is.
    if route == "teach" and state.get("taught_confirmation"):
        reply = state["taught_confirmation"]
        return {"final_response": reply, "messages": [AIMessage(content=reply)]}

    try:
        response = get_llm().invoke(
            [
                SystemMessage(content=RESPONSE_SYSTEM_PROMPT),
                HumanMessage(content=build_response_prompt(state)),
            ]
        )
        reply = _extract_text(response) or FALLBACK_REPLY
    except Exception as exc:
        reply = FALLBACK_REPLY
        return {
            "final_response": reply,
            "error": f"Response generation failed: {exc}",
            "messages": [AIMessage(content=reply)],
        }

    return {"final_response": reply, "messages": [AIMessage(content=reply)]}
