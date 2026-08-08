"""Prompts for the Item Resolution agent (same-name / different-item_code check)."""

ITEM_RESOLUTION_SYSTEM_PROMPT = """You are the Item Resolution Agent for a supply chain assistant.

Several items in the item master share the same name but have different item_code
and specs. You are called only when that is true for the item the user asked about.
Your only job is to decide whether the user's latest message already tells us which
of the candidate items they want.

The user may point at one item by its item_code, by a distinguishing spec/material
word, by naming a few of them, or by saying "all"/"any"/"every one"/"both" for all
of them. If nothing in the message narrows it down, they have not answered yet.

RULES
1. Only return item_code values that appear in the candidate list below - never
   invent one.
2. If the user asked for "all" (or equivalent - every one, both, the whole
   family), set resolved=true and all_of_them=true, and leave item_codes empty.
3. If the message does not point to a specific item_code or subset, set
   resolved=false and return an empty list - do not guess."""


def build_item_resolution_prompt(
    item_name: str,
    candidates: list[dict],
    user_query: str,
    rewritten_query: str,
    truncated: bool = False,
) -> str:
    listing = "\n".join(
        f"- item_code {c['item_code']}: "
        f"{c.get('specs') or '(no specs)'}"
        + (f" | category: {c['item_category']}" if c.get("item_category") else "")
        + (f" | uom: {c['uom']}" if c.get("uom") else "")
        for c in candidates
    )
    more_note = (
        f"\n(only the first {len(candidates)} are listed here; more exist - if the "
        "user's answer does not match any of these, treat it as unresolved rather "
        "than guessing)"
        if truncated
        else ""
    )
    return f"""The user asked about an item called "{item_name}", but multiple \
different items share that name:

{listing}{more_note}

Latest user message: {user_query}
Question so far: {rewritten_query}

Does the latest message already tell us which of these the user wants?"""
