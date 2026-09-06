# Automatic scanner

No model tokens, paid scraping API, or browser credentials are used. Python uses public HTML, and GitHub stores the published snapshot. A new listing means a newly discovered URL, not necessarily a newly posted ad. Dates shown are observation times. Missing sources explicitly report blocked/partial status. A successful search does not establish seller availability or dimensions.

Run locally: `python3 scanner.py --publish`. `run-scanner.command` updates the checkout first. The installed macOS working copy is in `~/Library/Application Support/ChrisList/app`; its logs are in the parent ChrisList folder. The schedule runs at 9am, 1pm and 5pm in the Mac's timezone while the Mac is awake. Sleep delays or skips execution according to macOS scheduling; it is not an always-on cloud service.

From your phone, use **Scan now** → GitHub **Run workflow**. This runs the same script on a GitHub runner, not on your Mac. No AI tokens are used. The website reads the committed snapshot directly, including when GitHub's automated push does not rebuild Pages.

All ten sources are attempted. A source stops on a blocked/login/unparseable page and reports how many queries it completed. Public pages that do work are parsed automatically; this does not bypass account gates. At most 30 matching visible records per query are collected. Search pages may be regional defaults; location/delivery that cannot be verified are labeled unverified. The other 70 donor searches are lower priority. Configure queries in scanner-config.json. For a new description on your phone, choose **Add description to automatic scans** and submit the GitHub search request. The scanner reads requests authored by the repository owner; close the request to stop scanning it. This is separate from device-local watches. The first 100 open repository issues are checked each run; the scanner reports API intake failures.

Automatic local alerts use the Mac's Mail and Messages apps through `alert_delivery.py`, with no model or paid API. Private settings live in `.scanner/alert-config.json` (never commit recipients or account settings). Email and text have separate persistent submission receipts, so a failed channel can retry without repeating the successful channel. Existing `pending.json` items migrate into the new outbox. Each scan sends at most one digest per enabled channel: up to ten email highlights or two text highlights, primary matches first, with a total count and dashboard link.

Private configuration example (replace placeholders on the Mac):

```json
{
  "email": {"enabled": true, "transport": "mail", "sender": "SENDER", "recipient": "RECIPIENT"},
  "text": {"enabled": true, "recipient": "PHONE", "service_id": "MESSAGES_SERVICE_ID"}
}
```

A missing channel waits for configuration. Setting `enabled` to `false` permanently skips its pending items and items discovered while disabled; reenabling starts with future items. Previously submitted records stay deduplicated. `.scanner/alert-outbox.json` contains per-item channel receipts and batch IDs. Records marked `held` require checking Mail/Messages (or the recipient) before an operator changes that channel to `submitted` or, only when known unsent, `pending`. Never automatically replay a held batch.

A successful adapter call means the app or SMTP server accepted the message, not that it reached the recipient. An interrupted or timed-out submission is held for review to avoid automatic duplicates. The Mac must be awake, signed into its messaging accounts, and allow the scheduled process to control Mail/Messages. Private failures and receipts remain under `.scanner/`; public scan status contains no recipients or raw delivery errors. Legacy SMTP environment settings remain supported. GitHub runs cannot use this Mac's apps and have ephemeral outboxes; automatic device alerts run locally.

The public snapshot includes discovered listings, search phrases and scan status. Your personal offers, negotiation timeline, email credentials and recipient remain outside the public snapshot. Use the browser's board backup to move private device-local data between devices.

## Facebook and strict machine eligibility (September 5 update)
Facebook now uses a rendered local Chromium browser via Playwright 1.58.0. The first complete browser scan read all 76 configured searches and saved 593 distinct Facebook listings. It collects the first visible batch, not exhaustive inventory. Facebook may broaden the requested Anaheim location; each ad keeps its displayed city or shipping label. No login, proxy, CAPTCHA bypass, paid scraper, or model is required for these public scans. If Facebook later requires login, use `connect-facebook.command`; profile data stays in Application Support, outside Git. Install on another Mac with `python3 -m pip install -r requirements-facebook.txt` and `python3 -m playwright install chromium`.

