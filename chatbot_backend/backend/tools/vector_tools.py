"""
Vector store for business terminology, learned mappings and company documents.

Backed by Chroma persisted on disk (path from VECTOR_DIR in .env), embedded
with OpenAI. Chroma is a lazy import: if it is not installed, or the store has
not been seeded yet, search() falls back to keyword matching over
backend/metadata/business_terms.py so the graph still works end to end.

Three kinds of content live here, separated by the "kind" metadata field:

    kind="term"    : curated business terminology + its database mapping
                     (backend/metadata/business_terms.py). Hand-maintained.
    kind="learned" : mappings the Knowledge Agent inferred from the schema that
                     then produced a working query. Auto-saved for reuse, and
                     mirrored to LEARNED_TERMS_PATH for human review.
    kind="doc"     : policy/process documents, for the RAG agent.

Two lifecycle entry points:

    ensure_seeded()        - called at startup. Re-seeds the curated terms only
                             when business_terms.py actually changed (hash), and
                             syncs learned mappings from disk. No manual re-seed.
    persist_learned_term() - called after a successful knowledge-inferred turn.

Run `python -m backend.tools.vector_tools` to force a seed; add --list-learned
or --clear-learned to inspect or wipe the learned store.
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from backend.config import (
    EMBEDDING_MODEL,
    EMBEDDING_TIMEOUT_S,
    EMBEDDING_MAX_RETRIES,
    LEARNED_TERMS_PATH,
    OPENAI_API_KEY,
    PERSIST_LEARNED,
    RAG_MAX_DISTANCE,
    RAG_TOP_K,
    VECTOR_COLLECTION,
    VECTOR_DIR,
)
from backend.metadata import business_terms


@lru_cache(maxsize=1)
def _embeddings():
    """
    The embedding client, with an EXPLICIT timeout - do not remove it.

    Default is `timeout=None`, which was costing whole minutes per turn. The
    HTTP pool drops an idle connection after ~5s, and every turn leaves a much
    longer gap than that while the chat model thinks. The next embed_query then
    writes into a half-open socket, and with no timeout it blocks until the OS
    TCP retransmit gives up before retrying.

    Measured, one 124-character query:
        back-to-back                 ~290 ms
        after a 10s idle gap      23,498 ms   <- one call, one turn
        same gap, timeout=10s      1,971 ms

    Every turn embeds once (context_agent), so this was ~42% of turn time and
    the single biggest cause of "it took a minute to answer". The timeout is
    what turns a dead connection into a fast retry instead of a stall.
    """
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        api_key=OPENAI_API_KEY,
        timeout=EMBEDDING_TIMEOUT_S,
        max_retries=EMBEDDING_MAX_RETRIES,
    )


@lru_cache(maxsize=1)
def get_collection():
    """The Chroma collection, or None when Chroma is unavailable."""
    try:
        import chromadb
    except ImportError:
        return None

    try:
        client = chromadb.PersistentClient(path=VECTOR_DIR)
        return client.get_or_create_collection(
            name=VECTOR_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
    except Exception:
        # A corrupt or locked store must not take the whole chatbot down.
        return None


def is_available() -> bool:
    """True when the vector store exists and has been seeded."""
    collection = get_collection()
    try:
        return collection is not None and collection.count() > 0
    except Exception:
        return False


def add_documents(
    texts: List[str],
    kind: str = "doc",
    metadatas: Optional[List[Dict[str, Any]]] = None,
    ids: Optional[List[str]] = None,
    id_prefix: str = "",
) -> int:
    """Embed and store texts. Returns how many were written."""
    collection = get_collection()
    if collection is None:
        raise RuntimeError("Chroma is not installed. Run: pip install chromadb")
    if not texts:
        return 0

    vectors = _embeddings().embed_documents(texts)
    ids = ids or [f"{id_prefix or kind}-{i}" for i in range(len(texts))]

    metas = metadatas or [{} for _ in texts]
    for meta in metas:
        meta.setdefault("kind", kind)

    # upsert, so re-seeding replaces instead of duplicating.
    collection.upsert(ids=ids, documents=texts, embeddings=vectors, metadatas=metas)
    return len(texts)


def search(
    query: str,
    top_k: int = RAG_TOP_K,
    kind: Optional[Union[str, List[str]]] = None,
    max_distance: float = RAG_MAX_DISTANCE,
) -> List[str]:
    """
    Documents relevant to the query - not merely the nearest ones.

    `kind` may be a single kind or a list (e.g. ["term", "learned"] so the
    context agent sees both curated and learned mappings). Results beyond
    `max_distance` are dropped, so an empty list genuinely means "nothing
    relevant" - which is what triggers the Knowledge Agent.

    Falls back to keyword search over the business terms when the vector store
    is unavailable, so callers never have to handle "no store yet".
    """
    collection = get_collection()
    if collection is None or not is_available():
        return business_terms.keyword_search(query, top_k)

    if kind is None:
        where = None
    elif isinstance(kind, (list, tuple)):
        where = {"kind": {"$in": list(kind)}}
    else:
        where = {"kind": kind}

    try:
        vector = _embeddings().embed_query(query)
        result = collection.query(query_embeddings=[vector], n_results=top_k, where=where)
        documents = (result.get("documents") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        if not distances:  # some backends omit distances; keep what we got
            return list(documents)

        return [
            document
            for document, distance in zip(documents, distances)
            if distance <= max_distance
        ]
    except Exception:
        return business_terms.keyword_search(query, top_k)


# Cosine-distance width treated as "about as relevant". Two candidates inside
# one band are a tie on relevance, so trust decides; a candidate a full band
# closer wins outright. 0.05 is narrow against the 0.31-0.65 spread actually
# observed, so it only ever merges genuinely comparable matches.
_TRUST_TIE_BAND = 0.05


def _trust_rank(metadata: Dict[str, Any]) -> int:
    """Lower = more trusted. Curated > user-taught > machine-inferred."""
    if metadata.get("kind") == "term":
        return 0
    if metadata.get("source") == "taught":
        return 1
    return 2


def _visibility_filter(user_id: Optional[int]) -> Dict[str, Any]:
    """What this user is allowed to retrieve.

    Curated terms (kind='term') are the company glossary and always visible.
    A learned entry is visible only if it is COMPANY_WIDE - the pre-existing
    accepted vocabulary - or was taught by THIS user. One person's teaching no
    longer answers another person's question.
    """
    owners = [COMPANY_WIDE]
    if user_id:
        owners.append(int(user_id))
    return {
        "$or": [
            {"kind": {"$eq": "term"}},
            {
                "$and": [
                    {"kind": {"$eq": "learned"}},
                    {"owner_id": {"$in": owners}},
                ]
            },
        ]
    }


def search_context(
    query: str, top_k: int = RAG_TOP_K, max_distance: float = RAG_MAX_DISTANCE,
    user_id: Optional[int] = None,
) -> List[str]:
    """
    Term + learned-mapping retrieval for the context agent, ranked by trust
    rather than by raw vector distance alone.

    Runs the same single nearest-neighbour query as before (so relevance is
    judged against the calibrated `max_distance` exactly as it always was -
    querying each kind separately would let a handful of only loosely-related
    curated terms consume the whole result before a much closer, genuinely
    on-topic learned mapping is ever looked at). Pulls a larger candidate pool
    than top_k, keeps only those within `max_distance`, then stable-sorts the
    survivors by trust tier - curated business term, then user-taught mapping,
    then machine-inferred - so a documented or human-confirmed meaning wins a
    tie against a same-topic guess without discarding anything relevant.
    """
    collection = get_collection()
    if collection is None or not is_available():
        return business_terms.keyword_search(query, top_k)

    try:
        vector = _embeddings().embed_query(query)
        pool_size = max(top_k * 3, top_k)
        result = collection.query(
            query_embeddings=[vector],
            n_results=pool_size,
            where=_visibility_filter(user_id),
        )
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0] or [0.0] * len(documents)
    except Exception:
        return business_terms.keyword_search(query, top_k)

    candidates = [
        (document, _trust_rank(metadata or {}), distance)
        for document, metadata, distance in zip(documents, metadatas, distances)
        if distance <= max_distance
    ]
    if not candidates:
        return business_terms.keyword_search(query, top_k)

    # Trust breaks TIES; it does not override relevance.
    #
    # Sorting by trust alone discarded distance entirely once a candidate was
    # inside max_distance, so a handful of only loosely-related curated terms
    # scraping in just under the threshold outranked a bang-on taught mapping.
    # Measured on "what is a purchase order number": the taught
    # `purchase order number` sat at 0.315 - twice as close as anything else -
    # while `pending requisition` (0.628), `export order` (0.636) and
    # `procurement lead time` (0.646) all sorted ahead of it purely for being
    # curated. At top_k=3 the taught term was dropped outright; at top_k=4 it
    # survived only as the last of four. A term could be taught, stored and
    # retrieved into the pool, then pushed out at the final step - which undoes
    # the entire point of teaching it.
    #
    # Bucketing distance into bands and sorting (band, trust) restores the
    # documented intent: a clearly closer match wins on relevance, and trust
    # decides only between candidates of comparable closeness.
    candidates.sort(key=lambda c: (int(c[2] / _TRUST_TIE_BAND), c[1]))
    return [document for document, _, _ in candidates[:top_k]]


# --------------------------------------------------------------------------
#  Curated terms
# --------------------------------------------------------------------------
def seed_business_terms() -> int:
    """Load backend/metadata/business_terms.py into the vector store."""
    documents = business_terms.as_documents()
    metadatas = [
        {"kind": "term", "term": entry["term"]}
        for entry in business_terms.BUSINESS_TERMS
    ]
    ids = [f"term-{i}" for i in range(len(documents))]
    return add_documents(documents, kind="term", metadatas=metadatas, ids=ids)


# --------------------------------------------------------------------------
#  Learned mappings (inferred by the Knowledge Agent, then persisted)
# --------------------------------------------------------------------------
def _learned_path() -> Path:
    return Path(LEARNED_TERMS_PATH)


def load_learned() -> List[Dict[str, Any]]:
    """Read the learned-terms file. Returns [] if it does not exist yet."""
    path = _learned_path()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")) or []
    except (json.JSONDecodeError, OSError):
        return []


def _write_learned(entries: List[Dict[str, Any]]) -> None:
    path = _learned_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


def _learned_raw() -> str:
    path = _learned_path()
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def _entry_id(entry: Dict[str, Any]) -> str:
    """
    Stable id per entry, PER OWNER. Taught terms key by term; inferred by
    question; both are qualified by who owns them.

    The owner used to be missing from this key, and that quietly undid per-user
    scoping one layer below where it was enforced. The store upserts by id, so
    two people teaching the same word produced the SAME id and the second write
    overwrote the first - document, meaning and owner together. The first user
    did not get a wrong answer; their term vanished from retrieval entirely,
    while the learned file still listed it because that de-duplicates per owner.
    Disk said two, the store held one, and retrieval reads the store.
    """
    owner = int(entry.get("user_id") or COMPANY_WIDE)
    if entry.get("term"):
        key = f"term:{_norm(entry['term'])}|owner:{owner}"
    else:
        key = f"q:{_norm(entry.get('question', ''))}|owner:{owner}"
    return "learned-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _entry_doc(entry: Dict[str, Any]) -> str:
    """Embeddable text. Taught terms read like curated terms; inferred read as notes."""
    if entry.get("term"):
        parts = [f"TERM: {entry['term']}", f"MEANING: {entry.get('meaning', '')}"]
        if entry.get("maps_to"):
            parts.append(f"DATABASE MAPPING: {entry['maps_to']}")
        parts.append(f"NOTES: {entry.get('notes', '')} (defined by the user)".strip())
        return "\n".join(parts)
    notes = "\n".join(entry.get("notes", []))
    return (
        "LEARNED MAPPING (inferred from the schema, not yet human-verified) for "
        f"questions like: {entry.get('question', '')}\n{notes}"
    )


# A learned entry owned by nobody is COMPANY-WIDE: every user sees it. That is
# reserved for entries which predate per-user scoping and were accepted as
# vocabulary. Anything taught since carries the real user id and is private to
# them.
COMPANY_WIDE = 0


def _owner_or_none(user_id: Optional[int]) -> Optional[int]:
    """
    The owner to file a new entry under, or None if we cannot tell who it is.

    Deliberately NOT `user_id or COMPANY_WIDE`. That reading turns an unknown
    caller into the company: when the session cookie failed to verify, every
    term taught in that window was written as owner 0 and became authoritative
    for everybody - silently recreating the exact leak per-user scoping exists
    to prevent, and doing it precisely when identity was broken.

    Scoping a teaching to nobody is not a safe default, so there is none: an
    unidentified teaching is refused instead. Note that 0 is a legitimate owner
    value here, so the check is `is None`, not falsiness.
    """
    if user_id is None:
        return None
    return int(user_id)


def _entry_meta(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "kind": "learned",
        "source": entry.get("source", "inferred"),
        "term": entry.get("term", ""),
        "question": entry.get("question", ""),
        "confident": bool(entry.get("confident", True)),
        # Chroma cannot filter on a key that is absent, so this is always
        # written - an entry with no owner is stored as COMPANY_WIDE rather
        # than left blank.
        "owner_id": int(entry.get("user_id") or COMPANY_WIDE),
    }


def _upsert_learned(entries: List[Dict[str, Any]]) -> int:
    if not entries:
        return 0
    texts = [_entry_doc(e) for e in entries]
    ids = [_entry_id(e) for e in entries]
    metas = [_entry_meta(e) for e in entries]
    return add_documents(texts, kind="learned", metadatas=metas, ids=ids)


def sync_learned_to_store() -> int:
    """
    Push every learned entry from disk into the vector store (idempotent), and
    DROP any learned document the file no longer accounts for.

    The prune matters because ids are derived from content and ownership: when
    that derivation changed to include the owner, every document already stored
    kept its old id, so the same term would have existed twice - once under the
    stale unowned id, once correctly owned - and the stale copy would still have
    been retrieved. It also cleans up after an entry removed from the file by
    hand, which previously stayed in the store and kept answering questions.

    The file is the record; this makes the store agree with it.
    """
    entries = load_learned()
    written = _upsert_learned(entries)

    try:
        collection = get_collection()
        if collection is None:
            return written
        expected = {_entry_id(e) for e in entries}
        present = collection.get(where={"kind": "learned"}).get("ids") or []
        stale = [i for i in present if i not in expected]
        if stale:
            collection.delete(ids=stale)
    except Exception:
        # A failed prune leaves duplicates, which is worse than tidy but far
        # better than a sync that raises and leaves the store half-written.
        pass

    return written


def persist_learned_term(
    question: str, notes: List[str], confident: bool = True,
    user_id: Optional[int] = None,
) -> bool:
    """
    Save an inferred mapping so future similar questions reuse it.

    Called only after the quality gate in the API (confident inference that
    produced a working query). Writes to LEARNED_TERMS_PATH for review and
    upserts into the store immediately, so it is usable on the very next turn
    without a restart. De-duplicates by question.
    """
    notes = [n for n in (notes or []) if n and n.strip()]
    if not PERSIST_LEARNED or not question or not notes:
        return False

    # No identifiable user means no owner to scope this to. Refuse rather than
    # let it default to company-wide.
    owner = _owner_or_none(user_id)
    if owner is None:
        return False

    entries = load_learned()
    key = _norm(question)
    entries = [
        e
        for e in entries
        if not (
            _norm(e.get("question", "")) == key
            and int(e.get("user_id") or COMPANY_WIDE) == owner
        )
    ]
    entry = {
        "question": question,
        "notes": notes,
        "source": "inferred",
        "confident": bool(confident),
        "user_id": owner,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    entries.append(entry)
    return _save_and_upsert(entries, entry)


def persist_taught_term(
    term: str, meaning: str, maps_to: str = "", notes: str = "",
    user_id: Optional[int] = None,
) -> bool:
    """
    Save a term the USER explicitly defined.

    Higher trust than an inferred mapping (a person stated it), so it is saved
    immediately. De-duplicates by term, so re-defining a term updates it.
    """
    if not PERSIST_LEARNED or not term or not meaning:
        return False

    # Same rule as an inferred term: unattributable teachings are not saved.
    # This is the one the user actually feels - a term taught anonymously and
    # filed company-wide changes the answers everyone else gets.
    owner = _owner_or_none(user_id)
    if owner is None:
        return False

    entries = load_learned()
    key = _norm(term)
    # De-duplicate WITHIN THIS OWNER only. Keyed on the term alone, one person
    # redefining a word silently replaced everyone else's definition of it.
    entries = [
        e
        for e in entries
        if not (
            _norm(e.get("term", "")) == key
            and int(e.get("user_id") or COMPANY_WIDE) == owner
        )
    ]
    entry = {
        "term": term,
        "meaning": meaning,
        "maps_to": maps_to,
        "notes": notes,
        "source": "taught",
        "confident": True,
        "user_id": owner,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    entries.append(entry)
    return _save_and_upsert(entries, entry)


def _save_and_upsert(entries: List[Dict[str, Any]], new_entry: Dict[str, Any]) -> bool:
    """Write the learned file, push the new entry to the store, refresh the hash."""
    try:
        _write_learned(entries)
        _upsert_learned([new_entry])
    except Exception:
        return False

    # Keep the next startup from re-embedding everything for this one change.
    try:
        state = _read_state()
        state["learned_hash"] = _hash(_learned_raw())
        _write_state(state)
    except Exception:
        pass
    return True


def clear_learned() -> int:
    """
    Delete every learned entry from disk and the store. Returns the number of
    documents actually removed from the store.

    Deletes by METADATA FILTER, not by ids computed from the JSON file. The two
    can drift - an entry written to the store whose file write failed, or a file
    hand-edited afterwards - and an id-based delete can only remove what the
    file still lists, leaving the rest embedded and influencing answers with
    nothing tracking them. Filtering on kind="learned" removes them regardless
    of whether the file ever knew about them.
    """
    collection = get_collection()
    removed = 0

    if collection is not None:
        try:
            existing = collection.get(where={"kind": "learned"}, include=[])
            ids = existing.get("ids") or []
            if ids:
                collection.delete(ids=ids)
            removed = len(ids)
        except Exception:
            pass

    _write_learned([])

    # Keep the stored hash in step, or the next startup would "re-sync" the
    # now-empty file and think something changed.
    try:
        state = _read_state()
        state["learned_hash"] = _hash(_learned_raw())
        _write_state(state)
    except Exception:
        pass

    return removed


# --------------------------------------------------------------------------
#  Startup sync (auto-reseed on change)
# --------------------------------------------------------------------------
def _state_path() -> Path:
    return Path(VECTOR_DIR) / ".seed_state.json"


def _read_state() -> Dict[str, str]:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_state(state: Dict[str, str]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")


def _hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def ensure_seeded() -> Dict[str, Any]:
    """
    Keep the vector store in sync with its sources, cheaply.

    Called once at startup. Re-embeds the curated terms ONLY when
    business_terms.py changed since last time (content hash), and re-syncs
    learned mappings only when their file changed - so an unchanged store costs
    nothing but two hashes. This is what removes the manual re-seed step.
    """
    collection = get_collection()
    if collection is None:
        return {"ok": False, "reason": "vector store unavailable"}

    try:
        was_empty = collection.count() == 0
    except Exception:
        was_empty = True

    state = _read_state()
    terms_hash = _hash("\n".join(business_terms.as_documents()))
    learned_hash = _hash(_learned_raw())

    reseeded_terms = False
    if was_empty or state.get("terms_hash") != terms_hash:
        seed_business_terms()
        reseeded_terms = True

    synced_learned = 0
    if was_empty or state.get("learned_hash") != learned_hash:
        synced_learned = sync_learned_to_store()

    _write_state({"terms_hash": terms_hash, "learned_hash": learned_hash})
    return {
        "ok": True,
        "reseeded_terms": reseeded_terms,
        "synced_learned": synced_learned,
        "was_empty": was_empty,
    }


if __name__ == "__main__":
    args = set(sys.argv[1:])
    if "--list-learned" in args:
        learned = load_learned()
        print(f"{len(learned)} learned entr(ies) in {LEARNED_TERMS_PATH}:")
        for e in learned:
            src = e.get("source", "inferred")
            if e.get("term"):
                print(f"  - [{src}] TERM '{e['term']}' = {e.get('meaning', '')}")
                if e.get("maps_to"):
                    print(f"        maps_to: {e['maps_to']}")
            else:
                print(f"  - [{src}] Q: {e.get('question')}")
                for n in e.get("notes", []):
                    print(f"        {n}")
    elif "--clear-learned" in args:
        removed = clear_learned()
        print(f"Cleared {removed} learned mapping(s).")
    else:
        # Force a full seed (used for first-time setup).
        count = seed_business_terms()
        synced = sync_learned_to_store()
        _write_state(
            {
                "terms_hash": _hash("\n".join(business_terms.as_documents())),
                "learned_hash": _hash(_learned_raw()),
            }
        )
        print(
            f"Seeded {count} business terms + {synced} learned mapping(s) "
            f"into '{VECTOR_COLLECTION}' at {VECTOR_DIR}"
        )
