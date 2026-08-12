"""
Item Resolution agent - catches same-name, different-item_code items before SQL
is written.

The item master allows many item_codes to share the same `item` name with
different specs - this is not a rare edge case, common names like "Round Bar" or
"Hex Bolt" span hundreds of item_codes. Left alone, the SQL agent would match by
name and lump them all together, or guess one. This agent checks the real data
first:

    0-1 matching item_code : nothing ambiguous, proceed (pinning the single
                              item_code when there is exactly one, so SQL filters
                              exactly rather than by fuzzy name).
    2+ matching item_code  : ask which one(s) are wanted, via the same clarify
                              route as any other confirmation, with the matching
                              rows attached so the UI's normal table rendering
                              shows them immediately.

Runs stateless per turn like the rest of the graph: a follow-up reply ("ITEM003",
"the EN8 one", "all of them") is resolved fresh each time by checking whether the
latest message already narrows the candidate list down, rather than remembering
anything from the previous turn. That check only runs when the immediately
preceding assistant message was actually THIS item's disambiguation question -
otherwise a coincidental "all"/"any"/an item_code-looking token in a reply to some
OTHER clarify question (e.g. "All available dates" answering the date-scope gate)
would be misread as answering a question that was never asked.

Resolving the reply is two-tier: an exact item_code mention or an "all/any/every"
word is caught deterministically (cheap, no ambiguity in what it means); anything
more descriptive ("the 20mm one", "the EN8 grade") falls back to a small LLM call
against the candidate list.
"""

import re
from typing import List, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from backend.config import EFFORT_FAST, structured_llm
from backend.prompts.item_resolution_prompt import (
    ITEM_RESOLUTION_SYSTEM_PROMPT,
    build_item_resolution_prompt,
)
from backend.tools.postgres_tools import find_items_by_name

CHIP_LIMIT = 8  # above this, list codes only in the table, not as tap-chips
LLM_CANDIDATE_LIMIT = 50  # cap on how many candidates go into the resolution prompt

_ALL_WORDS_RE = re.compile(r"\b(all|any|every|everything|both|entire)\b", re.IGNORECASE)


class ItemSelection(BaseModel):
    resolved: bool = Field(
        description="True if the latest message already specifies which candidate item(s) are wanted."
    )
    all_of_them: bool = Field(
        default=False,
        description="True if the user wants every item with this name, not just a subset.",
    )
    item_codes: List[str] = Field(
        default_factory=list,
        description="The selected item_code(s), copied exactly from the candidate list. Empty unless resolved and not all_of_them.",
    )


def _we_asked_this(state: dict, item_name: str) -> bool:
    """
    True only if the immediately preceding assistant message was OUR
    disambiguation question for this exact item name.

    Without this check, a coincidental "all"/"any" (or a mentioned item_code)
    in a reply to some OTHER clarify question - e.g. "All available dates"
    answering the unrelated date-scope gate - would be misread as an answer
    to an item-disambiguation question that was never actually asked.
    """
    messages = state.get("messages") or []
    if len(messages) < 2:
        return False
    prev = messages[-2]
    if getattr(prev, "type", "") != "ai":
        return False
    content = prev.content if isinstance(prev.content, str) else ""
    return f'named "{item_name}"'.lower() in content.lower()


def _deterministic_selection(
    user_query: str, candidates: List[dict]
) -> Optional[Tuple[bool, List[str]]]:
    """Cheap, unambiguous replies, resolved without an LLM call."""
    text_lower = (user_query or "").lower()
    if not text_lower:
        return None
    if _ALL_WORDS_RE.search(text_lower):
        return True, []
    hits = [
        c["item_code"]
        for c in candidates
        if c.get("item_code") and c["item_code"].lower() in text_lower
    ]
    if hits:
        return False, hits
    return None


_DEAD_ITEM_RE = re.compile(r"\((?:deleted|old|obsolete)\)|\bdeleted\b", re.IGNORECASE)


def _tight(text: str) -> str:
    """Lowercase, strip all punctuation/space: 'A-85' and 'a 85' -> 'a85'."""
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _haystack(candidate: dict) -> str:
    # find_items_by_name aliases the master's columns back to these names.
    # material_standard no longer exists; category carries the grade instead.
    return f"{candidate.get('item') or ''} {candidate.get('specs') or ''} {candidate.get('item_category') or ''}"


def _prefer_live(candidates: List[dict]) -> List[dict]:
    """
    Drop retired items when live ones remain.

    834 rows in the master are tagged '(Deleted)' / '(old)' / '(obsolete)'.
    Offering a retired item beside its live replacement forces the user to
    choose between things that are not real alternatives.
    """
    live = [c for c in candidates if not _DEAD_ITEM_RE.search(c.get("item") or "")]
    return live if live else candidates


