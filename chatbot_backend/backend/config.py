"""
Central configuration for the chatbot backend.

Every credential, model name and tunable comes from the .env file in the
project root. No other module calls os.getenv() — they import from here, so
changing .env is the only thing needed to point the bot at a different
database, model or vector store.

Required keys in .env:

    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
    OPENAI_API_KEY, OPENAI_MODEL

Optional keys (see .env for the defaults we ship):

    LLM_TEMPERATURE, EMBEDDING_MODEL, RAG_TOP_K,
    SQL_ROW_LIMIT, SQL_TIMEOUT_MS, SQL_MAX_RETRIES,
    VECTOR_DIR, VECTOR_COLLECTION
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")


class ConfigError(RuntimeError):
    """Raised when a required .env key is missing, so failures are obvious."""


def _required(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value:
        raise ConfigError(
            f"{key} is not set. Add it to {PROJECT_ROOT / '.env'} and restart."
        )
    return value


def _optional(key: str, default: str) -> str:
    value = os.getenv(key, "").strip()
    return value or default


# --- LLM -------------------------------------------------------------
OPENAI_API_KEY = _required("OPENAI_API_KEY")
OPENAI_MODEL = _required("OPENAI_MODEL")

# Some newer models only accept their default temperature, so we send it
# only when .env explicitly asks for one.
_temperature = os.getenv("LLM_TEMPERATURE", "").strip()
LLM_TEMPERATURE = float(_temperature) if _temperature else None

# Reasoning models reject function tools on /v1/chat/completions, which is what
# structured output needs. The Responses API supports both, so we default to it.
USE_RESPONSES_API = os.getenv("OPENAI_USE_RESPONSES_API", "true").strip().lower() in (
    "1", "true", "yes",
)

# Transient connection errors are the single most common way a turn dies, so
# retry each model call a few times before giving up on the whole answer.
# NOTE: the OpenAI SDK applies `timeout` PER ATTEMPT, not per call, so the real
# worst case for one call is timeout x (retries + 1) plus backoff. At 45s x 5
# that was 232s for a single call, and a turn makes 4-5 sequential calls - up to
# ~19 minutes before the user saw anything. Retries exist for transient
# connection errors, which succeed on the first retry or not at all; 2 keeps
# that protection while bounding one call to ~140s.
LLM_MAX_RETRIES = int(_optional("LLM_MAX_RETRIES", "2"))
# Per-call ceiling. A turn makes 4-5 of these calls IN SEQUENCE, so one slow
# draw anywhere in the chain dominates the whole response time.
# Measured per node (uncached): understand 1.6-1.7s, generate_sql 1.9-3.8s,
# respond 1.1-3.1s - the slowest legitimate call seen is 3.8s. But the provider
# tail is long and unrelated to prompt size: the SAME understand call measured
# 1.6s twice and 12.6s once, and an identical trivial call has measured 62s.
# 20s is ~5x headroom over the slowest real call while cutting a 45s+ hang to
# one retry, which normally lands in ~2s. Raise it if a legitimately heavy
# prompt ever starts timing out; do not raise it to accommodate the tail.
LLM_TIMEOUT_S = float(_optional("LLM_TIMEOUT_S", "20"))
# Every call in this app is structured/schema-constrained (classification,
# entity extraction, SQL against a fixed schema) rather than open-ended
# reasoning, and this model's default (unset) reasoning effort measured
# dramatically slower AND far more variable in testing than an explicit low
# setting, with no accuracy difference on these tasks. "none" is also valid
# for this model but risks under-thinking a genuinely tricky SQL question;
# "low" is the safer floor.
LLM_REASONING_EFFORT = _optional("LLM_REASONING_EFFORT", "low")


# --- Database ---------------------------------------------------------
DB_HOST = _required("DB_HOST")
DB_PORT = _required("DB_PORT")
DB_NAME = _required("DB_NAME")
DB_USER = _required("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")  # may legitimately be blank

DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)


# --- SQL guardrails ---------------------------------------------------
# 0 (the default) means NO row cap - the user sees every matching row, in a
# scrollable/sortable/searchable table, rather than a silent top-100. The real
# safety net against a runaway query is SQL_TIMEOUT_MS plus the READ ONLY
# transaction (see tools/postgres_tools.py), not this. Set a positive number
# here to cap rows again if a specific deployment needs it.
SQL_ROW_LIMIT = int(_optional("SQL_ROW_LIMIT", "0"))
# Higher than a typical capped query needed, because an uncapped SELECT over a
# large table takes longer to fully scan.
SQL_TIMEOUT_MS = int(_optional("SQL_TIMEOUT_MS", "30000"))
SQL_MAX_RETRIES = int(_optional("SQL_MAX_RETRIES", "2"))


# --- Dynamic computation (code interpreter) ---------------------------
# When on, the assistant may write and run Python over query results for
# questions SQL/forecast cannot answer. This EXECUTES LLM-generated code in a
# guarded sandbox (backend/tools/sandbox.py). Set ENABLE_COMPUTE=false to
# disable code execution entirely.
ENABLE_COMPUTE = _optional("ENABLE_COMPUTE", "true").lower() in ("1", "true", "yes")
COMPUTE_TIMEOUT_S = float(_optional("COMPUTE_TIMEOUT_S", "10"))
COMPUTE_MAX_RETRIES = int(_optional("COMPUTE_MAX_RETRIES", "1"))


# --- Forecasting ------------------------------------------------------
# Seasonal cycle length for the series being forecast. 12 = monthly data with a
# yearly season (the usual case here). Seasonal models (SARIMA/Prophet) only
# engage when there are at least 2 full cycles of history; otherwise the engine
# falls back to a linear trend. ENABLE_PROPHET can force Prophet off even when
# installed (it is heavy); SARIMA via statsmodels is the lighter default.
FORECAST_SEASONAL_PERIODS = int(_optional("FORECAST_SEASONAL_PERIODS", "12"))
ENABLE_PROPHET = _optional("ENABLE_PROPHET", "true").lower() in ("1", "true", "yes")


# --- Observability ----------------------------------------------------
# Print every OpenAI call (messages sent + answer + token usage) to the
# terminal, with a running call counter. Handy for tracking how many calls a
# question makes and what is being sent. Set LOG_LLM=false to silence.
LOG_LLM = _optional("LOG_LLM", "true").lower() in ("1", "true", "yes")
# Per-message character cap so a big schema prompt does not flood the terminal.
# Set to 0 for no truncation.
LOG_LLM_MAX_CHARS = int(_optional("LOG_LLM_MAX_CHARS", "1000"))


# --- Vector store (business terminology / document RAG) ---------------
VECTOR_DIR = _optional("VECTOR_DIR", str(PROJECT_ROOT / ".chroma"))
VECTOR_COLLECTION = _optional("VECTOR_COLLECTION", "supply_chain_knowledge")
EMBEDDING_MODEL = _optional("EMBEDDING_MODEL", "text-embedding-3-small")

# An EXPLICIT embedding timeout, because the default is None and that cost
# whole minutes per turn. The HTTP pool drops an idle connection after ~5s and
# every turn leaves a longer gap than that while the chat model thinks; the next
# embed then writes into a half-open socket and, with no timeout, blocks on the
# OS TCP retransmit. Measured on one 124-char query: 290ms back-to-back, but
# 23,498ms after a 10s gap - and 1,971ms once a timeout was set.
EMBEDDING_TIMEOUT_S = float(_optional("EMBEDDING_TIMEOUT_S", "10"))
EMBEDDING_MAX_RETRIES = int(_optional("EMBEDDING_MAX_RETRIES", "3"))
RAG_TOP_K = int(_optional("RAG_TOP_K", "4"))

# When on, a term mapping the Knowledge Agent had to infer (because nothing was
# documented) is saved AFTER it produced a working query, so the next similar
# question reuses it instead of re-deriving. Saved to LEARNED_TERMS_PATH for
# human review; set PERSIST_LEARNED=false to disable.
PERSIST_LEARNED = _optional("PERSIST_LEARNED", "true").lower() in ("1", "true", "yes")
LEARNED_TERMS_PATH = _optional(
    "LEARNED_TERMS_PATH", str(PROJECT_ROOT / "backend" / "metadata" / "learned_terms.json")
)

# Cosine distance above which a retrieved document is treated as unrelated.
# Without this, nearest-neighbour search always returns something, so the
# "knowledge found?" branch could never be false. 0 = identical, 2 = opposite.
#
# Measured against the seeded terminology: documented questions score 0.31-0.63,
# undocumented ones 0.69+. Re-check this with tools/check_rag_threshold.py after
# adding a batch of new terms - the separation shifts as the corpus grows.
RAG_MAX_DISTANCE = float(_optional("RAG_MAX_DISTANCE", "0.65"))

# --- how much of the result the answering model actually reads -------------
# Budgeted in CHARACTERS, not rows, because row size varies by two orders of
# magnitude: a 2-column consumption series is ~70 chars/row while a 46-column
# logistics_consignments row is ~1,255. A fixed "60 rows" therefore sent 4k
# characters of one and 75k of the other. The same budget adapts:
#
#     ~70 chars/row  ->  ~3,500 rows
#    ~207 chars/row  ->  ~1,200 rows
#  ~1,255 chars/row  ->    ~200 rows
#
# 250k characters is roughly 60k tokens - generous, and still far inside the
# context window, leaving room for the schema, the business terms and the
# conversation. Raise it if answers still feel like they are working from a
# sample; there is no correctness reason to keep it low.
LLM_ROW_CHAR_BUDGET = int(_optional("LLM_ROW_CHAR_BUDGET", "250000"))

# A backstop so a pathologically narrow result (one tiny column) cannot send
# hundreds of thousands of rows and blow the request up.
LLM_ROW_HARD_CAP = int(_optional("LLM_ROW_HARD_CAP", "5000"))

# --- query cache ----------------------------------------------------------
# Remember the SQL that answered a question and replay it next time, instead of
# writing a new query from scratch. The SQL agent produced up to FIVE different
# queries for one question across five runs; they agreed only because the
# business terms were pinned tightly enough to force it. Replaying makes a
# repeat question identical by construction, and skips the slowest LLM call.
#
# Only a query that ran cleanly AND returned rows is remembered.
ENABLE_QUERY_CACHE = _optional("ENABLE_QUERY_CACHE", "true").lower() in ("1", "true", "yes")
QUERY_CACHE_PATH = _optional(
    "QUERY_CACHE_PATH", str(PROJECT_ROOT / "backend" / "metadata" / "query_cache.json")
)
# Much tighter than RAG_MAX_DISTANCE. Ordinary retrieval wants anything related;
# this decides whether to REUSE a query verbatim, where a near-miss silently
# answers a different question. "stock of resin" and "stock of steel" sit close
# together in embedding space, so the bar has to be high - and the entity key
# must match as well before a near hit is accepted.
QUERY_CACHE_MAX_DISTANCE = float(_optional("QUERY_CACHE_MAX_DISTANCE", "0.15"))

# One extra attempt when a query returns NOTHING, telling the model to question
# its own filters. Three real bugs (an over-narrow item_code, a doubled
# backslash in a regex, and AND where OR was meant) all surfaced as a confident
# "0" rather than an error, so nothing flagged them.
ZERO_ROW_RETRY = _optional("ZERO_ROW_RETRY", "true").lower() in ("1", "true", "yes")


@lru_cache(maxsize=4)
def get_llm(effort: Optional[str] = None):
    """
    Shared chat model, cached per reasoning-effort level.

    A turn makes 4-5 sequential calls and total latency is dominated by
    round-trips, not tokens - so the effort each call spends is the main speed
    lever. The calls are NOT equal, though: classification (routing, analysis
    type) is easy and wants speed; writing SQL against a large schema is where
    a wrong answer actually comes from and deserves more thinking. Callers pick
    via structured_llm(..., effort=...); `None` uses LLM_REASONING_EFFORT.
    """
    from langchain_openai import ChatOpenAI

    # Lazy import avoids a config <-> observability import cycle; by call time
    # config is fully loaded. The callback logs every request/response.
    from backend.observability import llm_logger

    kwargs = {
        "model": OPENAI_MODEL,
        "api_key": OPENAI_API_KEY,
        "use_responses_api": USE_RESPONSES_API,
        "callbacks": [llm_logger],
        # A transient network blip on any single agent call otherwise fails the
        # WHOLE turn ("Response generation failed: Connection error"), losing
        # work already done - the SQL that ran, the forecast that was computed.
        # Retrying the one call is far cheaper than losing the answer.
        "max_retries": LLM_MAX_RETRIES,
        "timeout": LLM_TIMEOUT_S,
        "reasoning_effort": effort or LLM_REASONING_EFFORT,
    }
    if LLM_TEMPERATURE is not None:
        kwargs["temperature"] = LLM_TEMPERATURE
    return ChatOpenAI(**kwargs)


# Per-role effort. Classification calls are simple and want speed; SQL
# generation is where accuracy is won or lost, so it gets more thinking.
EFFORT_FAST = _optional("LLM_EFFORT_FAST", "low")       # routing, analysis type
EFFORT_ACCURATE = _optional("LLM_EFFORT_ACCURATE", "medium")  # SQL, knowledge


def structured_llm(schema, effort: Optional[str] = None):
    """
    LLM that returns an instance of `schema` (a pydantic model).

    Uses function calling rather than OpenAI's strict json_schema mode, because
    strict mode rejects dict-typed and defaulted fields, which our schemas use.
    """
    return get_llm(effort).with_structured_output(schema, method="function_calling")


@lru_cache(maxsize=1)
def get_engine():
    """Shared SQLAlchemy engine built from the .env credentials."""
    from sqlalchemy import create_engine

    # pool_pre_ping avoids stale-connection errors after the DB idles.
    return create_engine(DATABASE_URL, pool_pre_ping=True)
