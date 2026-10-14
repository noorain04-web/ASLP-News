/**
 * ASLP-News email subscription + daily broadcast service.
 *
 * Deploy this as a web app owned by noorain.aslp@gmail.com.
 * Script Properties required:
 *   SPREADSHEET_ID       Google Sheet ID for subscriber storage
 *   EMAIL_WEBHOOK_SECRET Long random secret matching GitHub Actions secret
 *
 * The script is designed to be bound to the subscriber Google Sheet.
 */
const SHEET_NAME = "Subscribers";
const SENDER_NAME = "ASLP-News | Speech, Language & Hearing Intelligence";
const SUBJECT_PREFIX = "ASLP-News Daily Professional Intelligence";

function doGet(e) {
  const action = (e && e.parameter && e.parameter.action) || "";
  const token = (e && e.parameter && e.parameter.token) || "";

  if (action === "verify") return htmlPage_(verifySubscription_(token));
  if (action === "unsubscribe") return htmlPage_(unsubscribe_(token));

  return HtmlService.createHtmlOutputFromFile("Index")
    .setTitle("Subscribe to ASLP-News")
    .addMetaTag("viewport", "width=device-width, initial-scale=1");
}

function doPost(e) {
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const payload = JSON.parse((e && e.postData && e.postData.contents) || "{}");
    const expectedSecret = PropertiesService.getScriptProperties().getProperty("EMAIL_WEBHOOK_SECRET");
    if (!expectedSecret || !payload.secret ||
        !constantTimeEquals_(String(payload.secret), String(expectedSecret))) {
      return json_(401, { ok: false, error: "Unauthorized" });
    }

    const alertDate = String(payload.alertDate || "").trim();
    const body = String(payload.body || "").trim();
    if (!/^\d{4}-\d{2}-\d{2}$/.test(alertDate) || !body) {
      return json_(400, { ok: false, error: "Missing/invalid alertDate or body" });
    }
    if (body.length > 90000) return json_(413, { ok: false, error: "Alert exceeds size limit" });

    const props = PropertiesService.getScriptProperties();
    const lastSentDate = props.getProperty("LAST_ALERT_DATE");
    if (lastSentDate === alertDate) {
      return json_(200, { ok: true, skipped: true, message: "Alert already distributed for this date" });
    }

    const sheet = subscriberSheet_();
    const lastRow = sheet.getLastRow();
    if (lastRow < 2) return json_(200, { ok: true, sent: 0, message: "No subscribers yet" });

    const rows = sheet.getRange(2, 1, lastRow - 1, 7).getValues();
    const recipients = [];
    const failed = [];
    rows.forEach((row, idx) => {
      const email = String(row[0] || "").trim().toLowerCase();
      const status = String(row[1] || "").trim();
      if (status === "confirmed" && email && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        recipients.push({ email, sheetRow: idx + 2, unsubscribeToken: String(row[4] || "") });
      }
    });

    if (!recipients.length) return json_(200, { ok: true, sent: 0, message: "No confirmed subscribers" });

    const quota = MailApp.getRemainingDailyQuota();
    if (quota < recipients.length) {
      return json_(429, { ok: false, error: "Daily email quota is insufficient", recipients: recipients.length, quota });
    }

    let sent = 0;
    recipients.forEach((recipient) => {
      const unsubscribeUrl = webAppUrl_() + "?action=unsubscribe&token=" + encodeURIComponent(recipient.unsubscribeToken);
      const emailBody = body +
        "\n\n—\nYou are receiving this because you subscribed to ASLP-News.\n" +
        "Unsubscribe: " + unsubscribeUrl + "\n" +
        "Information is provided for professional awareness; verify details with the official source.";
      try {
        MailApp.sendEmail({
          to: recipient.email,
          subject: SUBJECT_PREFIX + " — " + alertDate,
          body: emailBody,
          name: SENDER_NAME
        });
        sheet.getRange(recipient.sheetRow, 6).setValue(new Date()); // lastSentAt
        sent++;
      } catch (sendError) {
        console.error("Email failed for row " + recipient.sheetRow + ": " + sendError);
        failed.push(recipient.email);
      }
    });

    if (failed.length === 0) props.setProperty("LAST_ALERT_DATE", alertDate);
    return json_(failed.length ? 207 : 200, {
      ok: failed.length === 0,
      sent,
      failed: failed.length,
      alertDate,
      message: failed.length ? "Some messages failed; inspect Apps Script logs before retrying." : "All messages sent"
    });
  } catch (err) {
    console.error(err && err.stack ? err.stack : err);
    return json_(500, { ok: false, error: "Internal error while processing request" });
  } finally {
    lock.releaseLock();
  }
}

