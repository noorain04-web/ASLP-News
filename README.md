# ASLP-News

Daily professional intelligence for speech-language pathology and audiology, with a focus on Indian developments and relevant international updates.

## Daily digest

The GitHub Actions workflow runs at **10:00 AM India Standard Time** and can also be started manually from **Actions → Speech Hearing Daily Intelligence → Run workflow**. The digest now retains up to **15** verified, non-duplicate clinical/research/policy/technology updates and up to **8** upcoming conferences. The vacancy monitor searches central institutes, AIIMS and other health institutions, Railway Recruitment Boards, and selected National Health Mission/state health recruitment portals. It checks role titles and BASLP/MASLP-related qualification wording, including PDF recruitment notices, and lists every verified open vacancy found in the monitored sources without a fixed five-job cap. Deadlines are checked against the current India date; expired, incomplete and duplicate entries are excluded. Because Indian vacancies are published across many independent central, state and district portals, coverage depends on the official sources configured in `data/feeds_v7_2_0.yaml`; the digest should not be interpreted as a guarantee that every vacancy nationwide has been captured. The alert is saved to `audit/alert_YYYY-MM-DD_v7_2_0.txt`. Telegram delivery remains available when its secrets are configured.

## Enable public email subscriptions

The repository includes an Apps Script service that can deliver the daily digest through **noorain.aslp@gmail.com** after you deploy it under that Google account. This setup is required once.

### 1. Create a subscriber spreadsheet

1. Sign in to Google as `noorain.aslp@gmail.com`.
2. Create a Google Sheet, for example **ASLP-News Subscribers**.
3. Open **Extensions → Apps Script** to create a script bound to the spreadsheet.
4. Replace the default `Code.gs` with the contents of [email-service/Code.gs](email-service/Code.gs), and add an HTML file named **Index** containing [email-service/Index.html](email-service/Index.html).
5. In Apps Script, open **Project Settings → Script Properties** and add:
   - `SPREADSHEET_ID`: the ID from the Sheet URL (the part between `/d/` and `/edit`).
   - `EMAIL_WEBHOOK_SECRET`: a long random value, at least 32 random characters. Use exactly the same value as a GitHub Actions secret. Do not commit it into this repository.
6. Save the project. The subscriber tab and column headings are initialized automatically when the service first runs. Authorize the script when Google requests it.

### 2. Deploy the web app

1. In Apps Script, choose **Deploy → New deployment → Web app**.
2. Set **Execute as: Me** (`noorain.aslp@gmail.com`).
3. Set **Who has access: Anyone** so the public can sign up, confirm, and unsubscribe. If your Google Workspace account does not allow public web apps, use a Google account that permits this setting.
4. Deploy and copy the web app URL ending in `/exec`. This is your public subscription link.
5. When the code changes later, publish a new version via **Deploy → Manage deployments → Edit → New version → Deploy**.

### 3. Add GitHub Actions secrets

Open this repository's **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret | Value |
|---|---|
| `EMAIL_WEBAPP_URL` | Deployed Apps Script web app URL ending in `/exec` |
| `EMAIL_WEBHOOK_SECRET` | The same random value stored in Apps Script Script Properties |
| `TELEGRAM_BOT_TOKEN` | Existing Telegram bot token (optional) |
| `TELEGRAM_CHAT_ID` | Existing Telegram destination/chat ID (optional) |

Do not add your Gmail password or Google account credentials to GitHub. Apps Script sends email under the Google account that authorized and deployed the script. Subscribers must confirm their address before they receive daily alerts; every alert includes an unsubscribe link.

### 4. Test before sharing

1. Open the deployed Apps Script `/exec` URL in a private/incognito window, or use the Subscribe button on the [ASLP-News GitHub Pages site](https://noorain04-web.github.io/ASLP-News/).
2. Subscribe with an email address you can access and click the confirmation link.
3. Open **Actions → Speech Hearing Daily Intelligence → Run workflow**.
4. Check the workflow logs and the confirmed subscriber's inbox.
5. Once the test succeeds, share the public [ASLP-News website](https://noorain04-web.github.io/ASLP-News/) with subscribers.

## Privacy and operational notes

- The Google Sheet stores email addresses, status, verification/unsubscribe tokens and timestamps. Restrict sheet access to the account owner and trusted administrators.
- Only confirmed addresses receive digests. Unconfirmed addresses do not receive daily emails.
- Public sign-up may attract automated abuse; monitor the sheet, Apps Script logs and quotas. CAPTCHA/rate limiting is a future hardening option.
- Google Apps Script/Gmail recipient quotas and provider anti-abuse rules apply. The service checks its remaining daily recipient quota before the broadcast. Large subscriber lists may require a dedicated mailing service.
- The service prevents a second successful broadcast for the same alert date. If the broadcast partially fails, review Apps Script logs before retrying; a retry may need the daily guard cleared in Script Properties.
- ASLP-News is an automated professional-awareness digest, not a substitute for original sources or official clinical/job notices.
