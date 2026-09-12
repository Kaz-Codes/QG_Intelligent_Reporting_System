# ============================================================================
#  READ-ONLY SERVER SURVEY
#
#  Writes everything into ONE text file you paste back. It changes NOTHING:
#  no git checkout/pull, no alembic, no pip install, no service restart. Every
#  SQL statement is a SELECT.
#
#  RUN AS ADMINISTRATOR - `nssm dump` needs it (it reads HKLM). Everything
#  else works unprivileged; if you cannot get an admin prompt, run it anyway
#  and the NSSM section will say "access denied" while the rest still fills in.
#
#  USAGE (from the repo folder on the server):
#      powershell -ExecutionPolicy Bypass -File .\server-survey.ps1
#  Then paste the contents of  server-survey-<date>.txt  back.
# ============================================================================

$ErrorActionPreference = "Continue"
$out = Join-Path $PSScriptRoot ("server-survey-" + (Get-Date -Format "yyyyMMdd-HHmm") + ".txt")
$repo = $PSScriptRoot

function Section($name) {
    ("`n" + ("=" * 78) + "`n== $name`n" + ("=" * 78)) | Out-File -Append -Encoding utf8 $out
}
function Run($label, $block) {
    "`n--- $label ---" | Out-File -Append -Encoding utf8 $out
    try { & $block 2>&1 | Out-String | Out-File -Append -Encoding utf8 $out }
    catch { "ERROR: $_" | Out-File -Append -Encoding utf8 $out }
}

"SERVER SURVEY  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File -Encoding utf8 $out
"host=$env:COMPUTERNAME  user=$env:USERNAME  repo=$repo" | Out-File -Append -Encoding utf8 $out
$admin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
  ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
"running as administrator: $admin" | Out-File -Append -Encoding utf8 $out

# ---------------------------------------------------------------- A. GIT ---
Section "GIT (read-only)"
Push-Location $repo
Run "branch"        { git rev-parse --abbrev-ref HEAD }
Run "log -1"        { git log -1 --oneline }
Run "status"        { git status }
Run "stash list"    { git stash list }
Run "remote -v"     { git remote -v }
Run "last 10"       { git log -10 --oneline }
Run "untracked+modified (short)" { git status --short }
Pop-Location

# ------------------------------------------------------------ B. SERVICES ---
Section "NSSM SERVICES  (needs administrator)"
$svcNames = @()
Run "services whose name or path mentions the app" {
    Get-CimInstance Win32_Service |
      Where-Object { $_.PathName -match 'nssm|uvicorn|python|node|qg|erp|supply' } |
      Select-Object Name, State, StartMode, PathName | Format-List
}
try {
    $svcNames = (Get-CimInstance Win32_Service |
        Where-Object { $_.PathName -match 'nssm' } |
        Select-Object -ExpandProperty Name)
} catch { }
"`nNSSM-managed service names found: $($svcNames -join ', ')" |
    Out-File -Append -Encoding utf8 $out

foreach ($s in $svcNames) {
    Run "nssm dump $s" { nssm dump $s }
    Run "sc query $s"  { sc.exe query $s }
    foreach ($p in @("Application","AppParameters","AppDirectory",
                     "AppStdout","AppStderr","AppExit","Start")) {
        Run "nssm get $s $p" { nssm get $s $p }
    }
}

