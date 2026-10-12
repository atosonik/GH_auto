# Bidding (Greenhouse Auto Apply)

Desktop app that applies to Greenhouse jobs across Chrome profiles.

## What it does

1. **Profiles** — add people, pick their Chrome profile, connect Outlook, mark Active
2. **Main** — paste job URLs in bulk, check active profiles, Start
3. Each run opens Greenhouse + DeepSeek per profile, builds a resume via clipboard + exporter notification on `localhost:615`, fills and submits
4. Progress shows in the Profile / URL / Status table
5. Job URLs and run progress reset every time you reopen the app; profiles and settings stay

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

In **Settings**, choose the extension folder that contains `prompts/`, `profile-context/`, and `profiles.json`.

Profile **names must match** `profiles.json` and the prompt filenames exactly.

## Run

```powershell
python main.py
```

## IMAP (security codes)

Used only when Greenhouse asks for a verification code.

**Outlook**
1. On the Profiles page, enter the Outlook address and click **Connect mailbox**
2. Or run: `python scripts/outlook_login.py --profile "Your Name"`
3. Tokens are cached under `.app-data/imap-tokens/`

**Gmail**: set preset Gmail + app password in the profile row (advanced / scripts).