def _best_matches(query: str, candidates: List[dict]) -> List[dict]:
    """
    The candidates that match what the user typed MOST completely.

    Three tiers, best first:
      3  the whole phrase IS the item - normalised name+spec equals the query
         ("resin a85" == Resin + spec "A-85"), so the user already named it
      2  every token appears as a whole word in name/spec/material
      1  every token appears somewhere (substring)

    Only the top non-empty tier is returned. When that tier holds exactly one
    candidate the user has already answered the disambiguation question, and
    asking again is pure friction - which is the whole point of this function.
    """
    wanted = _tight(query)
    tokens = [t.lower() for t in re.split(r"[^0-9a-zA-Z]+", query or "") if t]

    exact, worded, loose = [], [], []
    for c in candidates:
        hay = _haystack(c)
        if wanted and _tight(hay) == wanted:
            exact.append(c)
            continue
        words = set(re.split(r"[^0-9a-z]+", hay.lower()))
        if tokens and all(t in words for t in tokens):
            worded.append(c)
        else:
            loose.append(c)

    return exact or worded or loose


def _matched_on_words(query: str, candidate: dict) -> bool:
    """True only when every token of the query is a WHOLE WORD in the candidate.

    The guard against auto-pinning a coincidence: "rank" is a substring of
    "Crank", "bar" of "Barrel", "oil" of "Boiler". A substring hit tells you
    nothing about whether the user meant that item.
    """
    tokens = [t.lower() for t in re.split(r"[^0-9a-zA-Z]+", query or "") if t]
    if not tokens:
        return False

    hay = _haystack(candidate)
    # The EXACT tier is safe too: "resin a85" normalises to the same string as
    # Resin + spec "A-85", so the user has already named the item precisely -
    # even though "a85" is not a whole word once punctuation is stripped.
    if _tight(query) and _tight(hay) == _tight(query):
        return True

    words = set(re.split(r"[^0-9a-z]+", hay.lower()))
    return all(t in words for t in tokens)


def _pin_note(item_name: str, codes: List[str]) -> str:
    """The user really did choose these - state it as settled."""
    codes_list = ", ".join(f"'{c}'" for c in codes)
    return (
        f"The user selected these item_code value(s) for '{item_name}': {codes_list}. "
        f"Filter items.item_code IN ({codes_list}) using exactly this list - do not "
        "match by item name."
    )


def _auto_note(item_name: str, codes: List[str]) -> str:
    """
    We picked this ourselves - say so.

    This used to reuse _pin_note, which told the SQL agent "the user selected"
    a code the user had never seen. The SQL agent treats a user selection as
    settled fact and ANDs it with everything else, so one wrong auto-pick
    silently narrowed the whole query to a single row. Wording it as an
    inference lets the SQL agent weigh it instead of obeying it.
    """
    codes_list = ", ".join(f"'{c}'" for c in codes)
    return (
        f"'{item_name}' most closely matches item_code {codes_list} in the item "
        f"master, so treat that as the intended item. This was inferred from the "
        f"wording, NOT chosen by the user - if the question is about a category "
        f"or asks for a count across many items, ignore this and match by name "
        f"instead."
    )


# A phrase is treated as a CATEGORY rather than one item when the candidates it
# matches carry this many different names or more. "kerosene oil" returns two
# rows both named "kerosene Oil" - one item, two codes, a real disambiguation.
# "shafts" returns Shaft, Cast Iron Scrap, SPCE Shaft Seal Kit and a
# maintenance line - four unrelated things that merely mention the word, which
# is a keyword search, not a choice between duplicates.
_CATEGORY_DISTINCT_NAMES = 3

# Questions about how many KINDS of something exist, rather than about one
# thing. Pinning a single item_code here is a category error: the answer is a
# count across items, so narrowing to one guarantees a wrong number.
_AGGREGATE_RE = re.compile(
    r"\b(how many|number of|count of|list|which|what)\b[^?]*\b"
    r"(type|types|kind|kinds|variet\w+|categor\w+|different|distinct)\b"
    r"|\b(type|types|kind|kinds|variet\w+)\s+of\b",
    re.IGNORECASE,
)


def _is_aggregate_question(*texts: str) -> bool:
    return any(_AGGREGATE_RE.search(t or "") for t in texts)


