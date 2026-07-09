# Wrapper du scan quotidien EN LOCAL sur Windows (équivalent de docker/run_daily.sh).
# Route les ordres vers IB Gateway paper (natif Windows) sur localhost:4002.
# À lancer en séance US. Automatisable via le Planificateur de tâches (voir
# docs/ibkr_local_windows.md).

$ErrorActionPreference = "Stop"

# Racine du repo = dossier parent de /tools
$RepoDir = Split-Path -Parent $PSScriptRoot
Set-Location $RepoDir

# ── Routage IBKR (paper) ─────────────────────────────────────────
$env:DATA_DIR        = Join-Path $RepoDir "data"
$env:IBKR_ENABLED    = "1"
$env:IBKR_HOST       = "127.0.0.1"
$env:IBKR_PORT       = "4002"          # 4002 = paper, 4001 = live (go-live)
$env:IBKR_ACCOUNT    = "DUP588572"
$env:IBKR_ORDER_TYPE = "MKT"           # MKT car lancé EN séance
$env:IBKR_SHADOW     = "1"             # simulation en parallèle pour comparer

$py = Join-Path $RepoDir ".venv\Scripts\python.exe"

Write-Host "===== $(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ') — run_daily (local) ====="

# Sync éventuelle avant de trader (ne bloque pas si offline)
git pull --rebase --autostash origin master
if (-not $?) { Write-Host "git pull échoué (on continue)" }

# Scan + trading
& $py daily_auto.py

# Persiste l'état (PTF + logs + logs de validation sim-vs-réel)
git add data/portfolio_state.json data/momentum_state.json `
        data/daily_log.txt data/ibkr_validation*.jsonl 2>$null
git diff --staged --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -m "auto(local): portfolio $(Get-Date -Format 'yyyy-MM-dd')"
    git push
    if (-not $?) { Write-Host "git push échoué (vérifier l'auth git)" }
} else {
    Write-Host "Aucun changement à committer."
}

Write-Host "===== fin run_daily ====="
