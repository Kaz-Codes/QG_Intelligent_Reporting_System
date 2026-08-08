# Supply Chain Chatbot — Backend

LangGraph agent workflow over the supply chain Postgres database, exposed as a
FastAPI service for the React frontend.

## Flow

```
understand ─┬─ smalltalk ──────────────────────► respond
            ├─ clarify ────────────────────────► respond
            ├─ docs ──► retrieve_docs ─────────► respond
            └─ data ──► resolve_item ──► same-name item(s)?
                                            │  ambiguous
                                            │  └─► respond (clarify + table)
                                            │  resolved / none
                                            └──► context ──► knowledge found?
                                                               │  no
                                                               │  └─► knowledge ─┐
                                                               │  yes            │
                                                               └─────────────────┴─► generate_sql
                                                                                        │
                                                    ┌── retry ×2 ───────────────────────┤
                                                    ▼                                    ▼
                                               generate_sql ◄───────────────────────execute_sql
                                                                                        │ ok
                                                                                        ▼
                                                              analyze ──► forecast ──► respond
                                                                     └──────────────► respond
```

* **understand** rewrites the message so it stands alone (this is what makes
  "what about the highest?" work), then routes it.
* **resolve_item** looks up the named item in the item master. Many item names
  are shared by hundreds of item_codes with different specs ("Round Bar" alone
  spans 1000+) - when that's true, it asks which one(s) are wanted (one, a few,
  or all) with the matching rows attached, using the same clarify route and
  table rendering as any other answer. A follow-up reply is resolved fresh each
  turn: an exact item_code or "all/any/every" is caught deterministically, a
  descriptive reply ("the EN8 one") falls back to a small LLM check.
* **context** retrieves business terminology and its column mappings — this
  feeds the SQL agent, it does not answer anything. It returns only documents
  that clear `RAG_MAX_DISTANCE`, so an empty result genuinely means "not
  documented".
* **knowledge** is the recovery path. When the knowledge base has nothing, it
  derives the term→column mapping from the raw schema and rejoins the SQL path,
  so undocumented terminology never dead-ends. `knowledge_inferred` in the
  response flags it — those questions are the ones worth adding to
  `metadata/business_terms.py`.
* **retrieve_docs** is the separate RAG path, for questions the database cannot
  answer ("what does ALC mean").
* **execute_sql** loops back to **generate_sql** on failure with Postgres's own
  error message attached, up to `SQL_MAX_RETRIES`.
* **analyze** decides *whether* a forecast is warranted; **forecast** does the
  maths. The LLM never computes projections itself.

## Layout

| Path | What it does |
|---|---|
| `config.py` | Every credential and tunable, read from `.env`. Nothing else calls `os.getenv`. |
| `state.py` | `ChatState` + `fresh_turn()` (per-turn scratch reset). |
| `graph/workflow.py` | Node wiring and the routing functions. |
| `graph/memory.py` | Checkpointer. In-process today; swap for `PostgresSaver` to persist. |
| `agents/` | One file per agent. Each is a plain function `state -> partial state`. |
| `prompts/` | All prompt text. Agents import from here. |
| `tools/tools.py` | SQL safety validation. |
| `tools/postgres_tools.py` | Read-only query execution. |
| `tools/vector_tools.py` | Chroma vector store (business terms + documents). |
| `tools/check_rag_threshold.py` | Calibrates `RAG_MAX_DISTANCE`. Run after seeding new terms. |
| `tools/forecast_tools.py` | Trend and projection maths. |
| `metadata/schema.py` | Schema handed to the SQL agent (live, with static fallback). |
| `metadata/business_terms.py` | Company terminology and its database mappings. |
| `api/chatbot.py` | `/api/chat`, `/api/chat/{thread_id}/history`, `/api/health`. |
| `app/main.py` | FastAPI app + CORS. |

## Running

# The vector store now self-seeds on startup: ensure_seeded() re-embeds the
# business terms only when business_terms.py changed. So after editing terms,
# just restart the backend - no manual seed step. To force a seed anyway:
venv\Scripts\python -m backend.tools.vector_tools

# after adding terms: check the knowledge-found threshold still separates
venv\Scripts\python -m backend.tools.check_rag_threshold

# review / clear mappings the Knowledge Agent has learned and persisted
venv\Scripts\python -m backend.tools.vector_tools --list-learned
venv\Scripts\python -m backend.tools.vector_tools --clear-learned

# start the API (from the project root, so `backend` is importable)
venv\Scripts\python -m uvicorn backend.app.main:app --reload --port 8000
```

Docs at http://localhost:8000/docs

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"which 5 items have the lowest available stock?\"}"
```

The response carries a `thread_id`. **Send it back on every follow-up message** —
that is what gives the conversation memory. Omit it to start a fresh chat.

## Configuration

All in `.env`. Required: `DB_*`, `OPENAI_API_KEY`, `OPENAI_MODEL`. Optional
tunables (`SQL_ROW_LIMIT`, `SQL_MAX_RETRIES`, `SQL_TIMEOUT_MS`, `RAG_TOP_K`,
`VECTOR_DIR`, …) are listed in `.env` with their defaults. A missing required
key raises `ConfigError` at import rather than failing mid-conversation.

`OPENAI_USE_RESPONSES_API=true` is required for reasoning models — they reject
function tools (which structured output needs) on `/v1/chat/completions`.

## Safety

Generated SQL passes `tools.prepare_sql()`: markdown/comment stripping, single
statement only, must start with `SELECT` or `WITH`, whole-word keyword blocklist,
no `pg_sleep`/file functions, and a `LIMIT` appended if absent. Execution then
runs in a `READ ONLY` transaction with `statement_timeout`.

**Still to do:** point `DB_USER` at a Postgres role with `SELECT`-only grants.
The checks above are defence in depth, not a substitute for that.

## Dependencies

Beyond what was already installed: `fastapi`, `chromadb`.

## Known gaps

* Memory is in-process — lost on restart, not shared across workers. Install
  `langgraph-checkpoint-postgres` and swap `graph/memory.py` over.
* Only business terminology is seeded into the vector store. Load real policy
  documents with `vector_tools.add_documents(texts, kind="doc")` to make the
  docs path genuinely useful.
* `database/data_access.py` is the old Streamlit data layer — it imports
  `stubs.fake_data` and a stale `backend.db_connection` path. Not used by the
  chatbot; clean up when the frontend is wired.
