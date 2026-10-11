# Greenhouse Auto Apply

Python desktop app that applies to Greenhouse jobs **per Chrome profile**.

## What it does

1. Select Greenhouse job URLs and profiles (name + Chrome profile index)
2. **Start** opens one Chrome window per selected profile, tiled vertically
3. Each window uses 2 tabs: Greenhouse job + `chat.deepseek.com`
4. Reads the JD → sends profile prompt + JD to DeepSeek  
   (auto-clicks **Continue** / **Reply** when they appear)
5. Waits for resume JSON → waits for PDF notification on `localhost:615`
6. Fills the Greenhouse form, uploads the received PDF, submits
7. If a security code appears, reads it over IMAP for that profile

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

In **Settings**, choose the extension folder that contains `prompts/`, `profile-context/`, and `profiles.json`. Those paths are not set until you pick a folder.

Profile **names must match** `profiles.json` and the prompt filenames exactly.

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
   `python scripts/outlook_login.py --profile "Your Name"`
3. Tokens are cached under `.app-data/imap-tokens/`

**Gmail**: set preset Gmail + app password in the profile row.
