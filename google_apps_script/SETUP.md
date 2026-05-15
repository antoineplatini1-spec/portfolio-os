# Setup — Google Apps Script : Newsletter Momentum → Google Drive

Ce guide configure un script cloud qui lit automatiquement la newsletter
Momentum (momentum@prismamedia.com) chaque jour à 13h et publie le contenu
dans un fichier Google Drive accessible par le script Python local.

---

## Étape 1 — Ouvrir Google Apps Script

1. Ouvre un navigateur et connecte-toi avec le compte **antoine.platini1@gmail.com**
   (le même compte Gmail qui reçoit la newsletter).
2. Va sur : **https://script.google.com**
3. Clique sur **"Nouveau projet"** (bouton en haut à gauche).

---

## Étape 2 — Coller le script

1. Dans l'éditeur, supprime le contenu par défaut (`function myFunction() {}`).
2. Ouvre le fichier `newsletter_reader.gs` (dans ce dossier) et copie **tout** son contenu.
3. Colle-le dans l'éditeur Apps Script.
4. Clique sur l'icône **Enregistrer** (disquette) ou `Ctrl+S`.
5. Donne un nom au projet, par exemple : **Newsletter Momentum Cache**

---

## Étape 3 — Configurer le fuseau horaire du projet

Le trigger à 13h doit respecter l'heure de Paris (UTC+2 en été, UTC+1 en hiver).

1. Dans l'éditeur, clique sur **Paramètres du projet** (icône engrenage ⚙ dans la barre de gauche).
2. Sous **"Fuseau horaire"**, sélectionne : **(GMT+01:00) Europe/Paris**
3. Clique **Enregistrer**.

---

## Étape 4 — Installer le trigger temporel

### Option A — Automatique via le script (recommandé)

1. Dans l'éditeur, sélectionne la fonction **`createDailyTrigger`** dans le menu déroulant
   des fonctions (en haut, à droite du bouton ▶ Exécuter).
2. Clique sur **▶ Exécuter**.
3. Une boîte d'autorisation apparaît — clique **Vérifier les autorisations**, puis
   **Autoriser** (le script a besoin d'accéder à Gmail et Drive).
4. Vérifie dans la console d'exécution que le message suivant apparaît :
   `[newsletter_reader] Trigger créé : fetchNewsletterAndSave chaque jour à 13h.`

### Option B — Manuelle via l'interface

1. Clique sur **Déclencheurs** (icône horloge ⏰ dans la barre de gauche).
2. Clique **+ Ajouter un déclencheur** (coin inférieur droit).
3. Configure :
   - **Fonction à exécuter** : `fetchNewsletterAndSave`
   - **Source de l'événement** : Horaire
   - **Type de déclencheur** : Journalier
   - **Heure** : 13h00 – 14h00
4. Clique **Enregistrer** et autorise les permissions.

---

## Étape 5 — Tester le script manuellement

1. Dans le menu déroulant des fonctions, sélectionne **`fetchNewsletterAndSave`**.
2. Clique **▶ Exécuter**.
3. Consulte le **Journal d'exécution** (en bas de l'éditeur).
4. Tu dois voir :
   ```
   [newsletter_reader] Fichier Drive mis à jour. ID : 1AbCdEfGhIjKlMnOpQrStUvWxYz
   [newsletter_reader] URL directe : https://drive.google.com/uc?export=download&id=1AbCdEfGhIjKlMnOpQrStUvWxYz
   [newsletter_reader] Sujet : Momentum Capital — [titre de la newsletter]
   [newsletter_reader] Date email : 2026-05-14T10:32:00
   ```
5. **Copie l'ID du fichier** (la partie après `id=` dans l'URL).

> Si aucun email n'est trouvé, c'est normal si la newsletter n'est pas encore
> arrivée ce jour-là. Relance le test un jour où la newsletter a été reçue.

---

## Étape 6 — Configurer le script Python local

1. Ouvre le fichier `data/email_config.json` du projet Python.
2. Remplace `GDRIVE_FILE_ID` par l'ID récupéré à l'étape précédente :

   ```json
   {
     "gdrive_cache_url": "https://drive.google.com/uc?export=download&id=1AbCdEfGhIjKlMnOpQrStUvWxYz"
   }
   ```

3. Sauvegarde le fichier.

---

## Étape 7 — Vérifier le bon fonctionnement

Lance le script Python pour vérifier que le fallback Google Drive fonctionne :

```python
from signals.newsletter_agent import NewsletterAgent
signal = NewsletterAgent().fetch_and_parse()
print(signal.source)   # doit afficher "gdrive" si IMAP n'est pas configuré
print(signal.date)
print(signal.cac40_sentiment)
```

---

## Récapitulatif de l'architecture

```
[Gmail : momentum@prismamedia.com]
          │  (arrive ~10h30 chaque jour ouvré)
          │
          ▼
[Google Apps Script — trigger 13h Paris]
  ├── GmailApp.search("from:momentum@prismamedia.com")
  ├── Extrait le texte plein
  └── Écrit newsletter_cache.json sur Google Drive (public en lecture)
          │
          ▼
[Script Python local — NewsletterAgent.fetch_and_parse()]
  1. IMAP Gmail        (si APP_PASSWORD_READER configuré)
  2. Google Drive JSON (si gdrive_cache_url configuré)  ← nouveau fallback
  3. Cache local       (data/newsletter_cache.json)
```

---

## Dépannage

| Problème | Solution |
|---|---|
| "Aucun email trouvé" dans les logs | La newsletter n'est pas arrivée dans les 2 derniers jours, ou le compte Google est différent du compte de réception |
| Erreur d'autorisation Gmail | Relancer `createDailyTrigger` et ré-autoriser les scopes Gmail + Drive |
| L'URL Drive retourne une erreur 403 | Vérifier que le fichier est bien partagé "Anyone with the link" — re-exécuter le script |
| Python retourne `source="cache"` au lieu de `"gdrive"` | Vérifier que `gdrive_cache_url` ne contient plus `GDRIVE_FILE_ID` et que l'URL est correcte |
| Le trigger ne se déclenche pas à 13h | Vérifier le fuseau horaire du projet (Étape 3) — le fuseau doit être Europe/Paris |
