@echo off
:: Cree la tache planifiee pour le scan newsletter 13h
:: A executer en ADMINISTRATEUR (clic droit -> Executer en tant qu'administrateur)

set PYTHON="D:\Github - Claude\portfolio_manager\.venv\Scripts\python.exe"
set SCRIPT="D:\Github - Claude\portfolio_manager\newsletter_scan.py"

schtasks /create ^
  /tn "PortfolioNewsletterScan" ^
  /tr "%PYTHON% %SCRIPT%" ^
  /sc DAILY ^
  /st 13:00 ^
  /f ^
  /rl HIGHEST

if %errorlevel% == 0 (
    echo.
    echo [OK] Tache planifiee creee : "PortfolioNewsletterScan"
    echo      Execution chaque jour a 13h00
) else (
    echo.
    echo [ERREUR] Echec creation tache. Lance ce fichier en ADMINISTRATEUR.
)

pause