# ------------------------------------------------------------ C. FRONTEND ---
Section "HOW THE FRONTEND IS SERVED"
Run "is there a built dist/?" {
    $d = Join-Path $repo "React_Frontend-main\frontend\dist"
    if (Test-Path $d) {
        "dist EXISTS"
        Get-Item $d | Select-Object FullName, LastWriteTime | Format-List
        "file count: " + (Get-ChildItem $d -Recurse -File).Count
        Get-ChildItem $d -File | Select-Object Name, Length, LastWriteTime | Format-Table
    } else { "dist DOES NOT EXIST -> not a static build" }
}
Run "does the backend mount static files?" {
    Select-String -Path (Join-Path $repo "app\main.py") `
        -Pattern "StaticFiles|mount\(|FileResponse|dist" -SimpleMatch:$false
}
Run "vite config + package scripts" {
    Get-Content (Join-Path $repo "React_Frontend-main\frontend\package.json") |
        Select-String -Pattern '"scripts"' -Context 0,10
}
Run "anything LISTENING on 5173 / 8000 / 80" {
    # LISTENING only. An unfiltered netstat also matches OUTBOUND connections
    # to those ports on other machines, which say nothing about what this
    # machine serves - and one of them reading as a local dev server is how
    # the verdict below would confidently give the wrong answer.
    $lines = netstat -ano | Select-String "LISTENING"
    $hits = $lines | Select-String ":5173\s|:8000\s|:80\s"
    if ($hits) { $hits | Select-Object -First 20 }
    else { "nothing LISTENING on 5173, 8000 or 80" }
    "--- (all listeners, for context) ---"
    $lines | Select-Object -First 25
}
# ---------------------------------------------------------------------------
#  IIS - asked separately, because "is the frontend served by IIS" is one of
#  the two blanks DEPLOY.md still carries and the evidence above does not
#  answer it. Get-WebSite needs the WebAdministration module, which is only
#  present when the IIS management tools are installed, and it needs
#  administrator. Both failures are reported rather than silently skipped.
# ---------------------------------------------------------------------------
Run "IIS present?" {
    $svc = Get-Service W3SVC -ErrorAction SilentlyContinue
    if ($null -eq $svc) { "W3SVC (IIS) service NOT INSTALLED" }
    else {
        "W3SVC status: " + $svc.Status
        if (Get-Module -ListAvailable -Name WebAdministration) {
            Import-Module WebAdministration -ErrorAction SilentlyContinue
            try {
                Get-WebSite | Select-Object Name, State, PhysicalPath |
                    Format-Table -AutoSize
                "--- bindings ---"
                Get-WebBinding | Select-Object protocol, bindingInformation |
                    Format-Table -AutoSize
            } catch { "Get-WebSite failed (needs administrator): $_" }
        } else { "WebAdministration module not available - cannot list sites" }
    }
}

# ---------------------------------------------------------------------------
#  THE VERDICT.
#
#  Everything above this point is evidence; DEPLOY.md step 6 was leaving the
#  reader to assemble it themselves, on deploy day, on a machine they may not
#  know. This block assembles it and commits to an answer WHERE THE EVIDENCE
#  SUPPORTS ONE - and says "AMBIGUOUS" where it does not, rather than guessing.
#  A wrong confident answer here means overwriting or failing to overwrite the
#  files the users actually load.
# ---------------------------------------------------------------------------
Run "VERDICT: how is the frontend served?" {
    $distPath = Join-Path $repo "React_Frontend-main\frontend\dist"
    $distExists = Test-Path $distPath

    $mounts = $false
    $mainPy = Join-Path $repo "app\main.py"
    if (Test-Path $mainPy) {
        $hit = Select-String -Path $mainPy -Pattern "StaticFiles" -ErrorAction SilentlyContinue
        if ($hit) { $mounts = $true }
    }

    # LISTENING only - see the note in the evidence block above. An outbound
    # connection to :5173 on another host is not this machine serving Vite.
    $listening5173 = $false
    $net = netstat -ano 2>$null | Select-String "LISTENING" | Select-String ":5173\s"
    if ($net) { $listening5173 = $true }

    $listening8000 = $false
    $net8 = netstat -ano 2>$null | Select-String "LISTENING" | Select-String ":8000\s"
    if ($net8) { $listening8000 = $true }

    $iis = $false
    $iisSvc = Get-Service W3SVC -ErrorAction SilentlyContinue
    if ($null -ne $iisSvc -and $iisSvc.Status -eq "Running") { $iis = $true }

    $iisPointsAtRepo = $false
    $iisPaths = @()
    if ($iis -and (Get-Module -ListAvailable -Name WebAdministration)) {
        Import-Module WebAdministration -ErrorAction SilentlyContinue
        try {
            foreach ($site in (Get-WebSite)) {
                $pp = $site.PhysicalPath
                $iisPaths += ($site.Name + " -> " + $pp)
                if ($pp -and ($pp -replace '/','\') -like ("*" + ($repo -replace '/','\') + "*")) {
                    $iisPointsAtRepo = $true
                }
            }
        } catch { $iisPaths += "could not enumerate sites (needs administrator)" }
    }

    "evidence:"
    "  dist/ exists ................ $distExists"
    "  app/main.py mounts static ... $mounts"
    "  LISTENING on :5173 (vite dev) $listening5173"
    "  LISTENING on :8000 (ERP api) . $listening8000"
    "  IIS running ................. $iis"
    if ($iisPaths.Count -gt 0) { foreach ($x in $iisPaths) { "  IIS site .................... $x" } }
    if ($iisPointsAtRepo) { "  an IIS site points INSIDE the repo folder" }

    # dist/ freshness against the last commit - a dist older than the newest
    # commit means the running frontend is NOT built from the deployed code.
    if ($distExists) {
        $idx = Join-Path $distPath "index.html"
        if (Test-Path $idx) {
            $distTime = (Get-Item $idx).LastWriteTime
            "  dist/index.html built ....... $distTime"
            Push-Location $repo
            $commitEpoch = (git log -1 --format=%ct 2>$null)
            Pop-Location
            if ($commitEpoch) {
                $commitTime = [DateTimeOffset]::FromUnixTimeSeconds([int64]$commitEpoch).LocalDateTime
                "  last commit ................. $commitTime"
                if ($distTime -lt $commitTime) {
                    "  >> dist/ is OLDER than the last commit - it was not rebuilt from this code"
                } else {
                    "  >> dist/ is newer than the last commit"
                }
            }
        } else { "  dist/ exists but has no index.html" }
    }

    ""
    "VERDICT:"
    if ($iisPointsAtRepo -and $distExists) {
        "  IIS serves the built dist/ from inside the repo folder."
        "  -> DEPLOY.md step 6: `npm run build` in place is enough; no copy needed."
    } elseif ($iis -and $distExists) {
        "  IIS is running but no site was found pointing at this repo."
        "  -> AMBIGUOUS. dist/ may be COPIED somewhere IIS serves. Check the"
        "     IIS site paths listed above against where dist/ actually is"
        "     before overwriting anything."
    } elseif ($mounts -and $distExists) {
        "  The ERP service itself mounts StaticFiles and dist/ exists."
        "  -> DEPLOY.md step 6: `npm run build` in place, then restart the ERP"
        "     service (step 8) for it to pick the new files up."
    } elseif ($listening5173) {
        "  Something is listening on 5173, which is Vite's DEV server port."
        "  -> The frontend is being served by `npm run dev`, NOT from a build."
        "     That is not a deployment setup. Flag it before deploying."
    } elseif (-not $distExists -and -not $mounts -and -not $iis) {
        "  No dist/, no StaticFiles mount, no IIS, nothing on 5173."
        "  -> AMBIGUOUS, and it means the frontend is served from somewhere"
        "     this script cannot see (another machine, another web server, or"
        "     a reverse proxy). Do not guess - find out before step 6."
    } else {
        "  AMBIGUOUS - the evidence above does not fit a single pattern."
        "  -> Read the evidence lines and decide deliberately. Do not assume."
    }
}

Run "node/python processes" {
    Get-Process node, python, pythonw -ErrorAction SilentlyContinue |
        Select-Object Id, ProcessName, Path | Format-Table -AutoSize
}

# ----------------------------------------------------------------- D. ENV ---
Section "ENV (password redacted)"
Run ".env, redacted" {
    $envFile = Join-Path $repo ".env"
    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            if ($_ -match '^\s*(DB_PASSWORD|JWT_SECRET_KEY|ADMIN_PASSWORD)\s*=') {
                ($_ -replace '=.*$', '=<redacted>')
            } else { $_ }
        }
    } else { ".env NOT FOUND at $envFile" }
}
Run "chatbot .env, redacted" {
    $c = Join-Path $repo "chatbot_backend\.env"
    if (Test-Path $c) {
        Get-Content $c | ForEach-Object {
            if ($_ -match '(?i)(password|secret|key|token)\s*=') {
                ($_ -replace '=.*$', '=<redacted>')
            } else { $_ }
        }
    } else { "chatbot_backend\.env NOT FOUND" }
}

# ----------------------------------------------------------------- E. SQL ---
Section "DATABASE (SELECT only)"

# Read connection details out of .env rather than hardcoding them.
$envMap = @{}
Get-Content (Join-Path $repo ".env") -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)$') { $envMap[$Matches[1]] = $Matches[2].Trim() }
}
$dbName = $envMap["DB_NAME"]; $dbHost = $envMap["DB_HOST"]
$dbUser = $envMap["DB_USER"]; $dbPort = $envMap["DB_PORT"]
"DB_NAME=$dbName  DB_HOST=$dbHost  DB_PORT=$dbPort  DB_USER=$dbUser" |
    Out-File -Append -Encoding utf8 $out
$env:PGPASSWORD = $envMap["DB_PASSWORD"]

$psql = (Get-Command psql -ErrorAction SilentlyContinue).Source
if (-not $psql) {
    $psql = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\psql.exe" -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty FullName
}
"psql: $psql" | Out-File -Append -Encoding utf8 $out

function Sql($label, $q) {
    "`n--- SQL: $label ---" | Out-File -Append -Encoding utf8 $out
    if (-not $psql) { "psql not found" | Out-File -Append -Encoding utf8 $out; return }
    & $psql -U $dbUser -h $dbHost -p $dbPort -d $dbName -X -c $q 2>&1 |
        Out-String | Out-File -Append -Encoding utf8 $out
}