# A question about where an item STANDS - what we hold, how long it lasts, who
# wants it, whether to buy. These are answered per item_code by
# v_item_demand_picture, so several matching codes are extra ROWS, not a choice
# the user has to make first.
_POSITION_RE = re.compile(
    r"\b(?:"
    r"stock|on hand|available|availability|inventory|balance"
    r"|cover|how long|runs? out|left"
    r"|consum\w+|issued?|issuance|usage|used|burn"
    r"|demand|requisition|pending|short|shortage|shortfall"
    r"|buy|purchase|order|reorder|procure|replenish"
    r"|status|position|situation|doing"
    r"|how much|how many"
    r")\b",
    re.IGNORECASE,
)


def _is_position_question(*texts: str) -> bool:
    return any(_POSITION_RE.search(t or "") for t in texts)


def _looks_like_category(query: str, candidates: List[dict]) -> bool:
    """True when the phrase names a KIND of thing, not a specific item."""
    if len(candidates) < 2:
        return False

    wanted = _tight(query)
    names = {_tight(c.get("item") or "") for c in candidates}

    # EVERY candidate carries the exact name typed - so the phrase really is one
    # item and the candidates differ only by spec. That is a genuine
    # disambiguation ("kerosene oil" -> two codes, both named kerosene Oil).
    #
    # It is not enough for SOME candidate to match exactly, which is what this
    # used to test: "scrap" matches an item literally named Scrap, but also Cast
    # Iron Scrap, SS Scrap, Bronze Scrap and 22 other names across 94 codes.
    # Treating that as one item asked the user to pick from a 94-row list
    # instead of answering a plainly categorical question.
    if wanted and names == {wanted}:
        return False

    return len(names) >= _CATEGORY_DISTINCT_NAMES


def _category_note(item_name: str) -> str:
    return (
        f"'{item_name}' is being used as a CATEGORY here, not as one specific "
        f"item - the phrase matches several unrelated item names. Do NOT filter "
        f"on a single item_code. Match by name across the columns named in the "
        f"business context (item master, and the free-text item columns on the "
        f"imports/exports/trucking tables), and remember the item master stores "
        f"the singular form, so search the singular stem as well as what the "
        f"user typed."
    )


# Above this many candidates, an IN list stops being reasonable to embed in the
# prompt and we fall back to a token filter.
_PIN_ALL_LIMIT = 300


def _all_note(item_name: str, codes: List[str]) -> str:
    """
    "All of them" - pin the resolved codes rather than re-matching by name.

    Telling the SQL agent to match `items.name ILIKE '%<phrase>%'` is exactly
    the bug this agent exists to prevent: the user's phrase mixes the NAME with
    the SPEC ("resin a 85"), which lives in a different column, so the name
    match finds nothing. We already resolved the real candidates - hand those
    over. Only for an unusually large set do we fall back to a filter, and even
    then it is spelled out across item AND specs so it cannot silently miss.
    """
    if codes and len(codes) <= _PIN_ALL_LIMIT:
        codes_list = ", ".join(f"'{c}'" for c in codes)
        return (
            f"The user wants ALL {len(codes)} items matching '{item_name}'. Filter "
            f"items.item_code IN ({codes_list}) using exactly this list - do NOT "
            "match by item name, because the user's phrase may combine the item "
            "name with its spec, which are separate columns."
        )
    tokens = [t for t in re.split(r"[^0-9a-zA-Z]+", item_name or "") if t]
    predicate = " AND ".join(
        "(i.name ILIKE '%%%s%%' OR i.default_specification ILIKE '%%%s%%')" % (t, t)
        for t in tokens
    )
    return (
        f"The user wants every item matching '{item_name}' ({len(codes)} of them). "
        f"The phrase mixes the item NAME with its SPEC, which are separate columns, "
        f"so match each word against BOTH: {predicate}. Do not match the whole "
        "phrase against items.name alone - it will return nothing."
    )


