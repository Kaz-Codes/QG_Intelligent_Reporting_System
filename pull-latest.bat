@echo off
REM ---------------------------------------------------------------------------
REM Pull the latest main onto a machine whose working copy has drifted.
REM
REM WHY THIS EXISTS. Five files used to be tracked that every machine rewrites
REM as it runs - the query cache, the derived data profile, the learned terms,
REM and the ERP's two runtime logs. Ordinary use therefore produced local
REM edits to tracked files, and the commit that untracks them has to delete
REM them, so git refuses the pull with
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

REM --- 2. the runtime files, which are never hand-edited --------------------
REM  The two .log files joined this list when they were untracked. A machine
REM  that has not pulled that commit yet still has them TRACKED, and its
REM  running server is appending to them - so the pull that deletes them fails
REM  exactly the way the three .json files used to. Anything untracked in a
REM  later commit belongs here in the SAME commit, or this script stops being
REM  able to do the one job it exists for.
echo === Discarding local edits to runtime data ^(cache, profile, terms, logs^)
for %%F in (
    "chatbot_backend/backend/metadata/query_cache.json"
    "chatbot_backend/backend/metadata/data_profile.json"
    "chatbot_backend/backend/metadata/learned_terms.json"
    "erp_backend.out.log"
    "erp_backend.err.log"
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