Sql "alembic_version" @"
SELECT COALESCE((SELECT string_agg(version_num, ', ') FROM alembic_version),
                '(table exists, NO ROW)') AS revision
 WHERE EXISTS (SELECT 1 FROM information_schema.tables
                WHERE table_name='alembic_version');
"@

Sql "does alembic_version exist at all" @"
SELECT count(*) AS alembic_version_table_present
  FROM information_schema.tables WHERE table_name='alembic_version';
"@

Sql "row counts" @"
SELECT 'consignments live' k, count(*)::text v FROM consignments WHERE is_deleted=false
UNION ALL SELECT 'consignments all', count(*)::text FROM consignments
UNION ALL SELECT 'consignment_items live', count(*)::text FROM consignment_items WHERE is_deleted=false
UNION ALL SELECT 'consignment_items all', count(*)::text FROM consignment_items
UNION ALL SELECT 'payments', count(*)::text FROM payments
UNION ALL SELECT 'logistics orders', count(*)::text FROM logistics_consignments WHERE is_deleted=false
UNION ALL SELECT 'trucking jobs', count(*)::text FROM trucking_consignments WHERE is_deleted=false;
"@

# ---------------------------------------------------------------------------
#  ACCOUNTS.
#
#  Nobody has looked at production's `users` table, and on 9 September a
#  rebuild of the DEV database took it from 13 accounts to 1 - every named
#  login replaced by a freshly seeded `admin`. That is the first number worth
#  knowing BEFORE a deploy, not after, because nothing in any workbook puts
#  those rows back and only a backup can.
#
#  THE PASSWORD COLUMN IS DELIBERATELY NOT SELECTED. `users.password` is
#  PLAIN TEXT (CLAUDE.md, "accounts"), and the whole point of this file is
#  that it gets pasted into a chat window. Usernames and the admin flag are
#  what a deploy needs; the passwords are not, and a survey that leaks every
#  account's credentials is a worse problem than the one it was solving.
# ---------------------------------------------------------------------------
Sql "user accounts (NO passwords - that column is plain text and is not read)" @"
SELECT count(*) AS total,
       count(*) FILTER (WHERE is_admin)          AS admins,
       count(*) FILTER (WHERE is_active)         AS active,
       min(created_at)::date                     AS earliest_account,
       max(created_at)::date                     AS newest_account
  FROM users;
