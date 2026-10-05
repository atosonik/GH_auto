# Greenhouse Auto Apply

Python desktop app that applies to Greenhouse jobs **per Chrome profile**.

## What it does

1. Select Greenhouse job URLs and profiles (name + Chrome profile index)
2. **Start** opens one Chrome window per selected profile, tiled vertically
3. Each window uses 2 tabs: Greenhouse job + `chat.deepseek.com`
4. Reads the JD → sends profile prompt + JD to DeepSeek  
   (auto-clicks **Continue** / **Reply** when they appear)
5. Waits for resume JSON → hands it to `D:\3.Work\Develop\bid\main.py` for PDF generation
6. Fills the Greenhouse form, uploads the PDF, submits
7. If a security code appears, reads it over IMAP for that profile

## Setup

```powershell
cd C:\greenhouse
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

Point **Settings** at your bid project paths if they differ from the defaults:

- prompts dir → `D:\3.Work\Develop\bid\prompts`
- profiles.json → `D:\3.Work\Develop\bid\extension-deepseek\profiles.json`
- main.py → `D:\3.Work\Develop\bid\main.py`

Profile **names must match** `profiles.json` / prompt filenames exactly (e.g. `Peter Chu`).

## Run

```powershell
python main.py
```

Close Chrome before the first Start for each profile — the app clones login cookies into an isolated automation profile under `.app-data\.chrome-profiles`.

## IMAP (security codes)

Used only when Greenhouse asks for a verification code.

**Outlook** (Thunderbird method — IMAP + OAuth2, not Graph):
1. Set the profile mailbox email (Outlook preset)
2. One-time browser login:
   `python scripts/outlook_login.py --profile "Robert Yuan"`
3. Tokens are cached under `.app-data/imap-tokens/`

**Gmail**: set preset Gmail + app password in the profile row.
