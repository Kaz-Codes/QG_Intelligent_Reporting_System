@echo off
REM One command to run the whole stack: the ERP backend (:8000), the chatbot
REM backend (:8010, proxied through the ERP backend at /chatbot/* - see
REM app/chatbot_proxy.py so the frontend never needs to know about it), and the
REM React frontend (:5173). Each opens in its own window so you can read its
REM logs and Ctrl+C it individually; closing this window does not stop them.
REM
REM PORTABLE ON PURPOSE. Every path is derived from where this file sits
REM (%~dp0), so the project can live on any drive, in any folder, with spaces
REM in the name, and be run from any working directory.
REM
REM IT ALSO DOES NOT INSIST ON A VENV PER FOLDER. Each service looks for its
REM own venv, then a shared one at the project root, then falls back to
REM whatever `python` is on PATH. One venv for everything is fine; three is
REM fine; none is fine if the packages are installed globally.

setlocal EnableDelayedExpansion
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

REM ---------------------------------------------------------------- chatbot
call :find_python "%ROOT%\chatbot_backend" CHATBOT_PY
if not defined CHATBOT_PY goto :no_python

REM ------------------------------------------------------------------- ERP
call :find_python "%ROOT%" ERP_PY
if not defined ERP_PY goto :no_python

REM -------------------------------------------------------------- frontend
set "FRONTEND=%ROOT%\React_Frontend-main\frontend"
if not exist "%FRONTEND%\package.json" (
    echo(
    echo   ERROR: no frontend found at
    echo          %FRONTEND%
    goto :end
)
if not exist "%FRONTEND%\node_modules" (
    echo(
    echo   ERROR: the frontend has no node_modules. Run this once:
    echo          cd /d "%FRONTEND%" ^&^& npm install
    goto :end
)

echo(
echo   chatbot python : !CHATBOT_PY!
echo   erp python     : !ERP_PY!
echo(

echo Starting chatbot backend on :8010 ...
start "Chatbot Backend :8010" /D "%ROOT%\chatbot_backend" cmd /k ""!CHATBOT_PY!" -m uvicorn backend.app.main:app --reload --port 8010"

timeout /t 2 /nobreak >nul

echo Starting ERP backend on :8000 (proxies /chatbot/* to :8010) ...
start "ERP Backend :8000" /D "%ROOT%" cmd /k ""!ERP_PY!" -m uvicorn app.main:app --reload --port 8000"

timeout /t 2 /nobreak >nul

echo Starting frontend on :5173 ...
start "Frontend :5173" /D "%FRONTEND%" cmd /k "npm run dev"

echo(
echo All three started in their own windows. Open http://localhost:5173 once they warm up.
echo (Chatbot backend: ~15-30s. ERP backend + frontend: a few seconds.)
goto :end

REM ---------------------------------------------------------------------------
REM :find_python <folder> <out-var>
REM   That folder's own venv, else a shared venv at the project root, else
REM   whatever python is on PATH. Checking in that order means a per-service
REM   venv still wins when one exists, so nobody's existing setup changes.
REM ---------------------------------------------------------------------------
:find_python
set "_dir=%~1"
set "%~2="
if exist "%_dir%\venv\Scripts\python.exe"  set "%~2=%_dir%\venv\Scripts\python.exe"  & exit /b
if exist "%_dir%\.venv\Scripts\python.exe" set "%~2=%_dir%\.venv\Scripts\python.exe" & exit /b
if exist "%ROOT%\venv\Scripts\python.exe"  set "%~2=%ROOT%\venv\Scripts\python.exe"  & exit /b
if exist "%ROOT%\.venv\Scripts\python.exe" set "%~2=%ROOT%\.venv\Scripts\python.exe" & exit /b
where python >nul 2>&1 && set "%~2=python"
exit /b

:no_python
echo(
echo   ERROR: no Python found.
echo(
echo   Looked for a venv in the service folder, then a shared one at
echo   %ROOT%, then `python` on PATH. Do ONE of these:
echo(
echo     python -m venv "%ROOT%\venv"
echo     "%ROOT%\venv\Scripts\pip" install -r "%ROOT%\requirements.txt"
echo     "%ROOT%\venv\Scripts\pip" install -r "%ROOT%\chatbot_backend\requirements.txt"
echo(
echo   ...or just install Python and put it on PATH.
goto :end

:end
endlocal
