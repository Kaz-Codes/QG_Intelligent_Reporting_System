@echo off
REM One command to run the whole stack: the ERP backend (:8000), the chatbot
REM backend (:8010, proxied through the ERP backend at /chatbot/* - see
REM app/chatbot_proxy.py so the frontend never needs to know about it), and
REM the React frontend (:5173). Each opens in its own window so you can see
REM its logs and Ctrl+C it individually; closing this window does not stop
REM them.
REM
REM First-time setup this does NOT do for you:
REM   - chatbot_backend\venv  ->  cd chatbot_backend && python -m venv venv && venv\Scripts\pip install -r requirements.txt
REM   - venv (this folder)    ->  python -m venv venv && venv\Scripts\pip install -r requirements.txt
REM   - React_Frontend-main\frontend\node_modules  ->  cd React_Frontend-main\frontend && npm install
REM Run those once, then this script every time after.

set ROOT=%~dp0

echo Starting chatbot backend on :8010 ...
start "Chatbot Backend :8010" /D "%ROOT%chatbot_backend" cmd /k "venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --port 8010"

timeout /t 2 /nobreak >nul

echo Starting ERP backend on :8000 (proxies /chatbot/* to :8010) ...
start "ERP Backend :8000" /D "%ROOT%" cmd /k "venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"

timeout /t 2 /nobreak >nul

echo Starting frontend on :5173 ...
start "Frontend :5173" /D "%ROOT%React_Frontend-main\frontend" cmd /k "npm run dev"

echo.
echo All three started in their own windows. Open http://localhost:5173 once they warm up.
echo (Chatbot backend: ~15-30s. ERP backend + frontend: a few seconds.)
