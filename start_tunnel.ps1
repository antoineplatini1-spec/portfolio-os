# start_tunnel.ps1 - Démarre le tunnel Cloudflare Quick Tunnel
# Lance cloudflared et sauvegarde l'URL publique dans data/tunnel_url.txt
# Redémarre automatiquement en cas d'erreur

$cloudflared = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$dataDir = Join-Path $projectDir "data"
$urlFile = Join-Path $dataDir "tunnel_url.txt"
$logFile = Join-Path $dataDir "tunnel_log.txt"

# Créer le dossier data si besoin
if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Path $dataDir | Out-Null }

Write-Host "Démarrage Quick Tunnel Cloudflare..." -ForegroundColor Cyan
Write-Host "URL publiée dans : $urlFile" -ForegroundColor Gray

while ($true) {
    # Effacer l'ancienne URL
    "en attente..." | Out-File -FilePath $urlFile -Encoding utf8

    # Lancer cloudflared et lire son stderr en temps réel
    $pinfo = New-Object System.Diagnostics.ProcessStartInfo
    $pinfo.FileName = $cloudflared
    $pinfo.Arguments = "tunnel --url http://localhost:8501"
    $pinfo.RedirectStandardError = $true
    $pinfo.RedirectStandardOutput = $true
    $pinfo.UseShellExecute = $false
    $pinfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $pinfo
    $p.Start() | Out-Null

    $urlFound = $false
    $startTime = Get-Date

    while (-not $p.HasExited) {
        $line = $p.StandardError.ReadLine()
        if ($line) {
            # Log
            $line | Out-File -FilePath $logFile -Encoding utf8 -Append

            # Chercher l'URL trycloudflare.com
            if ($line -match "https://[a-z0-9\-]+\.trycloudflare\.com") {
                $url = $Matches[0]
                $url | Out-File -FilePath $urlFile -Encoding utf8 -NoNewline
                Write-Host "URL du tunnel : $url" -ForegroundColor Green
                $urlFound = $true
            }
        }

        # Timeout si pas d'URL en 60s
        if (-not $urlFound -and ((Get-Date) - $startTime).TotalSeconds -gt 60) {
            Write-Host "Timeout - pas d'URL trouvee, redémarrage..." -ForegroundColor Yellow
            $p.Kill()
            break
        }
    }

    Write-Host "Tunnel arreté, redémarrage dans 10s..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10
}
