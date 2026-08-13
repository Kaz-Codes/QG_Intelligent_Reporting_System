@echo off
REM ===========================================================================
REM  One command to run the whole stack from a SINGLE venv at the project root:
REM
REM     :8010  chatbot backend   (chatbot_backend/)
REM     :8000  ERP backend       (app/)  - proxies the chatbot at /chatbot/*
REM     :5173  React frontend    (React_Frontend-main/frontend/)
REM
REM  Each opens in its own window so you can read its logs and Ctrl+C it on its
REM  own; closing this window does not stop them.
REM
REM  IT SETS ITSELF UP. If the root venv is missing it is created; if the
REM  packages are not all there they are installed; if the frontend has no
REM  node_modules, npm install runs. A fresh clone needs nothing but Python,
REM  Node and this file.
REM
REM  ONE VENV, NOT THREE. Both backends run from %ROOT%\venv. The ERP's
REM  requirements are installed first and the chatbot's second, because the
REM  chatbot pins exact versions (fastapi==, langchain==) while the ERP does
REM  not - installing it last lets the pins win instead of being quietly
REM  downgraded by an unpinned resolve.
REM
REM  PORTABLE. Every path comes from where this file sits (%~dp0), so the
REM  project can live on any drive, in any folder, with spaces in the name, and
REM  be started from any working directory.
REM ===========================================================================

setlocal EnableDelayedExpansion
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "VENV=%ROOT%\venv"
set "PY=%VENV%\Scripts\python.exe"
set "FRONTEND=%ROOT%\React_Frontend-main\frontend"

echo(
echo  QG-IRS  -  starting from %ROOT%
echo(

REM ------------------------------------------------------------ 1. the venv
if not exist "%PY%" (
    echo  [1/4] No venv at %VENV% - creating one...
    call :find_base_python BASE
    if not defined BASE goto :no_python
    "!BASE!" -m venv "%VENV%"
    if not exist "%PY%" (
        echo(
        echo   ERROR: could not create a virtual environment.
        echo          Tried: !BASE! -m venv "%VENV%"
        goto :end
    )
    echo        created.
) else (
    echo  [1/4] Using venv at %VENV%
)

REM ------------------------------------------------- 2. the Python packages
REM  Probed rather than installed every time: `pip install -r` takes half a
REM  minute even when everything is already present. The probe names one
REM  import from each area both services need - if any is missing the whole
REM  set is installed. prophet is deliberately NOT probed: it is heavy, it is
REM  optional (the chatbot logs a warm-up skip and carries on without it), and
REM  a failed build would otherwise re-trigger a full install on every start.
"%PY%" -c "import fastapi, uvicorn, pydantic, sqlalchemy, psycopg2, jose, dotenv, langgraph, langchain_openai, chromadb, pandas, numpy" >nul 2>&1
if errorlevel 1 (
    echo  [2/4] Installing Python packages ^(first run takes several minutes^)...
    "%PY%" -m pip install --upgrade pip >nul 2>&1
    REM  BOTH FILES IN ONE RESOLVE, not one install after another. Installing
    REM  them sequentially lets the second quietly override versions the first
    REM  needed, leaving a set that satisfies neither - and pip would not
    REM  complain, because each install succeeded on its own. Naming both here
    REM  makes pip solve them together, so a genuine conflict fails loudly
    REM  instead of being papered over.
    "%PY%" -m pip install -r "%ROOT%\requirements.txt" -r "%ROOT%\chatbot_backend\requirements.txt"
    if errorlevel 1 goto :pip_failed
    echo        done.
) else (
    echo  [2/4] Python packages already present
)

REM ------------------------------------------------------- 3. the front end
if not exist "%FRONTEND%\package.json" (
    echo(
    echo   ERROR: no frontend found at
    echo          %FRONTEND%
    goto :end
)
if not exist "%FRONTEND%\node_modules" (
    echo  [3/4] Installing frontend packages ^(first run takes a few minutes^)...
    pushd "%FRONTEND%"
    call npm install
    popd
) else (
    echo  [3/4] Frontend packages already present
)

REM ------------------------------------------------------------- 4. warnings
REM  Not fatal, but both cost an afternoon when they are wrong, so they are
REM  said out loud before anything starts rather than discovered later.
if not exist "%ROOT%\.env" (
    echo(
    echo   WARNING: no .env at the project root. The ERP needs its database
    echo            settings and JWT_SECRET_KEY there.
)
call :port_busy 8000 && echo   WARNING: port 8000 is already in use - the ERP backend will not start.
call :port_busy 8010 && echo   WARNING: port 8010 is already in use - the chatbot will not start.
call :port_busy 5173 && echo   WARNING: port 5173 is already in use - Vite will pick another port.

REM ---------------------------------------------------------------- 5. go
echo  [4/4] Starting services...
echo(

REM  The chatbot first: the ERP proxies to it, so starting it second means the
REM  first /chatbot request can arrive before it is listening.
start "QG-IRS chatbot :8010" /d "%ROOT%\chatbot_backend" cmd /k ""%PY%" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010"
start "QG-IRS ERP :8000"     /d "%ROOT%"                 cmd /k ""%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "QG-IRS frontend :5173" /d "%FRONTEND%"            cmd /k "npm run dev"

echo   chatbot   http://127.0.0.1:8010
echo   ERP       http://127.0.0.1:8000
echo   frontend  http://127.0.0.1:5173
echo(
echo   Open the frontend on 127.0.0.1, NOT localhost - the session cookie is
echo   SameSite=Lax, so a page on localhost calling the API on 127.0.0.1 is
echo   cross-site and the cookie is withheld. You would be unable to sign in
echo   or create accounts, with nothing explaining why.
echo(
goto :end

REM ===========================================================================
:find_base_python
REM  A python to BUILD the venv with. The launcher first (it is what a normal
REM  Windows install provides), then whatever is on PATH.
set "%~1="
for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "%~1=%%P"
if defined %~1 exit /b 0
for /f "delims=" %%P in ('python -c "import sys;print(sys.executable)" 2^>nul') do set "%~1=%%P"
exit /b 0

:port_busy
REM  Succeeds (errorlevel 0) when something is already listening on %1.
netstat -ano -p tcp | findstr /r /c:"LISTENING" | findstr /c:":%~1 " >nul 2>&1
exit /b %errorlevel%

:pip_failed
echo(
echo   ERROR: installing Python packages failed. The message above says why.
echo          A common cause on Windows is a package needing a compiler -
echo          chatbot_backend\requirements.no_prophet.txt drops the one that
echo          usually needs it.
goto :end

:no_python
echo(
echo   ERROR: no Python found. Install Python 3 and tick "Add to PATH",
echo          then run this again.
goto :end

:end
echo(
pause
endlocal
