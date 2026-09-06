# Automatic scanner

No model tokens, paid scraping API, or browser credentials are used. Python uses public HTML, and GitHub stores the published snapshot. A new listing means a newly discovered URL, not necessarily a newly posted ad. Dates shown are observation times. Missing sources explicitly report blocked/partial status. A successful search does not establish seller availability or dimensions.

Run locally: `python3 scanner.py --publish`. `run-scanner.command` updates the checkout first. The macOS schedule runs at 9am, 1pm and 5pm in the Mac's timezone while the Mac is awake. Sleep delays or skips execution according to macOS scheduling; it is not an always-on cloud service.

From your phone, use **Scan now** → GitHub **Run workflow**. This runs the same script on a GitHub runner, not on your Mac. No AI tokens are used. The website reads the committed snapshot directly, including when GitHub's automated push does not rebuild Pages.

All ten sources are attempted. A source stops on a blocked/login/unparseable page and reports how many queries it completed. Public pages that do work are parsed automatically; this does not bypass account gates. At most 30 visible records per query are collected. Search pages may be regional defaults; location/delivery that cannot be verified are labeled unverified. The other 70 donor searches are lower priority. Configure queries in scanner-config.json; adding a device-local watch in the website does not change the shared scanner configuration.

Alert delivery uses SMTP with STARTTLS. Configure CHRIS_SMTP_HOST, CHRIS_SMTP_USER, CHRIS_SMTP_PASSWORD, CHRIS_MAIL_FROM and CHRIS_MAIL_TO in the environment for local runs, or repository Secrets for manual GitHub runs. No credentials go in this repository. Until configured, new-item digests are written as .scanner/latest-alert.txt and .eml. Failed local email stays queued for retry; local repeated scans do not repeat already delivered new-item alerts. The GitHub manual runner has ephemeral storage and does not retain failed outboxes between runs.

The public snapshot includes discovered listings, search phrases and scan status. Your personal offers, negotiation timeline, email credentials and recipient remain outside the public snapshot. Use the browser's board backup to move private device-local data between devices.