Machine matching now fails closed: Roland CAMM-1, Graphtec, generic unknown cutters and accessories are hidden. The small evidence-backed catalog in `machine-rules.json` covers exact models with a pen and cutter installed together. It is NOT an exhaustive list of compatible machines. Model capability does not verify seller-included tools or condition. Candidates carry separate working/body widths and a conspicuous unverified 500-foot plain-paper feed / sheet-separation status. The Cameo 3 crosscutter is manual. Existing browser records that fail the rule are retained privately in `hidden_machines`, excluded from cards and notifications. Public feed cleanup also removes them.

## Local assistant and messaging app
Run `python3 companion.py`; it serves the same board at port 8766. On this installation the local app is available at `http://127.0.0.1:8766/` on the Mac or `http://kms-mac-mini-1.tail016811.ts.net:8766/` on the existing Tailscale network (Tailscale Serve proxies to loopback). No public port forwarding is configured. Public GitHub Pages remains a snapshot viewer. Local AI and sending require reaching the Mac; the GitHub site cannot run the Mac's model by itself.

The assistant calls ONLY local Ollama at 127.0.0.1:11434 using the already-installed `qwen3.5:latest`. It asks questions and drafts a search specification. The user edits and approves it before it enters `.scanner/watches.json` and triggers a scan. Keywords, required/excluded phrases and maximum asking price are applied; technical requirements without evidence are retained for verification, not inferred as satisfied. No model call is used for scheduled scanning. The manual add-ad form has been removed.

Select ads, open Message selected ads, choose free pickup / offer / tool questions / custom, and review each message. The public page can transfer the exact batch to the Mac app in the URL fragment (not a public GitHub issue). Explicit Send queues messages locally. Facebook sending uses a dedicated tab in the user's normal Chrome via Apple Events, requiring Chrome View > Developer > Allow JavaScript from Apple Events and a signed-in Facebook account. It never extracts cookies. A message is marked sent only after Facebook shows a confirmation. Ambiguous delivery is never automatically retried; identical submitted messages are deduplicated. Other platforms explicitly report manual_send_required because they have no send connector yet. Do not claim that bulk sending across all ten is implemented. No unattended negotiation is enabled.

Ad popups show all collected gallery images. The local app retrieves ad photos on opening: Facebook's exposed Product photo thumbnails, or Product JSON-LD images on other platforms. Recommendation images are excluded. Missing/incomplete galleries are labeled rather than advertised as complete; Facebook sometimes exposes thumbnails only. Photos require internet and remote image URLs may expire. Gallery metadata caches locally. Saved text and the local chat work without internet; marketplace scanning and sending require it.

`companion.py` serves a static allowlist, checks Host/Origin on requests, and requires a same-origin custom header for mutations. Private queues, model chats, and browser sessions are not served as files or committed. The user requested no dashboard password, so the app is bound to loopback and exposed only through Tailscale Serve.


### Messaging repair
The failed six-ad batch was all OfferUp and was recorded as manual_send_required; no messages were sent. OfferUp now has an adapter for its documented Ask / New Message / Send website flow. This adapter has not been validated against a signed-in account: Chrome Apple Events remains disabled on this installation. Preflight now rejects blocked Chrome connections and unsupported platforms before queueing. The modal polls delivery for the submitted batch and displays plain-language failures. Re-submitting a previously blocked OfferUp draft is allowed, but sent/uncertain messages are not replayed. Chrome and OfferUp sign-in must be connected before live delivery can be verified.

Email selected ad links now uses only checked records, with a recipient and editable preview. It clearly opens an external email draft (not a seller message). Oversized mailto links are prevented, with an .eml download fallback. This manual draft action is separate from the automatic local Mail/Messages alert service.


### Connection checks
The Mac app distinguishes a closed Chrome window from a disabled Chrome Apple Events setting or a denied macOS Automation permission. These checks concern seller messaging; viewing listings and automatic Mail/Messages alerts use separate paths. A connection check does not prove a marketplace is signed in or a seller received anything.
