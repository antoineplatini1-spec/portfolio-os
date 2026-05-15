/**
 * newsletter_reader.gs
 * --------------------
 * Lit le dernier email de momentum@prismamedia.com dans Gmail,
 * extrait le corps en texte plein, et écrit un fichier JSON
 * dans Google Drive nommé "newsletter_cache.json".
 *
 * Le fichier est partagé publiquement en lecture (Anyone with link).
 * L'ID du fichier Drive est loggé dans la console pour récupération.
 *
 * Trigger recommandé : time-based, chaque jour à 13h (Europe/Paris).
 */

var SENDER        = "momentum@prismamedia.com";
var FILENAME      = "newsletter_cache.json";
var SEARCH_DAYS   = 2;   // chercher dans les N derniers jours

// ─────────────────────────────────────────────────────────────────────────────
// Point d'entrée principal — à lier au trigger temporel
// ─────────────────────────────────────────────────────────────────────────────
function fetchNewsletterAndSave() {
  try {
    var result = fetchLatestNewsletter();
    if (!result) {
      Logger.log("[newsletter_reader] Aucun email trouvé — pas de mise à jour du cache.");
      return;
    }

    var fileId = writeToGoogleDrive(result);
    Logger.log("[newsletter_reader] Fichier Drive mis à jour. ID : " + fileId);
    Logger.log("[newsletter_reader] URL directe : https://drive.google.com/uc?export=download&id=" + fileId);
    Logger.log("[newsletter_reader] Sujet : " + result.subject);
    Logger.log("[newsletter_reader] Date email : " + result.date);
  } catch (e) {
    Logger.log("[newsletter_reader] ERREUR : " + e.message);
    Logger.log(e.stack);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Recherche du dernier email du sender dans Gmail
// ─────────────────────────────────────────────────────────────────────────────
function fetchLatestNewsletter() {
  // Calculer la date de début de recherche (N derniers jours)
  var since = new Date();
  since.setDate(since.getDate() - SEARCH_DAYS);
  var sinceStr = Utilities.formatDate(since, "UTC", "yyyy/MM/dd");

  var query = "from:" + SENDER + " after:" + sinceStr;
  Logger.log("[newsletter_reader] Recherche Gmail : " + query);

  var threads = GmailApp.search(query, 0, 10);
  if (!threads || threads.length === 0) {
    return null;
  }

  // Trier pour obtenir le thread le plus récent en premier
  threads.sort(function(a, b) {
    return b.getLastMessageDate() - a.getLastMessageDate();
  });

  var latestThread = threads[0];
  var messages = latestThread.getMessages();
  if (!messages || messages.length === 0) {
    return null;
  }

  // Prendre le dernier message du thread
  var msg = messages[messages.length - 1];

  var subject  = msg.getSubject() || "";
  var dateObj  = msg.getDate();
  var dateStr  = Utilities.formatDate(dateObj, "Europe/Paris", "yyyy-MM-dd'T'HH:mm:ss");
  var bodyPlain= msg.getPlainBody() || msg.getBody() || "";

  // Si on n'a que le corps HTML, convertir en texte lisible (suppression des balises)
  if (!msg.getPlainBody() && bodyPlain) {
    bodyPlain = htmlToText(bodyPlain);
  }

  // Nettoyage minimal : supprimer les retours chariot Windows
  bodyPlain = bodyPlain.replace(/\r\n/g, "\n").replace(/\r/g, "\n");

  return {
    text   : bodyPlain,
    subject: subject,
    date   : dateStr
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Écriture dans Google Drive
// ─────────────────────────────────────────────────────────────────────────────
function writeToGoogleDrive(data) {
  var savedAt = Utilities.formatDate(new Date(), "Europe/Paris", "yyyy-MM-dd'T'HH:mm:ss");

  var payload = JSON.stringify({
    text    : data.text,
    subject : data.subject,
    date    : data.date,
    saved_at: savedAt
  }, null, 2);

  var blob = Utilities.newBlob(payload, "application/json", FILENAME);

  // Chercher si le fichier existe déjà (pour éviter les doublons)
  var files = DriveApp.getFilesByName(FILENAME);
  var file;

  if (files.hasNext()) {
    // Mettre à jour le fichier existant
    file = files.next();
    file.setContent(payload);
    Logger.log("[newsletter_reader] Fichier existant mis à jour : " + file.getId());
  } else {
    // Créer un nouveau fichier à la racine de My Drive
    file = DriveApp.createFile(blob);
    Logger.log("[newsletter_reader] Nouveau fichier créé : " + file.getId());
  }

  // Partager publiquement en lecture (Anyone with the link can view)
  file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);

  return file.getId();
}

// ─────────────────────────────────────────────────────────────────────────────
// Utilitaire : conversion HTML → texte brut (fallback si pas de plaintext)
// ─────────────────────────────────────────────────────────────────────────────
function htmlToText(html) {
  if (!html) return "";
  // Remplacer les balises de saut de ligne par des newlines
  var text = html
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/p>/gi, "\n\n")
    .replace(/<\/div>/gi, "\n")
    .replace(/<\/tr>/gi, "\n")
    .replace(/<\/td>/gi, " | ")
    .replace(/<\/th>/gi, " | ")
    .replace(/<[^>]+>/g, "");  // supprimer toutes les autres balises

  // Décoder les entités HTML courantes
  text = text
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&eacute;/g, "é")
    .replace(/&egrave;/g, "è")
    .replace(/&agrave;/g, "à")
    .replace(/&ugrave;/g, "ù")
    .replace(/&ccedil;/g, "ç")
    .replace(/&ocirc;/g, "ô")
    .replace(/&ecirc;/g, "ê")
    .replace(/&acirc;/g, "â")
    .replace(/&ucirc;/g, "û")
    .replace(/&iuml;/g, "ï")
    .replace(/&hellip;/g, "...")
    .replace(/&mdash;/g, "—")
    .replace(/&ndash;/g, "–")
    .replace(/&#8217;/g, "'")
    .replace(/&#8216;/g, "'")
    .replace(/&#8220;/g, '"')
    .replace(/&#8221;/g, '"');

  // Supprimer les lignes vides successives (max 2 sauts)
  text = text.replace(/\n{3,}/g, "\n\n");

  return text.trim();
}

// ─────────────────────────────────────────────────────────────────────────────
// Fonction utilitaire : créer le trigger manuellement depuis l'éditeur
// (à exécuter une seule fois pour installer le trigger)
// ─────────────────────────────────────────────────────────────────────────────
function createDailyTrigger() {
  // Supprimer les triggers existants du même projet pour éviter les doublons
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === "fetchNewsletterAndSave") {
      ScriptApp.deleteTrigger(triggers[i]);
      Logger.log("[newsletter_reader] Ancien trigger supprimé.");
    }
  }

  // Créer le trigger à 13h00 heure de Paris
  // Google Apps Script interprète l'heure du trigger selon le fuseau du projet
  // => régler le fuseau du projet sur "Europe/Paris" dans les paramètres du projet
  ScriptApp.newTrigger("fetchNewsletterAndSave")
    .timeBased()
    .everyDays(1)
    .atHour(13)
    .create();

  Logger.log("[newsletter_reader] Trigger créé : fetchNewsletterAndSave chaque jour à 13h.");
}
