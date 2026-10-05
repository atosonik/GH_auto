"""
Smoke-test IMAP for a Greenhouse Auto Apply profile.

Outlook (default): Thunderbird-style IMAP + OAuth2
Gmail: app password

Usage:
  python scripts/test_imap.py --profile "Robert Yuan"
  python scripts/outlook_login.py --profile "Robert Yuan"   # first-time Outlook login
  python scripts/test_imap.py --user you@gmail.com --password "xxxx" --preset gmail
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
from app.automation.outlook_oauth import token_status


PRESETS = {
    "outlook": {"host": "outlook.office365.com", "port": 993, "auth": "oauth"},
    "gmail": {"host": "imap.gmail.com", "port": 993, "auth": "password"},
}


def load_state() -> dict:
    path = ROOT / ".app-data" / "app-state.json"
    if not path.exists():
        return {"profiles": []}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Test IMAP inbox read")
    parser.add_argument("--profile", help="Profile name from the app (exact match)")
    parser.add_argument("--user", help="Mailbox email (overrides profile)")
    parser.add_argument("--password", help="App password (Gmail / basic auth)")
    parser.add_argument("--preset", choices=["outlook", "gmail"], default=None)
    parser.add_argument("--auth", choices=["oauth", "password"], default=None)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument(
        "--login",
        action="store_true",
        help="Allow interactive Outlook OAuth browser login if no token cached",
    )
    args = parser.parse_args()

    cfg: dict = {}
    state = load_state()
    profiles = state.get("profiles") or []

    if args.profile:
        match = next(
            (p for p in profiles if (p.get("name") or "").strip() == args.profile.strip()),
            None,
        )
        if not match:
            names = ", ".join(p.get("name") or "?" for p in profiles) or "(none)"
            print(f'Profile "{args.profile}" not found. Available: {names}')
            return 1
        cfg = dict(match.get("imap") or {})
        print(f"Using profile: {match.get('name')}")
    elif args.user:
        preset = args.preset or "outlook"
        cfg = {
            "preset": preset,
            **PRESETS[preset],
            "user": args.user,
            "password": args.password or "",
        }
    else:
        for profile in profiles:
            imap = profile.get("imap") or {}
            if imap.get("user"):
                cfg = dict(imap)
                print(f"Using profile: {profile.get('name')}")
                break
        if not cfg:
            print(
                "No IMAP mailbox found.\n"
                "1) Open the app > Profiles > set Mailbox email\n"
                "2) For Outlook, run: python scripts/outlook_login.py --profile \"Name\""
            )
            return 1

    if args.user:
        cfg["user"] = args.user
    if args.password:
        cfg["password"] = args.password
    if args.preset:
        cfg["preset"] = args.preset
        cfg.update(PRESETS[args.preset])
    if args.auth:
        cfg["auth"] = args.auth

    preset = (cfg.get("preset") or args.preset or "outlook").lower()
    if preset in PRESETS:
        cfg.setdefault("host", PRESETS[preset]["host"])
        cfg.setdefault("port", PRESETS[preset]["port"])
        cfg.setdefault("auth", PRESETS[preset]["auth"])

    user = cfg.get("user") or ""
    host = cfg.get("host") or ""
    auth = cfg.get("auth") or "oauth"
    print(f"Connecting to {host}:993 as {user} (auth={auth}) ...")
    if auth == "oauth":
        print("Status:", token_status(user))
        if not token_status(user).get("cached") and not args.login:
            print(
                "No OAuth token cached yet.\n"
                f'Run: python scripts/outlook_login.py --user {user}\n'
                "or re-run this command with --login"
            )
            return 1

    try:
        messages = fetch_recent_messages(
            cfg,
            limit=args.limit,
            interactive_oauth=bool(args.login) or auth == "oauth",
        )
    except Exception as error:
        print(f"FAILED: {error}")
        print(
            "\nTips:\n"
            "- Outlook: python scripts/outlook_login.py --user you@outlook.com\n"
            "  (browser OAuth once, then IMAP XOAUTH2 — Thunderbird method)\n"
            "- Enable IMAP in Outlook.com Settings > Mail > Forwarding and IMAP\n"
            "- Gmail: use --preset gmail with an app password"
        )
        return 2

    if not messages:
        print("OK — logged in, but INBOX is empty.")
        return 0

    def safe(text: object) -> str:
        return str(text or "").encode("ascii", "replace").decode("ascii")

    print(f"OK - logged in. Newest {len(messages)} message(s):\n")
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
