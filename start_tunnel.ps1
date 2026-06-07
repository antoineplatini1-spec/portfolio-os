# start_tunnel.ps1 - Démarre le tunnel Cloudflare Zero Trust (token managé)
# URL permanente : https://dashboard.zentry.uk
# Redémarre automatiquement en cas d'erreur

$cloudflared = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$token       = "eyJhIjoiZmIxZWI1YzgzYzhkZmJjMzNhZjk2MjliZWVlMjRmZjciLCJ0IjoiNGI0MWE1Y2QtOWRlZi00ZjE2LWEzMjctMmZiNTQ3ODNkZTBkIiwicyI6IlpEQTJZVGszWmpjdE5EYzFNUzAwTkRBMUxUazFPR1V0TmpSaU5URTRZak0zWW1ZeCJ9"
$projectDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$dataDir     = Join-Path $projectDir "data"
$logFile     = Join-Path $dataDir "tunnel_log.txt"

# Créer le dossier data si besoin
if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Path $dataDir | Out-Null }

Write-Host "Démarrage tunnel Cloudflare Zero Trust..." -ForegroundColor Cyan
Write-Host "URL permanente : https://dashboard.zentry.uk" -ForegroundColor Green

while ($true) {
    $pinfo = New-Object System.Diagnostics.ProcessStartInfo
    $pinfo.FileName = $cloudflared
    $pinfo.Arguments = "tunnel run --token $token"
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