"@

Sql "usernames (again: no password column)" @"
SELECT id, username, is_admin, is_active, created_at::date AS created
  FROM users ORDER BY id;
"@

Sql "batching tables present? (EXPECTED: 0 0 0)" @"
SELECT table_name FROM information_schema.tables
 WHERE table_name IN ('consignment_batch_groups','consignment_order_items',
                      'enum_normalisation_audit','payment_addenda')
 ORDER BY 1;
"@

Sql "out-of-enum: mode_of_shipment" @"
SELECT mode_of_shipment AS stored, count(*) AS n
  FROM consignments
 WHERE mode_of_shipment IS NOT NULL
   AND mode_of_shipment NOT IN ('Sea freight FCL','Sea freight LCL','Air freight','Land/courier')
 GROUP BY 1 ORDER BY 2 DESC;
"@

Sql "out-of-enum: payment_instrument" @"
SELECT payment_instrument AS stored, count(*) AS n
  FROM consignments
 WHERE payment_instrument IS NOT NULL
   AND payment_instrument NOT IN ('LC','Adv','DP','CAD')
 GROUP BY 1 ORDER BY 2 DESC;
"@

Sql "out-of-enum: unit_of_measurement" @"
SELECT unit_of_measurement AS stored, count(*) AS n
  FROM consignment_items
 WHERE unit_of_measurement IS NOT NULL
   AND unit_of_measurement NOT IN ('Pcs','Set','Pair','Roll','Box','Carton','Drum',
        'Pallet','Kg','Gram','Ton','Lb','Metre','Centimetre','Foot','Inch',
        'Sq. metre','Cu. metre','Litre')
 GROUP BY 1 ORDER BY 2 DESC;
"@

Sql "out-of-enum: totals, and how many consignments are affected" @"
SELECT count(*) AS consignments_that_cannot_be_saved
  FROM consignments c
 WHERE c.is_deleted=false AND (
       (c.mode_of_shipment IS NOT NULL AND c.mode_of_shipment NOT IN
          ('Sea freight FCL','Sea freight LCL','Air freight','Land/courier'))
    OR (c.payment_instrument IS NOT NULL AND c.payment_instrument NOT IN
          ('LC','Adv','DP','CAD'))
    OR EXISTS (SELECT 1 FROM consignment_items i
                WHERE i.consignment_id=c.id AND i.is_deleted=false
                  AND i.unit_of_measurement IS NOT NULL
                  AND i.unit_of_measurement NOT IN ('Pcs','Set','Pair','Roll','Box',
                      'Carton','Drum','Pallet','Kg','Gram','Ton','Lb','Metre',
                      'Centimetre','Foot','Inch','Sq. metre','Cu. metre','Litre')));
