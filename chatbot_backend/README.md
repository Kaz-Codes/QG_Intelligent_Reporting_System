# Chatbot backend

Moved in from `Supply Chain Bot V2` (unchanged internals — package name is
still `backend`, so nothing inside it had to be edited). A standalone FastAPI
service, separate from this ERP's own `app/` backend: different stack
(LangGraph + OpenAI text-to-SQL, chromadb, statsmodels), different port,
no shared auth. Both point at the same Postgres database.

## Run

```
venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --port 8010
```

Docs at http://localhost:8010/docs, health at http://localhost:8010/api/health.

The React app's Assistant page is already pointed at port 8010 by default
(`VITE_CHATBOT_API_BASE_URL` in `React_Frontend-main/frontend/.env`).

## Setup already done

- `venv/` created with `C:\Python314\python.exe`, `pip install -r requirements.txt`
  (minus `prophet` — `ENABLE_PROPHET=false` in `.env`, so it's never imported;
  install it too if you ever flip that on).
- `.env` copied over as-is (same DB, same OpenAI key).
- `.chroma/` (the seeded vector store of business terms + learned mappings)
  copied over so it doesn't need to re-embed everything on first run.

## Everything else

See `AGENT_LOG.md` and `CLAUDE.md` in the original `Supply Chain Bot V2`
project for the full history of how this was built — not copied here since
it documents the old repo's development, not this one.
