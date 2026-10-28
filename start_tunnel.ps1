# start_tunnel.ps1 - Démarre le tunnel Cloudflare Zero Trust (token managé)
# URL permanente : https://dashboard.zentry.uk
# Redémarre automatiquement en cas d'erreur
#
# Token : variable d'environnement CLOUDFLARED_TUNNEL_TOKEN, sinon fichier
# data\tunnel.token (ignoré par git). Ne jamais committer le token.
#
# Version : cloudflared >= 2026.10.3 requis (certificats eMudhra compromis,
# cf. avis Cloudflare du 20/10/2026). Mise à jour auto au démarrage si besoin
# (nécessite une session administrateur pour écrire dans Program Files).

$cloudflared = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$minVersion  = [version]"2026.10.3"
$projectDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$dataDir     = Join-Path $projectDir "data"
$logFile     = Join-Path $dataDir "tunnel_log.txt"
$tokenFile   = Join-Path $dataDir "tunnel.token"

# Créer le dossier data si besoin
if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Path $dataDir | Out-Null }

# --- Token (hors du code) ---------------------------------------------------
$token = $env:CLOUDFLARED_TUNNEL_TOKEN
if (-not $token -and (Test-Path $tokenFile)) {
    $token = (Get-Content $tokenFile -Raw).Trim()
}
if (-not $token) {
    Write-Host "Token introuvable : définir CLOUDFLARED_TUNNEL_TOKEN ou créer $tokenFile" -ForegroundColor Red
    exit 1
}

# --- Version cloudflared ----------------------------------------------------
function Get-CloudflaredVersion {
    if (-not (Test-Path $cloudflared)) { return $null }
    $out = & $cloudflared --version 2>&1 | Out-String
    if ($out -match '(\d{4}\.\d+\.\d+)') { return [version]$Matches[1] }
    return $null
}

$current = Get-CloudflaredVersion
if (-not $current -or $current -lt $minVersion) {
    Write-Host "cloudflared $current < $minVersion : mise à jour..." -ForegroundColor Yellow
    try {
        $url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
        $tmp = Join-Path $env:TEMP "cloudflared-new.exe"
        Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
        New-Item -ItemType Directory -Path (Split-Path $cloudflared) -Force | Out-Null
        Move-Item -Path $tmp -Destination $cloudflared -Force
    } catch {
        Write-Host "Échec de la mise à jour : $_" -ForegroundColor Red
    }
    $current = Get-CloudflaredVersion
    if (-not $current -or $current -lt $minVersion) {
        Write-Host "cloudflared $current toujours < $minVersion. Relancer en administrateur ou mettre à jour manuellement." -ForegroundColor Red
        exit 1
    }
}
Write-Host "cloudflared $current OK" -ForegroundColor Green

Write-Host "Démarrage tunnel Cloudflare Zero Trust..." -ForegroundColor Cyan
Write-Host "URL permanente : https://dashboard.zentry.uk" -ForegroundColor Green

# Token passé par variable d'environnement (évite de l'exposer dans la ligne de commande)
$env:TUNNEL_TOKEN = $token

while ($true) {
    $pinfo = New-Object System.Diagnostics.ProcessStartInfo
    $pinfo.FileName = $cloudflared
    $pinfo.Arguments = "tunnel run"
    $pinfo.RedirectStandardError  = $true
    $pinfo.RedirectStandardOutput = $true
    $pinfo.UseShellExecute = $false
    $pinfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $pinfo
    $p.Start() | Out-Null

    # Lire la sortie en continu pour le log
    while (-not $p.HasExited) {
        $line = $p.StandardError.ReadLine()
        if ($line) {
            $line | Out-File -FilePath $logFile -Encoding utf8 -Append
        }
    }

    Write-Host "Tunnel arrêté, redémarrage dans 15s..." -ForegroundColor Yellow
    Start-Sleep -Seconds 15
}
