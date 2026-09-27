# Laptop Brand Outreach Automation (India)

A cautious, review-first Python automation for sending personalized laptop-support requests to laptop brands operating in India.

**Important:** this is intentionally **not** a one-click mass spammer. It creates brand-specific drafts first, requires per-brand approval, sends at a controlled rate, and records every successful send so a rerun does not duplicate outreach.

## What it does

- Maintains a researched `targets.csv` with direct public contact routes and brand-specific personalization.
- Maintains `manual_targets.csv` for brands where an appropriate public email was not confidently verified.
- Creates one readable draft per brand in `drafts/`.
- Uses one truthful template but changes the brand, product family, appreciation paragraph, India context, recipient, and routing note for each company.
- Sends **only** rows with `approved=yes`.
- Refuses to send if your profile still contains placeholders.
- Uses SMTP over STARTTLS (Gmail defaults included, but generic SMTP works).
- Limits the number of messages per run and inserts a delay between messages.
- Writes `logs/sent.jsonl` so already-sent brand/email pairs are skipped on future runs.
- Uses only the Python standard library—no `pip install` is required.

## 1. Personalize your real story

Open `config.json` and replace the placeholder values in:

- `profile.full_name`
- `profile.story`
- `profile.use_case`
- `profile.signature`
- optional portfolio / LinkedIn URLs

Keep the story accurate. A company is more likely to take a concise, verifiable student request seriously than an exaggerated emotional story.

The provided request explicitly allows the brand to offer a review unit, student-support route, refurbished/demo device, sponsorship, discount, or referral if a free new laptop is not possible. You can change that wording in `config.json`.

## 2. Validate

From this folder:

```bash
python outreach.py validate
```

The program will tell you if your profile still has placeholders or if the contact CSV has structural problems.

## 3. Generate drafts (sends nothing)

```bash
python outreach.py preview
```

Review every file in `drafts/`. Also check the public source URL shown at the top of each draft before sending; contacts can change over time.

## 4. Approve only the messages you actually want sent

Open `targets.csv`. Change the final approval field for selected rows from:

```text
approved=no
```

to:

```text
approved=yes
```

Do **not** approve a contact if the draft feels irrelevant to that inbox.

## 5. Configure Gmail / SMTP safely

The script never stores your mail password in the ZIP.

For Gmail, use a **Google App Password** rather than your normal Google password. App Password availability depends on your Google account/security configuration.

macOS / Linux:

```bash
export SMTP_USERNAME="you@gmail.com"
export SMTP_PASSWORD="YOUR_APP_PASSWORD"
export FROM_EMAIL="you@gmail.com"
```

Windows PowerShell:

```powershell
$env:SMTP_USERNAME="you@gmail.com"
$env:SMTP_PASSWORD="YOUR_APP_PASSWORD"
$env:FROM_EMAIL="you@gmail.com"
```

For another provider, also set `SMTP_HOST` and `SMTP_PORT`, or edit the non-secret defaults in `config.json`.

## 6. Send reviewed + approved messages

```bash
python outreach.py send --confirmed
```

The default configuration sends at most **10 emails per run** and waits **45 seconds** between messages. You can make it more conservative in `config.json`.

You can lower the run limit without editing the file:

```bash
python outreach.py send --confirmed --limit 3
```

`--limit` can only lower, not exceed, the configured maximum.

## Duplicate protection

A successful send is appended to:

```text
logs/sent.jsonl
```

The unique key combines the brand and recipient email. If you rerun the sender, those pairs are skipped.

If you deliberately need to resend later, do not blindly delete the whole ledger. Review it and remove only the specific historical line you intentionally want to retry.

## Adding a new company

Add one row to `targets.csv` only when you have:

1. A public business/contact email that is appropriate enough for the request.
2. An official or otherwise trustworthy source URL.
3. A specific, truthful appreciation sentence.
4. A current product line or category relevant to your use.
5. A source-check date.

If the company only exposes a web form, put it in `manual_targets.csv`; do not guess employee email addresses.

## Improving reply odds without being misleading

A short outreach works best when it gives the recipient a reason to route it internally. Before approving a draft, consider adding one **real** proof point to your story: a GitHub/portfolio project, a college project, an open-source contribution, a small audience/community if you genuinely have one, or a concrete project you will complete with the machine.

Avoid claims such as “your brand has always been my lifelong dream” unless that is literally true. The template instead shows brand appreciation through verifiable product/company details.

## Why some brands are in `manual_targets.csv`

For several companies, public search surfaced only customer-support, grievance, anti-scraping, or generic contact routes. The project keeps these manual rather than automatically firing sponsorship requests into unrelated complaint/support inboxes.

## Files

```text
outreach.py             Main automation
config.json             Your profile, request wording, mail/sending settings
targets.csv             Direct-email targets + personalization + sources
manual_targets.csv      Brands needing a form/manual route
templates/email.txt     Body template
templates/subject.txt   Subject template
.env.example            Environment-variable example (no secrets)
drafts/                 Generated previews
logs/                    Send history
SOURCES.md               Research notes and official-source references
tests/test_outreach.py   Basic tests
```

## Safety / etiquette defaults

- Review every message before approval.
- Contact one relevant inbox per brand, not multiple employees at the same company.
- Do not repeatedly follow up if there is no response.
- If a company asks not to be contacted, mark it unapproved and keep that preference.
- Re-check contact pages before a future campaign because people and inboxes change.
- Never put your normal email password in `config.json` or `targets.csv`.

## Troubleshooting

### Gmail says authentication failed
Use an App Password where supported and make sure the account/email in `SMTP_USERNAME` is correct. Do not use your ordinary Google password.

### `No targets are approved`
That is intentional. You must edit `targets.csv` after reviewing the generated drafts.

### A message was already sent
The recipient pair is in `logs/sent.jsonl`. The script is protecting you from duplicate outreach.

### An address bounces
Set that row back to `approved=no`, verify the company’s current official contact page, update the email/source/date, preview again, and only then retry.
