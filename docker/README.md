# IBKR Paper Trading — Setup VPS

Passage du `PaperBroker` simulé au **compte IBKR paper réel** (frais + conditions
réelles) avant le go-live. Le code est prêt ; ce guide couvre la mise en place
sur le VPS (Phase 2).

## Architecture

```
VPS Linux (toujours allumé)
├── IB Gateway (Docker, image gnzsnz/ib-gateway) + IBC auto-login → port 4002 (paper)
└── daily_auto.py (cron 13h Paris) → IBKRBroker → localhost:4002
                                    └→ PaperBroker (shadow) → ibkr_validation.jsonl
```

Le bot et le Gateway tournent sur **le même host** : l'API IBKR n'est exposée qu'en
`127.0.0.1`, jamais sur Internet.

## Prérequis

1. **Compte IBKR paper** (gratuit) : créer sur ibkr.com, activer le paper trading,
   noter le user (`TWS_USERID`) et le mot de passe. Le compte paper commence par `DU`.
2. **VPS** : ~2 vCPU / 2–4 Go RAM (Hetzner CX22 ≈ 4€/mois convient). Docker installé.

## Étape 1 — Lancer le Gateway

```bash
git clone <repo> && cd portfolio_manager/docker
cp .env.example .env
nano .env          # remplir TWS_USERID / TWS_PASSWORD  (⚠️ toi seul, jamais dans le chat)
docker compose up -d
docker compose logs -f ib-gateway     # attendre "IBC: Login has completed"
```

En cas de blocage d'auth (2FA IBKR Mobile) : se connecter en VNC sur `127.0.0.1:5900`
via un tunnel SSH (`ssh -L 5900:localhost:5900 vps`) pour voir l'écran du Gateway.

## Étape 2 — Smoke test (aucun ordre passé)

```bash
cd ..                      # racine du projet
pip install -r requirements.txt
IBKR_ENABLED=1 python tools/ibkr_smoketest.py
```

Doit afficher : connexion OK, contrat AAPL qualifié, cash + positions du compte.

## Étape 3 — Activer le routage des ordres

Variables d'environnement du cron (voir `config.py` → `IBKR_CONFIG`) :

| Variable         | Valeur conseillée | Rôle                                             |
|------------------|-------------------|--------------------------------------------------|
| `IBKR_ENABLED`   | `1`               | Route les ordres vers IBKR                        |
| `IBKR_PORT`      | `4002`            | Paper (4001 = live)                               |
| `IBKR_ACCOUNT`   | `DUxxxxxx`        | Ton compte paper                                  |
| `IBKR_ORDER_TYPE`| `MOO`             | Market-On-Open (le cron tourne avant l'ouverture) |
| `IBKR_SHADOW`    | `1`               | Garde la simulation en parallèle pour comparer    |

> ⚠️ Le scan tourne à 13h Paris = **avant l'ouverture US (15h30 Paris)**. En `MKT`
> les ordres seraient rejetés/en attente hors séance. `MOO` (tif=OPG) les fait
> exécuter à l'ouverture officielle → fills réalistes.

## Étape 4 — Valider avant go-live

Laisser tourner quelques semaines en paper, puis :

```bash
python tools/validation_report.py     # slippage réel vs modèle, frais réels vs BROKER_CONFIG
python tools/reconcile.py             # état local vs positions IBKR (doit être aligné)
```

Quand le slippage réel ≈ modèle et la réconciliation est propre → prêt pour le live
(`TRADING_MODE=live`, `IBKR_PORT=4001`). **Un seul flip de config**, pas de code à changer.

## Sécurité

- `.env` et `ibc-settings/` sont git-ignorés — les identifiants ne quittent jamais le VPS.
- API bindée en `127.0.0.1` uniquement. Fermer le port VNC (5900) après le setup.
- Go-live = décision manuelle explicite (changer `TRADING_MODE` et le port).
