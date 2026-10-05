"""
One-time Outlook IMAP OAuth login (Thunderbird-style).

Opens a Microsoft browser window, caches a refresh token, then lists recent mail.

  python scripts/outlook_login.py --user robertyuan81@outlook.com
  python scripts/outlook_login.py --profile "Robert Yuan"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.automation.imap_client import fetch_recent_messages
from app.automation.outlook_oauth import acquire_access_token, token_status


def load_state() -> dict:
    path = ROOT / ".app-data" / "app-state.json"
    if not path.exists():
        return {"profiles": []}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Outlook IMAP OAuth login (Thunderbird method)")
    parser.add_argument("--profile", help="App profile name")
    parser.add_argument("--user", help="Mailbox email")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    user = (args.user or "").strip()
    if args.profile and not user:
        profiles = load_state().get("profiles") or []
        match = next(
            (p for p in profiles if (p.get("name") or "").strip() == args.profile.strip()),
            None,
        )
        if not match:
            print(f'Profile "{args.profile}" not found')
            return 1
        user = str((match.get("imap") or {}).get("user") or "").strip()
        print(f"Using profile: {match.get('name')}")

    if not user:
        print("Provide --user email@outlook.com or --profile \"Name\"")
        return 1

    print("Method: IMAP + OAuth2 XOAUTH2 (same as Thunderbird — not Graph API)")
    print(f"Mailbox: {user}")
    print(token_status(user))

    try:
        token = acquire_access_token(user, interactive=True, on_status=print)
    except Exception as error:
        print(f"LOGIN FAILED: {error}")
        return 2

    print(f"Token OK (length {len(token)}). Fetching inbox via IMAP ...")
    try:
        messages = fetch_recent_messages(
            {
                "preset": "outlook",
                "host": "outlook.office365.com",
                "port": 993,
                "user": user,
                "auth": "oauth",
            },
            limit=args.limit,
            interactive_oauth=False,
        )
    except Exception as error:
        print(f"IMAP FAILED: {error}")
        return 3

    if not messages:
        print("OK — OAuth + IMAP works. Inbox is empty.")
        return 0

    def safe(text: object) -> str:
        return str(text or "").encode("ascii", "replace").decode("ascii")

    print(f"OK - OAuth + IMAP works. Newest {len(messages)} message(s):\n")
    for i, msg in enumerate(messages, start=1):
        print(f"{i}. {safe(msg.get('date'))}")
        print(f"   From:    {safe(msg.get('from'))}")
        print(f"   Subject: {safe(msg.get('subject'))}")
        if msg.get("snippet"):
            print(f"   Snippet: {safe(msg.get('snippet'))}")
        if msg.get("possible_code"):
            print(f"   Code?:   {safe(msg.get('possible_code'))}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