/** Called from the public sign-up page via google.script.run. */
function subscribe(emailInput) {
  const email = String(emailInput || "").trim().toLowerCase();
  if (email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return { ok: false, message: "Enter a valid email address." };
  }

  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const sheet = subscriberSheet_();
    const lastRow = sheet.getLastRow();
    if (lastRow >= 2) {
      const emails = sheet.getRange(2, 1, lastRow - 1, 1).getDisplayValues().flat().map(v => String(v).trim().toLowerCase());
      const found = emails.indexOf(email);
      if (found !== -1) {
        const rowNumber = found + 2;
        const status = String(sheet.getRange(rowNumber, 2).getValue());
        if (status === "confirmed") return { ok: true, message: "This email is already subscribed." };
        const verifyToken = randomToken_();
        const unsubscribeToken = String(sheet.getRange(rowNumber, 5).getValue() || randomToken_());
        sheet.getRange(rowNumber, 2, 1, 4).setValues([["pending", verifyToken, new Date(), unsubscribeToken]]);
        sendVerification_(email, verifyToken);
        return { ok: true, message: "Check your inbox for a confirmation link." };
      }
    }

    const verifyToken = randomToken_();
    const unsubscribeToken = randomToken_();
    sheet.appendRow([email, "pending", verifyToken, new Date(), unsubscribeToken, ""]);
    sendVerification_(email, verifyToken);
    return { ok: true, message: "Check your inbox for a confirmation link to complete subscription." };
  } finally {
    lock.releaseLock();
  }
}

function verifySubscription_(token) {
  if (!token) return "Verification link is invalid.";
  const sheet = subscriberSheet_();
  const row = findTokenRow_(sheet, 3, token);
  if (!row) return "This verification link is invalid or has already been used.";
  const status = String(sheet.getRange(row, 2).getValue());
  if (status === "confirmed") return "Your ASLP-News email subscription is already confirmed.";
  if (status !== "pending") return "This subscription is no longer pending.";
  sheet.getRange(row, 2).setValue("confirmed");
  sheet.getRange(row, 7).setValue(new Date()); // verifiedAt
  sheet.getRange(row, 3).clearContent();
  sheet.getRange(row, 5).setValue(randomToken_());
  return "Your subscription is confirmed. ASLP-News daily intelligence will arrive by email.";
}

function unsubscribe_(token) {
  if (!token) return "Unsubscribe link is invalid.";
  const sheet = subscriberSheet_();
  const row = findTokenRow_(sheet, 5, token);
  if (!row) return "This unsubscribe link is invalid or the subscription has already been removed.";
  sheet.getRange(row, 2).setValue("unsubscribed");
  sheet.getRange(row, 3).clearContent();
  return "You have been unsubscribed from ASLP-News email alerts.";
}

function sendVerification_(email, token) {
  const url = webAppUrl_() + "?action=verify&token=" + encodeURIComponent(token);
  MailApp.sendEmail({
    to: email,
    subject: "Confirm your ASLP-News subscription",
    name: SENDER_NAME,
    body: "Please confirm your email address to receive ASLP-News daily professional intelligence.\n\nConfirm subscription: " +
      url + "\n\nIf you did not request this, ignore this email."
  });
}

function subscriberSheet_() {
  const id = PropertiesService.getScriptProperties().getProperty("SPREADSHEET_ID");
  if (!id) throw new Error("Set SPREADSHEET_ID in Script Properties.");
  const ss = SpreadsheetApp.openById(id);
  let sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
    sheet.appendRow(["email", "status", "verifyToken", "createdAt", "unsubscribeToken", "lastSentAt", "verifiedAt"]);
    sheet.setFrozenRows(1);
  } else if (sheet.getLastRow() === 0) {
    sheet.appendRow(["email", "status", "verifyToken", "createdAt", "unsubscribeToken", "lastSentAt", "verifiedAt"]);
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function findTokenRow_(sheet, column, token) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return 0;
  const values = sheet.getRange(2, column, lastRow - 1, 1).getDisplayValues();
  for (let i = 0; i < values.length; i++) {
    if (String(values[i][0]) && String(values[i][0]) === String(token)) return i + 2;
  }
  return 0;
}

function webAppUrl_() {
  const url = ScriptApp.getService().getUrl();
  if (!url) throw new Error("Deploy this script as a web app before using email links.");
  return url;
}

function randomToken_() {
  return Utilities.getUuid().replace(/-/g, "") + Utilities.getUuid().replace(/-/g, "");
}

function constantTimeEquals_(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function json_(status, value) {
  // Apps Script ContentService controls the HTTP response status; include a code in JSON.
  return ContentService.createTextOutput(JSON.stringify({ ...value, status }))
    .setMimeType(ContentService.MimeType.JSON);
}

function htmlPage_(message) {
  const safe = String(message).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  return HtmlService.createHtmlOutput(
    '<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<style>body{font:16px system-ui,sans-serif;max-width:620px;margin:12vh auto;padding:24px;color:#172033}h1{font-size:1.5rem}p{line-height:1.6}</style></head>' +
    '<body><h1>ASLP-News</h1><p>' + safe + '</p><p><a href="' + webAppUrl_() + '">Back to subscription page</a></p></body></html>'
  );
}