def _position_note(item_name: str, codes=None) -> str:
    """The item's standing position, formatted for the answer.

    Read straight from v_item_demand_picture, which is one row per item_code.
    Returns "" on any problem - a missing position note must never cost the user
    their actual answer.
    """
    try:
        from sqlalchemy import text

        from backend.config import get_engine

        where, params = "", {}
        if codes:
            where = "WHERE item_code = ANY(:codes)"
            params["codes"] = list(codes)
        elif item_name:
            where = "WHERE item_name ~* :pat"
            params["pat"] = r"[[:<:]]" + re.escape(item_name.strip()) + r"s?[[:>:]]"
        else:
            return ""

        with get_engine().connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT item_code, item_name, available_qty, issued_qty_3m,
                           issued_since, data_through, days_of_cover,
                           open_demand_qty, open_requisitions, demand_statuses,
                           demand_overdue, earliest_required_date,
                           incoming_qty, earliest_eta, incoming_statuses,
                           suggested_buy_qty, rank
                    FROM v_item_demand_picture
                    {where}
                    ORDER BY available_qty DESC NULLS LAST
                    LIMIT 6
                    """
                ),
                params,
            ).mappings().all()
    except Exception:
        return ""

    if not rows:
        return ""

    lines = [
        f"STANDING POSITION for '{item_name}' - state these BESIDE the answer to "
        f"the question that was actually asked, in the lens each belongs to. Do "
        f"NOT let them replace that answer, and do not repeat them as a table:",
    ]
    for r in rows:
        bits = [f"  {r['item_name']} ({r['item_code']})"]
        bits.append(f"    stock now: {r['available_qty']}")
        if r["issued_qty_3m"] is not None:
            bits.append(
                f"    issued since {r['issued_since']}: {r['issued_qty_3m']}"
                f" (issuance data runs to {r['data_through']})"
            )
        bits.append(
            f"    days of cover: {r['days_of_cover'] if r['days_of_cover'] is not None else 'not measurable - no issues in 3 months'}"
        )
        if r["open_demand_qty"]:
            over = " OVERDUE" if r["demand_overdue"] else ""
            bits.append(
                f"    open demand: {r['open_demand_qty']} across "
                f"{r['open_requisitions']} requisition(s) [{r['demand_statuses']}]"
                f" required by {r['earliest_required_date']}{over}"
            )
        else:
            bits.append("    open demand: none")
        if r["incoming_qty"]:
            bits.append(
                f"    inbound: {r['incoming_qty']} , earliest ETA "
                f"{r['earliest_eta']} [{r['incoming_statuses']}]"
            )
        else:
            bits.append("    inbound: nothing on the way")
        bits.append(
            f"    shortfall to buy: {r['suggested_buy_qty']}"
            " (committed demand only, no safety stock is set)"
        )
        if r["rank"]:
            bits.append(f"    ABC rank: {r['rank']}")
        lines.append("\n".join(bits))
    return "\n".join(lines)


def _with_position(notes, item_name, codes=None):
    """Append the standing position to whatever notes this path produced.

    Every return path goes through here so none can quietly ship without the
    figures the user expects beside an item answer.
    """
    note = _position_note(item_name, codes)
    return [*notes, note] if note else list(notes)


def item_resolution_agent(state: dict) -> dict:
    if state.get("route") != "data":
        return {}

    entities = state.get("entities") or {}
    if entities.get("item_code"):
        # The user already gave (or picked) an exact code - nothing to resolve.
        return {}

    item_name = entities.get("item")
    if not item_name:
        return {}

    # "How many TYPES of shafts do we have" is a count ACROSS items, so there is
    # no single item to resolve and pinning one guarantees a wrong answer. Leave
    # it to the SQL agent and the business-term mapping.
    if _is_aggregate_question(
        state.get("rewritten_query", ""),
        state.get("user_query", ""),
        str((entities.get("metric") or "")),
        state.get("intent", ""),
    ):
        return {"item_context": _with_position([_category_note(item_name)], item_name)}

    lookup = find_items_by_name(item_name)
    candidates = lookup["rows"]
    truncated = lookup["truncated"]

    # Retired items are not real alternatives - never make the user choose
    # between a live item and its '(Deleted)' twin.
    if not truncated:
        candidates = _prefer_live(candidates)

    if len(candidates) <= 1 and not truncated:
        if candidates:
            code = candidates[0]["item_code"]
            return {
                "item_context": [
                    f"'{item_name}' refers to item_code = '{code}' in the items "
                    "table - filter on this exact item_code, not a name match."
                ],
                # Publish the resolved code as an entity too: downstream steps
                # (reorder / purchase timing) look it up there, and a note meant
                # for the SQL agent is invisible to them.
                "entities": {**entities, "item_code": code},
            }
        return {}

    # A word that matches several unrelated item names is a CATEGORY, not one
    # item. 'shafts' hits Shaft, Cast Iron Scrap (spec "Crank Shafts Scrap"),
    # SPCE Shaft Seal Kit and a maintenance line - only one of which happens to
    # contain the literal plural, so the tie-break below would auto-pin it and
    # filter the whole question down to Cast Iron Scrap.
    if not truncated and _looks_like_category(item_name, candidates):
        return {"item_context": _with_position([_category_note(item_name)], item_name)}

    # The user may have ALREADY identified the item by including its spec
    # ("resin a85"). If one candidate matches what they typed more completely
    # than every other, that IS their answer - asking them to pick it from a
    # list is friction, not diligence. Only a genuine tie gets a question.
    if not truncated:
        best = _best_matches(item_name, candidates)
        # A SUBSTRING-ONLY match must never auto-pin. _best_matches falls back
        # to a loose tier where every token merely appears SOMEWHERE in the
        # text, and that tier matches things nobody meant: asked "which A rank
        # items are out of stock", it resolved 'A rank items' to
        # 'Crank Lath Machine Tol Post' - because "rank" is inside "Crank" -
        # and pinned it as an exact item_code. The query then filtered the whole
        # question down to one irrelevant machine part and answered 0.
        # Pinning is only safe on a whole-word or exact match; a loose hit is a
        # coincidence of spelling, not an identification.
        if len(best) == 1 and _matched_on_words(item_name, best[0]):
            return {
                # _auto_note, not _pin_note: we inferred this, the user never
                # saw it, and the SQL agent must be able to override it.
                "item_context": _with_position([_auto_note(item_name, [best[0]["item_code"]])], item_name, [best[0]["item_code"]]),
                "entities": {**entities, "item_code": best[0]["item_code"]},
            }
        # A clear top tier that is smaller than the full set still narrows the
        # question to the plausible items instead of everything sharing a name.
        if best and len(best) < len(candidates):
            candidates = best

    valid_codes = {c["item_code"] for c in candidates}
    user_query = state.get("user_query", "")

    selection = None
    if _we_asked_this(state, item_name):
        selection = _deterministic_selection(user_query, candidates)
        if selection is None:
            result = None
            try:
                llm = structured_llm(ItemSelection, effort=EFFORT_FAST)
                result = llm.invoke(
                    [
                        SystemMessage(content=ITEM_RESOLUTION_SYSTEM_PROMPT),
                        HumanMessage(
                            content=build_item_resolution_prompt(
                                item_name,
                                candidates[:LLM_CANDIDATE_LIMIT],
                                user_query,
                                state.get("rewritten_query", ""),
                                truncated,
                            )
                        ),
                    ]
                )
            except Exception:
                pass
            if result and result.resolved:
                if result.all_of_them:
                    selection = (True, [])
                elif result.item_codes:
                    selection = (False, [c for c in result.item_codes if c in valid_codes])

    if selection is not None:
        all_of_them, codes = selection
        if all_of_them:
            return {"item_context": _with_position([_all_note(item_name, sorted(valid_codes))], item_name, sorted(valid_codes))}
        if codes:
            resolved = {**entities}
            if len(codes) == 1:
                resolved["item_code"] = codes[0]
            return {"item_context": _with_position([_pin_note(item_name, codes)], item_name, codes), "entities": resolved}

    # POSITION QUESTIONS DO NOT NEED A CHOICE. "how much lime stone do we have",
    # "days of cover for X", "should we buy more X" are answered per item_code
    # anyway - the item picture returns one row per code, so every candidate is
    # simply a row in the answer. Asking which one first spends a turn to return
    # LESS than not asking would have, and the user can still narrow afterwards
    # by reading the rows.
    # A choice is still worth asking for when picking the wrong code changes the
    # answer rather than adding a row - which is what the branches above handle.
    if _is_position_question(
        state.get("rewritten_query", ""), state.get("user_query", "")
    ):
        return {
            "item_context": [
                _all_note(item_name, sorted(valid_codes)),
                (
                    f'"{item_name}" matches {len(candidates)} item codes. This is '
                    f"a stock-position question, so answer for ALL of them - one "
                    f"row each - rather than picking one. Say in the answer that "
                    f"several variants matched, and give the figures per variant "
                    f"so the user can see which one they meant."
                ),
            ]
        }

    # Still ambiguous - ask, with the real candidates attached so the normal
    # table rendering shows them under the question.
    columns = list(candidates[0].keys())
    show_chips = len(candidates) <= CHIP_LIMIT
    options = ([c["item_code"] for c in candidates] if show_chips else []) + ["All of them"]

    count_desc = f"{len(candidates)}{'+' if truncated else ''}"
    ask = (
        "tap the one you want, describe a few, or say \"all of them\""
        if show_chips
        else "reply with the item_code (or a distinguishing spec/material), a few of them, or say \"all of them\""
    )
    question = (
        f'I found {count_desc} different items named "{item_name}"'
        + (f" (showing the first {len(candidates)})" if truncated else "")
        + f" — see the table below for their specs. Which do you want: {ask}?"
    )

    return {
        "route": "clarify",
        "clarification_question": question,
        "clarification_options": options,
        "columns": columns,
        "retrieved_data": candidates,
        "row_count": len(candidates),
        "truncated": truncated,
    }
