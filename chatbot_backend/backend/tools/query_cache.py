"""
Remember the SQL that answered a question, and reuse it verbatim next time.

Why this exists
---------------
The SQL agent writes a NEW query from scratch on every turn. Measured over five
runs of the same question it produced up to five different queries - they
happened to agree, but only because the business terms were pinned tightly
enough to force convergence. Where a term is loose, the same question gets
different SQL and therefore different answers.

Caching the SQL turns that from "hope the model agrees with itself" into
"identical by construction": the second time a question is asked, the stored
query runs and the answer cannot drift. It also removes the slowest LLM call in
the turn, which is the SQL one.

What is cached
--------------
Only a turn that clearly worked: SQL ran, no error, and it returned rows. A
query that returned nothing is exactly the kind we do NOT want to make
permanent - see the zero-row guard in sql_agent.

Matching
--------
Two stages, tightest first:

  1. EXACT on a normalised fingerprint (lowercased, punctuation stripped,
     filler words removed, plus the resolved entities). Deterministic.
  2. NEAREST-NEIGHBOUR on the question embedding, but only inside a much
     tighter distance than ordinary retrieval uses. "How much stock of X" and
     "how much stock of Y" are close in embedding space and must never share a
     query, which is why the entities are part of the fingerprint and why this
     threshold is deliberately strict.

Invalidation
------------
Every entry stores a hash of the schema text it was written against. Change the
database shape and every entry stops matching, because a cached query naming a
dropped column is worse than no cache at all.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.config import (
    ENABLE_QUERY_CACHE,
    QUERY_CACHE_MAX_DISTANCE,
    QUERY_CACHE_PATH,
)

# Words that change how a question reads but not what it asks for. Removing
# them means "how many items are out of stock" and "how many items are out of
# stock?" and "tell me how many items are out of stock" share one entry.
_FILLER = {
    "a", "an", "the", "me", "us", "please", "can", "you", "tell", "show",
    "give", "what", "whats", "is", "are", "do", "does", "did", "we", "our",
    "have", "has", "of", "in", "on", "for", "to", "and", "there", "any",
    "get", "list", "want", "would", "like", "could", "i",
}


def _normalise(text: str) -> str:
    """Lowercase, drop punctuation and filler, collapse whitespace."""
    words = re.split(r"[^0-9a-z]+", (text or "").lower())
    kept = [w for w in words if w and w not in _FILLER]
    return " ".join(kept)


def _entity_key(entities: Optional[Dict[str, Any]]) -> str:
    """
    The parts of the extracted entities that change WHICH rows come back.

    item_code is the important one: two questions identical in wording but
    pinned to different items must never share a cached query.
    """
    if not entities:
        return ""
    keep = ("item_code", "item", "branch", "supplier", "status", "department")
    parts = [
        f"{k}={str(entities[k]).strip().lower()}"
        for k in keep
        if entities.get(k)
    ]
    return "|".join(sorted(parts))


def _schema_hash() -> str:
    """
    Hash of everything a cached query was written against.

    THREE inputs, because a cached query is only as good as everything that
    shaped it:

      * the SCHEMA - obviously.
      * the BUSINESS TERMS - a term change silently rewrites what a query SHOULD
        say. Tightening "shaft" from 'any item named bar or shaft' (1,687 codes)
        to 'forged shaft material' (90 codes) leaves the schema untouched.
      * the SQL PROMPT - this one was MISSING and it mattered most, because the
        correctness rules live there. Adding the rule that forbids
        SELECT DISTINCT when listing records did not change the schema or any
        term, so every question already in the cache kept replaying its old,
        pre-rule SQL - through a restart, forever. It was caught when
        `shaft-item-codes` answered 31 twice from cache while a cache-cleared run
        of the identical question answered the correct 29.

    The whole point of this hash is that a fix cannot be made permanent by the
    cache. Leaving the prompt out defeated that for exactly the file where fixes
    are written.
    """
    parts = []
    try:
        from backend.metadata.schema import get_schema_text

        parts.append(get_schema_text())
    except Exception:
        parts.append("schema-unavailable")

    try:
        from backend.metadata import business_terms

        parts.append("\n".join(business_terms.as_documents()))
    except Exception:
        parts.append("terms-unavailable")

    try:
        from backend.prompts.sql_prompt import SQL_SYSTEM_PROMPT

        parts.append(SQL_SYSTEM_PROMPT)
    except Exception:
        parts.append("sql-prompt-unavailable")

    # The GUARDS, for the same reason as the prompt. Correctness rules are
    # written in two places, and a rule added here is invisible to the schema,
    # the terms and the prompt alike. Adding the guard that forbids computing
    # out-of-stock by hand did not change any of those, so three cached
    # branch queries kept replaying the very SQL it now rejects - and a cache
    # hit never reaches the guard to be caught. Hashing the source ties every
    # cached query to the rules it was checked against.
    try:
        from pathlib import Path

        import backend.tools.sql_guards as _guards

        parts.append(Path(_guards.__file__).read_text(encoding="utf-8"))
    except Exception:
        parts.append("guards-unavailable")

    # The DATA fingerprint, so loading a workbook retires queries written
    # against the old contents - a filter on a status that no longer exists
    # would otherwise replay forever and quietly return nothing.
    try:
        from backend.metadata.data_profile import get_profile

        parts.append(get_profile().get("fingerprint", ""))
    except Exception:
        parts.append("profile-unavailable")

    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def fingerprint(question: str, entities: Optional[Dict[str, Any]] = None) -> str:
    raw = f"{_normalise(question)}||{_entity_key(entities)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


# How much of what the USER typed must survive into the rewrite for the turn to
# stand on its own.
#
# Measured this way round on purpose. The obvious direction - how much of the
# rewrite the user supplied - punishes the rewrite for adding adjectives:
# "how many shafts types are in data" became "How many DISTINCT types of shafts
# are PRESENT in the AVAILABLE INVENTORY data", scoring 0.56 and disabling the
# cache on a perfectly self-contained question. Whether the rewrite is verbose
# says nothing about whether the user's words needed context.
_SELF_CONTAINED_OVERLAP = 0.6

# Openers that continue a previous turn rather than starting a new question.
# "what about last month" keeps most of its own words in the rewrite, so the
# ratio alone lets it through - but as a cache key it is meaningless, because
# the month means nothing without the question before it.
_CONTINUATION_OPENERS = (
    "what about", "how about", "and what", "and how", "what if", "same for",
    "same but", "now what", "then what", "also", "instead", "but for",
)

# Words that point at something in the previous turn. A question containing one
# cannot be understood on its own, so it must never become a cache key.
_ANAPHORS = {
    "it", "its", "they", "them", "their", "thier", "those", "these", "that",
    "this", "same", "above", "previous", "former", "latter", "one",
}


def is_self_contained(user_query: str, rewritten_query: str) -> bool:
    """
    True when the user's own words carry the whole question.

    The cache is keyed on what the USER typed, not on the rewritten question,
    because the rewrite is LLM-generated and unstable: three runs of one
    question produced "How many distinct types of shafts are in the
    organization's data?", "How many types of shafts are in the available
    data?" and "How many types of shafts are present in the available inventory
    data?" - three different keys for one question, so the exact-match stage
    almost never hit.

    The user's text is stable, but it is only a valid key when it means the same
    thing on its own. A follow-up like "write their names" depends entirely on
    the previous turn; caching it would let one conversation's answer leak into
    another's identical-looking question. So those turns are neither looked up
    nor stored - measured by how much of the rewrite the user actually supplied.
    """
    plain = " ".join((user_query or "").lower().split())
    if not plain:
        return False

    # "what about last month" - the words are its own, but the question is not.
    if plain.startswith(_CONTINUATION_OPENERS):
        return False

    # "write their names", "how much of that" - points at the previous turn.
    if _ANAPHORS & set(re.split(r"[^a-z]+", plain)):
        return False

    typed = set(_normalise(user_query).split())
    full = set(_normalise(rewritten_query or user_query).split())

    if not typed:
        return False
    if not full:
        return True

    # How much of what the USER said the rewrite kept - not the reverse.
    return len(typed & full) / len(typed) >= _SELF_CONTAINED_OVERLAP


# --------------------------------------------------------------------------
#  disk
# --------------------------------------------------------------------------
def _path() -> Path:
    return Path(QUERY_CACHE_PATH)


def load_cache() -> List[Dict[str, Any]]:
    # Reads take the lock too, cheap as they are. On Windows os.replace() fails
    # outright if any other handle has the destination open, so a read that
    # overlapped a write would make that WRITE fail - measured as 3 silently
    # dropped entries out of 96 under 8 concurrent writers before this.
    with _LOCK:
        path = _path()
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8")) or []
        except (json.JSONDecodeError, OSError):
            return []


# Serialises the read-modify-write cycles below. FastAPI runs the sync chat
# endpoint in a threadpool and the streaming one on the event loop, so two turns
# really can reach `remember()` at the same moment in one process; without this
# the later write is built from a stale read and silently drops the earlier
# entry. Re-entrant because the write helper is called from inside these
# sections.
_LOCK = threading.RLock()


def _write(entries: List[Dict[str, Any]]) -> None:
    """
    Replace the cache file atomically.

    `lookup()` rewrites this file on every cache HIT (to bump the counter), so a
    torn write is not a rare event - and `load_cache()` swallows JSONDecodeError
    and returns [], which would silently discard EVERY remembered query. Writing
    to a temp file in the same directory and os.replace()-ing it in means a
    reader sees either the whole old file or the whole new one, never a
    half-written one. os.replace is atomic on POSIX and on Windows, but only
    within one filesystem - hence the temp file next to the target, not in /tmp.
    """
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_name = None
    try:
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
        )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(entries, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())  # survive a power loss, not just a crash
        os.replace(tmp_name, path)
        tmp_name = None  # ownership transferred; nothing to clean up
    finally:
        if tmp_name:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


# --------------------------------------------------------------------------
#  vector index, for the near-match stage
# --------------------------------------------------------------------------
def _index(entry: Dict[str, Any]) -> None:
    """Embed the question so a rewording can find this entry."""
    try:
        from backend.tools.vector_tools import add_documents

        add_documents(
            [entry["question"]],
            kind="query",
            metadatas=[{"kind": "query", "fingerprint": entry["fingerprint"]}],
            ids=[f"query-{entry['fingerprint']}"],
        )
    except Exception:
        pass  # the cache still works on exact matches without this


def _nearest(question: str) -> Optional[str]:
    """Fingerprint of the closest remembered question, if it is close ENOUGH."""
    try:
        from backend.tools.vector_tools import _embeddings, get_collection

        collection = get_collection()
        if collection is None:
            return None

        found = collection.query(
            query_embeddings=[_embeddings().embed_query(question)],
            n_results=1,
            where={"kind": "query"},
        )
        distances = (found.get("distances") or [[]])[0]
        metadatas = (found.get("metadatas") or [[]])[0]
        if not distances or distances[0] > QUERY_CACHE_MAX_DISTANCE:
            return None
        return (metadatas[0] or {}).get("fingerprint")
    except Exception:
        return None


# --------------------------------------------------------------------------
#  the api
# --------------------------------------------------------------------------
def lookup(question: str, entities: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """The remembered query for this question, or None."""
    if not ENABLE_QUERY_CACHE or not question:
        return None

    entries = load_cache()
    if not entries:
        return None

    schema = _schema_hash()
    by_fp = {
        e["fingerprint"]: e
        for e in entries
        if e.get("schema_hash") == schema  # a stale entry never matches
    }
    if not by_fp:
        return None

    hit = by_fp.get(fingerprint(question, entities))

    if hit is None:
        near_fp = _nearest(question)
        candidate = by_fp.get(near_fp) if near_fp else None
        # A near match is only safe when it was resolved against the same
        # entities - otherwise "stock of resin" would answer "stock of steel".
        if candidate and candidate.get("entity_key") == _entity_key(entities):
            hit = candidate

    if hit is None:
        return None

    # Bump the counter under the lock, re-reading from disk rather than writing
    # back `entries` - which was read before the (slow, networked) embedding
    # call in _nearest() and may be stale by now. Deliberately NOT holding the
    # lock across that call: it would serialise every cache lookup behind an
    # embedding round-trip.
    hit["hits"] = hit.get("hits", 0) + 1
    hit["last_used"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _bump(hit["fingerprint"], hit["last_used"])

    return hit


def _bump(fp: str, when: str) -> None:
    """Record one use of a cached entry. Best-effort; never fails a lookup."""
    try:
        with _LOCK:
            entries = load_cache()
            for entry in entries:
                if entry.get("fingerprint") == fp:
                    entry["hits"] = entry.get("hits", 0) + 1
                    entry["last_used"] = when
                    _write(entries)
                    return
    except Exception:
        pass


def remember(
    question: str,
    entities: Optional[Dict[str, Any]],
    sql: str,
    tables_used: Optional[List[str]] = None,
    limit_is_user_requested: bool = False,
) -> bool:
    """Store the query that answered this question. Overwrites its own entry."""
    if not ENABLE_QUERY_CACHE or not question or not sql.strip():
        return False

    fp = fingerprint(question, entities)
    entry = {
        "fingerprint": fp,
        "question": question,
        "normalised": _normalise(question),
        "entity_key": _entity_key(entities),
        "sql": sql,
        "tables_used": tables_used or [],
        "limit_is_user_requested": limit_is_user_requested,
        "schema_hash": _schema_hash(),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "last_used": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "hits": 0,
    }

    try:
        with _LOCK:
            entries = [e for e in load_cache() if e.get("fingerprint") != fp]
            entries.append(entry)
            _write(entries)
    except Exception:
        return False

    _index(entry)
    return True


def forget(fingerprint_or_question: str) -> int:
    """Drop one entry, by fingerprint or by the question text. Returns count."""
    with _LOCK:
        entries = load_cache()
        fp = fingerprint_or_question
        remaining = [
            e for e in entries
            if e.get("fingerprint") != fp
            and _normalise(e.get("question", "")) != _normalise(fingerprint_or_question)
        ]
        removed = len(entries) - len(remaining)
        if removed:
            _write(remaining)
        try:
            from backend.tools.vector_tools import get_collection

            collection = get_collection()
            if collection is not None:
                gone = {e["fingerprint"] for e in entries} - {
                    e["fingerprint"] for e in remaining
                }
                collection.delete(ids=[f"query-{f}" for f in gone])
        except Exception:
            pass
    return removed


def clear_cache() -> int:
    """Drop every entry, from disk and from the vector index."""
    with _LOCK:
        return _clear_cache_locked()


def _clear_cache_locked() -> int:
    entries = load_cache()
    try:
        from backend.tools.vector_tools import get_collection

        collection = get_collection()
        if collection is not None:
            existing = collection.get(where={"kind": "query"}, include=[])
            ids = existing.get("ids") or []
            if ids:
                collection.delete(ids=ids)
    except Exception:
        pass
    _write([])
    return len(entries)


def stats() -> Dict[str, Any]:
    entries = load_cache()
    schema = _schema_hash()
    fresh = [e for e in entries if e.get("schema_hash") == schema]
    return {
        "entries": len(entries),
        "usable": len(fresh),
        "stale_after_schema_change": len(entries) - len(fresh),
        "total_hits": sum(e.get("hits", 0) for e in entries),
    }


if __name__ == "__main__":  # pragma: no cover
    import sys

    if "--clear" in sys.argv:
        print(f"cleared {clear_cache()} cached queries")
    elif "--list" in sys.argv:
        for e in load_cache():
            print(f"[{e.get('hits', 0):>3} hits] {e['question']}")
            print(f"          {' '.join(e['sql'].split())[:150]}")
    else:
        print(stats())
