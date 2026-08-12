"""
FastAPI entry point.

Run from the project root so `backend` is importable:

    venv\\Scripts\\python -m uvicorn backend.app.main:app --reload --port 8000

Docs at http://localhost:8000/docs
"""

import os
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.chatbot import router as chat_router

# Flipped to True once the background warm-up has finished. Only reported on
# /health - nothing waits on it, because every warmed path works cold too,
# just slower.
_WARM = False


def _warm_forecast_libs() -> None:
    """
    Pay statsmodels'/Prophet's import and JIT/BLAS warm-up cost once, here,
    instead of on the first real user's forecast/reorder question. These are
    lazy-imported inside forecast_tools specifically so a missing library
    degrades gracefully rather than crashing startup - but that means the
    first live request would otherwise eat several extra seconds of pure
    import/compilation time on top of its actual computation.
    """
    import numpy as np
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    dummy = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    SARIMAX(dummy, order=(1, 0, 0), enforce_stationarity=False, enforce_invertibility=False).fit(disp=False)

    from backend.config import ENABLE_PROPHET

    if ENABLE_PROPHET:
        import pandas as pd
        from prophet import Prophet

        df = pd.DataFrame({"ds": pd.date_range("2024-01-01", periods=6, freq="MS"), "y": dummy})
        Prophet(yearly_seasonality=False, weekly_seasonality=False, daily_seasonality=False).fit(df)


def _warm_retrieval() -> None:
    """
    Do the first embedding round-trip and Chroma collection load HERE, not on
    the first user's question.

    Measured: the first search_context() costs ~4s (HTTP client setup + the
    embedding call + loading the collection off disk), while every warm call
    after it is ~0.28s. Every data question goes through retrieval, so without
    this the first person to ask anything after a restart waits several seconds
    for infrastructure rather than for their answer.
    """
    from backend.tools.vector_tools import search_context

    search_context("warm up the embedding client and vector collection")


def _warm_schema() -> None:
    """Cache the live schema text once, so the first SQL question skips it."""
    from backend.metadata.schema import get_schema_text

    get_schema_text()


def _preimport_heavy_modules() -> None:
    """
    Import everything the warm-up touches, ON THE MAIN THREAD, before any
    worker thread or request can race for it.

    Python serialises imports per module. When two threads import the same
    module at once, one can deadlock waiting on the other's module lock - and
    that is exactly what a background warm-up creates: the warm-up thread
    importing openai's embedding client while the first request imports it too.
    Observed in the wild as

        Query understanding failed: deadlock detected by
        _ModuleLock('openai.resources.embeddings')

    which surfaces to the user as a failed answer, not a slow one.

    Importing here first makes every later import a cache hit, so no thread
    ever waits on a lock. It costs a second or two on the critical path and is
    the price of the warm-up being concurrent at all.
    """
    import langchain_openai  # noqa: F401  the embedding + chat clients
    import openai  # noqa: F401
    import openai.resources.embeddings  # noqa: F401  the module that deadlocked
    import chromadb  # noqa: F401

    from backend.metadata import schema  # noqa: F401
    from backend.tools import vector_tools  # noqa: F401


def _warm_everything() -> None:
    """
    All the startup warm-up, off the critical path.

    Each step is wrapped separately so one failure does not skip the rest -
    a missing Prophet install should not cost us the retrieval warm-up.
    """
    global _WARM
    started = time.time()

    # The chat tables, created up front rather than on first successful write.
    #
    # They used to appear only when somebody was identified and a turn was
    # stored. On a machine where the JWT secret did not match the ERP's, nobody
    # ever was - so the tables were never created either, and one configuration
    # fault presented as two unrelated ones: no conversations, and no table to
    # look in. Creating them here means the schema is always present and the
    # only remaining question is whether rows arrive, which is a much shorter
    # trail to follow.
    try:
        from backend.database import chat_log
        from backend.database import conversation_store

        made = [
            name
            for name, ok in (
                ("chatbot_conversations", conversation_store.ensure_table()),
                ("chatbot_messages", chat_log.ensure_table()),
            )
            if ok
        ]
        if len(made) == 2:
            print("[warmup] chat tables ready", flush=True)
        else:
            print(
                "[warmup] CHAT TABLES NOT READY - conversations will not be "
                "stored. Check the database user can CREATE tables.",
                flush=True,
            )
    except Exception as exc:
        print(f"[warmup] chat table setup skipped: {exc}", flush=True)

    # Keep the vector store in sync with its sources: re-seed curated terms
    # only if business_terms.py changed, and load any learned mappings from
    # disk. Removes the manual re-seed step.
    try:
        from backend.tools.vector_tools import ensure_seeded

        summary = ensure_seeded()
        print(f"[warmup] vector store: {summary}", flush=True)
    except Exception as exc:
        print(f"[warmup] vector store sync skipped: {exc}", flush=True)

    try:
        _warm_forecast_libs()
        print("[warmup] forecast libraries warmed", flush=True)
    except Exception as exc:
        print(f"[warmup] forecast library warm-up skipped: {exc}", flush=True)

    try:
        _warm_retrieval()
        _warm_schema()
        print("[warmup] retrieval + schema warmed", flush=True)
    except Exception as exc:
        print(f"[warmup] retrieval warm-up skipped: {exc}", flush=True)

    _WARM = True
    print(f"[warmup] complete in {time.time() - started:.1f}s - "
          "first question is now fast", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The warm-up runs on a BACKGROUND THREAD, not here.
    #
    # Uvicorn does not bind the port until this function reaches `yield`, so
    # doing the warm-up inline meant the server refused connections for ~60s
    # (fitting a throwaway SARIMAX model, an embedding round-trip, and reading
    # the live schema). Anyone who started the frontend straight after the
    # backend saw "backend not connected" for a full minute and reasonably
    # concluded it was broken.
    #
    # Nothing depends on the warm-up having finished: every path it touches
    # works cold, just slower. So serve immediately and warm up alongside.
    # Imports FIRST, on this thread. Concurrent imports of the same module
    # deadlock, so the warm-up thread must never be the one to import
    # something a request might also be importing.
    try:
        _preimport_heavy_modules()
    except Exception as exc:
        print(f"[startup] pre-import skipped: {exc}", flush=True)

    threading.Thread(target=_warm_everything, name="warmup", daemon=True).start()
    print("[startup] serving now; warming up in the background", flush=True)

    yield


app = FastAPI(
    title="Supply Chain Assistant API",
    description="LangGraph chatbot over the Organizatoin's supply chain database.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS. Two layers:
#   * A regex that accepts localhost / 127.0.0.1 on ANY port, so the frontend
#     works whether Vite lands on 5173, 5174, ... and whether you open it via
#     "localhost" or "127.0.0.1" (a browser treats those as different origins,
#     which is the usual cause of a 400 on the OPTIONS preflight).
#   * An explicit list from CORS_ORIGINS in .env, for real deployed domains.
_LOCAL_ORIGIN_REGEX = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"

_extra = os.getenv("CORS_ORIGINS", "")
_explicit_origins = [o.strip() for o in _extra.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_explicit_origins,
    allow_origin_regex=_LOCAL_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api")


@app.get("/")
def root():
    return {"service": "supply-chain-assistant", "docs": "/docs"}
