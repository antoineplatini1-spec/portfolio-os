# IBKR Paper en local sur Windows (PC, disque D:)

Setup pour faire tourner le bot contre un **compte IBKR paper réel** directement sur
ton PC Windows — **sans Docker ni VPS**. Idéal pour valider l'intégration maintenant.
Le VPS reste la cible pour le run quotidien fiable (voir `docker/README.md`).

> ⚠️ Ton PC doit être **allumé et IB Gateway connecté** pendant les heures de marché US
> (15h30–22h Paris) pour que les ordres et les stops s'exécutent. Pour du non-surveillé,
> bascule sur le VPS.

## Étape 1 — Installer IB Gateway (natif Windows)

1. Télécharger **IB Gateway** (pas TWS) — version *stable* :
   https://www.interactivebrokers.com/en/trading/ibgateway-stable.php
2. Lancer l'installeur. Tu peux choisir le dossier d'installation (ex. `D:\IBKR\Gateway`).
3. Au lancement : choisir **IB API** (pas FIX), mode **Paper Trading**, se connecter avec
   tes identifiants paper (compte `DUP588572`).
   → ⚠️ Toi seul saisis le mot de passe, jamais dans le chat.

## Étape 2 — Activer l'API dans le Gateway

Dans IB Gateway : **Configure → Settings → API → Settings** :

| Réglage | Valeur |
|---------|--------|
| Enable ActiveX and Socket Clients | ✅ coché |
| Socket port | **4002** (paper) |
| Read-Only API | ❌ décoché (on doit passer des ordres) |
| Allow connections from localhost only | ✅ (ou ajouter `127.0.0.1` aux Trusted IPs) |

Appliquer et laisser le Gateway ouvert.

## Étape 3 — Smoke test (aucun ordre passé)

Dans PowerShell, à la racine du projet :

```powershell
cd "D:\Github - Claude\portfolio_manager"
$env:IBKR_ENABLED = "1"
.venv\Scripts\python.exe tools\ibkr_smoketest.py
```

Attendu : connexion OK, contrat AAPL qualifié, cash + positions du compte paper.

## Étape 4 — Lancer un scan complet contre IBKR

`tools\run_daily.ps1` fixe les variables (port 4002, compte, MKT, shadow) puis lance
`daily_auto.py` et pousse l'état. À lancer **en séance US** (après 15h30 Paris) :

```powershell
cd "D:\Github - Claude\portfolio_manager"
.\tools\run_daily.ps1
```

## Étape 5 — Automatiser (Planificateur de tâches Windows)

Créer une tâche quotidienne lun–ven à ~16h30 (Paris), en séance US :

```powershell
$action  = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument '-NoProfile -ExecutionPolicy Bypass -File "D:\Github - Claude\portfolio_manager\tools\run_daily.ps1"'
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 16:30
Register-ScheduledTask -TaskName "PortfolioOS-Daily" -Action $action -Trigger $trigger -Description "Scan IBKR paper quotidien"
```

⚠️ La tâche ne tourne que si le PC est allumé à l'heure. IB Gateway doit aussi être
lancé (pour l'auto-login, installer **IBC for Windows** — étape optionnelle plus tard).

## Passage au live plus tard

Quand la validation est bonne (`tools\validation_report.py`), le go-live = changer le
Gateway en mode **Live** + `IBKR_PORT=4001`. Aucun code à modifier.
