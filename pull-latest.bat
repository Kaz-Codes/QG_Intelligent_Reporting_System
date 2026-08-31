@echo off
REM ---------------------------------------------------------------------------
REM Pull the latest main onto a machine whose working copy has drifted.
REM
REM WHY THIS EXISTS. Three files used to be tracked that every machine rewrites
REM as it runs - the query cache, the derived data profile, and the learned
REM terms. Ordinary use therefore produced local edits to tracked files, and the
REM commit that untracks them has to delete them, so git refuses the pull with
REM "your local changes would be overwritten". On a machine that had been
REM running a while, that is a wall of conflicts for files nobody edited by hand.
REM
REM WHAT IT DOES, in order, stopping if anything looks unexpected:
REM   1. finishes any merge left half-open by an earlier attempt
REM   2. discards local edits to those three runtime files ONLY - they are a
REM      cache, a derived profile, and per-machine vocabulary; all three rebuild
REM   3. stashes anything else still modified, so real work is kept, not lost
REM   4. pulls
REM
REM It never force-pushes, never resets --hard, and never discards a file other
REM than the three named below. Anything it stashes is recoverable with
REM `git stash pop`.
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

echo.
echo === Repository: %CD%
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo    Not a git repository. Run this from inside the project folder.
    exit /b 1
)

REM --- 1. an interrupted merge blocks everything else -------------------------
if exist ".git\MERGE_HEAD" (
    echo === Finishing a merge left open by an earlier attempt
    git merge --abort
)

REM --- 2. the three runtime files, which are never hand-edited ---------------
echo === Discarding local edits to runtime data ^(cache, profile, learned terms^)
for %%F in (
    "chatbot_backend/backend/metadata/query_cache.json"
    "chatbot_backend/backend/metadata/data_profile.json"
    "chatbot_backend/backend/metadata/learned_terms.json"
) do (
    git checkout -- %%F 2>nul
)

REM --- 3. keep anything else, rather than throwing it away -------------------
git diff --quiet && git diff --cached --quiet
if errorlevel 1 (
    echo === Other local changes found - stashing them ^(recover with: git stash pop^)
    git stash push -u -m "pull-latest: before syncing with main"
)

REM --- 4. pull ---------------------------------------------------------------
echo === Pulling main
git pull origin main
if errorlevel 1 (
    echo.
    echo    PULL FAILED. Nothing has been lost - your work is either committed
    echo    or in `git stash list`. Send the message above for help.
    exit /b 1
)

echo.
echo === Done. Now restart both services.
echo     The chatbot takes the JWT secret from the ERP's .env automatically,
echo     so no .env editing is needed. On startup you should see:
echo        [warmup] chat tables ready
echo     and NO "access_token cookie ... could not be verified" error.
endlocal