"@

# --- the two rows the migration's own assumptions rest on --------------------
Sql "SS4.3 COALESCE: lines with NO quantity (the rows ordered_quantity=0 covers)" @"
SELECT i.id AS line_id, i.consignment_id, c.is_deleted AS consignment_deleted,
       i.item_code, i.item_name, i.quantity
  FROM consignment_items i JOIN consignments c ON c.id=i.consignment_id
 WHERE i.quantity IS NULL
 ORDER BY i.id;
"@

Sql "SS4.9 zero-count: DRAFTS already at Arrived at Works (EXPECTED: 0)" @"
SELECT count(*) AS drafts_at_arrived_at_works
  FROM consignments
 WHERE current_status='Arrived at Works' AND record_state='draft';
"@

Sql "SS4.9 support: the lock/status cross-tab" @"
SELECT current_status, record_state, is_locked, is_deleted, count(*)
  FROM consignments
 GROUP BY 1,2,3,4 ORDER BY 1,2,3,4;
"@

Sql "semantic views that depend on the moving columns" @"
SELECT table_name FROM information_schema.views
 WHERE table_schema='public' AND view_definition ILIKE '%consignment%'
 ORDER BY 1;
"@

Sql "database size + name" @"
SELECT current_database() AS db, pg_size_pretty(pg_database_size(current_database())) AS size;
"@

# -------------------------------------------------------------- F. PYTHON ---
Section "PYTHON PACKAGES - diff against requirements.txt ONLY"
Run "pip freeze vs requirements.txt (differences only)" {
    $py = Join-Path $repo "venv\Scripts\python.exe"
    if (-not (Test-Path $py)) { $py = "python" }
    $frozen = & $py -m pip freeze 2>$null
    $req    = Get-Content (Join-Path $repo "requirements.txt") -ErrorAction SilentlyContinue

    $fmap = @{}; foreach ($l in $frozen) { if ($l -match '^([^=]+)==(.+)$') { $fmap[$Matches[1].ToLower().Trim()] = $Matches[2].Trim() } }
    $rmap = @{}; foreach ($l in $req)    { if ($l -match '^([^=<>~!#\s]+)\s*==\s*(.+)$') { $rmap[$Matches[1].ToLower().Trim()] = $Matches[2].Trim() }
                                            elseif ($l -match '^([^=<>~!#\s]+)\s*$')      { $rmap[$Matches[1].ToLower().Trim()] = '(unpinned)' } }

    "requirements.txt entries: $($rmap.Count)   installed: $($fmap.Count)"
    ""
    "MISSING (in requirements.txt, not installed):"
    foreach ($k in ($rmap.Keys | Sort-Object)) { if (-not $fmap.ContainsKey($k)) { "  $k  (want $($rmap[$k]))" } }
    ""
    "VERSION MISMATCH:"
    foreach ($k in ($rmap.Keys | Sort-Object)) {
        if ($fmap.ContainsKey($k) -and $rmap[$k] -ne '(unpinned)' -and $fmap[$k] -ne $rmap[$k]) {
            "  $k  want $($rmap[$k])  installed $($fmap[$k])"
        }
    }
    ""
    "EXTRA (installed, not in requirements.txt) - first 40:"
    $extra = @()
    foreach ($k in ($fmap.Keys | Sort-Object)) {
        if (-not $rmap.ContainsKey($k)) {
            $v = $fmap[$k]
            $extra += ("  " + $k + "==" + $v)
        }
    }
    $extra | Select-Object -First 40
    "  ... total extra: $($extra.Count)"
}
Run "python version" {
    $py = Join-Path $repo "venv\Scripts\python.exe"
    if (-not (Test-Path $py)) { $py = "python" }
    & $py --version
}

Section "DONE"
"Report written to: $out" | Out-File -Append -Encoding utf8 $out
Write-Host ""
Write-Host "Done. Paste this file back:" -ForegroundColor Green
Write-Host "  $out" -ForegroundColor Green
Write-Host ""
Write-Host "It made no changes: no checkout, no pull, no alembic, no pip install," -ForegroundColor Yellow
Write-Host "no service restart, and every SQL statement was a SELECT." -ForegroundColor Yellow
