"""
Outlook IMAP OAuth2 — same approach as Thunderbird / eM Client.

Not Microsoft Graph. Flow:
  1) Browser login once (MSAL) → refresh token cached locally
  2) IMAP to outlook.office365.com with SASL XOAUTH2 access token

Uses Thunderbird's public Microsoft client ID (no Azure app registration needed
for personal Outlook.com / many M365 tenants).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

# Thunderbird desktop public client — see OAuth2Providers.sys.mjs
THUNDERBIRD_CLIENT_ID = "9e5f94bc-e8a4-4e73-b8be-63364c29d753"
AUTHORITY = "https://login.microsoftonline.com/common"
# MSAL adds offline_access / openid / profile itself — do not list those.
IMAP_SCOPES = [
    "https://outlook.office.com/IMAP.AccessAsUser.All",
]


def _default_cache_dir() -> Path:
    return Path(__file__).resolve().parents[2] / ".app-data" / "imap-tokens"


def cache_path_for_user(user: str, cache_dir: Path | None = None) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "._-@" else "_" for ch in (user or "").strip().lower())
    root = cache_dir or _default_cache_dir()
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{safe or 'mailbox'}.json"


def _load_cache(path: Path):
    import msal

    cache = msal.SerializableTokenCache()
    if path.exists():
        try:
            cache.deserialize(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return cache


def _save_cache(cache, path: Path) -> None:
    if getattr(cache, "has_state_changed", False):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(cache.serialize(), encoding="utf-8")


def _msal_app(cache, client_id: str | None = None):
    import msal

    return msal.PublicClientApplication(
        client_id or THUNDERBIRD_CLIENT_ID,
        authority=AUTHORITY,
        token_cache=cache,
    )


def acquire_access_token(
    user: str,
    *,
    interactive: bool = True,
    on_status: Callable[[str], None] | None = None,
    cache_dir: Path | None = None,
    client_id: str | None = None,
) -> str:
    """
    Return a fresh Outlook IMAP access token for `user`.
    Uses cached refresh token when possible; otherwise opens a browser login
    (Thunderbird-style OAuth).
    """
    email = (user or "").strip()
    if not email:
        raise RuntimeError("Mailbox email is required for Outlook OAuth")

    path = cache_path_for_user(email, cache_dir)
    cache = _load_cache(path)
    app = _msal_app(cache, client_id=client_id)

    accounts = app.get_accounts(username=email)
    if not accounts:
        accounts = app.get_accounts()

    result: dict[str, Any] | None = None
    if accounts:
        if on_status:
            on_status(f"Refreshing Outlook token for {email} ...")
        result = app.acquire_token_silent(IMAP_SCOPES, account=accounts[0])

    if not result:
        if not interactive:
            raise RuntimeError(
                f"No Outlook OAuth token for {email}. "
                "Run: python scripts/outlook_login.py --user " + email
            )
        if on_status:
            on_status(
                "Opening Microsoft login in your browser "
                "(same OAuth IMAP flow as Thunderbird) ..."
            )
        # Interactive auth code + localhost redirect — Thunderbird-compatible.
        result = app.acquire_token_interactive(
            scopes=IMAP_SCOPES,
            login_hint=email,
            prompt="select_account",
        )

    _save_cache(cache, path)

    if not result or "access_token" not in result:
        err = (result or {}).get("error_description") or (result or {}).get("error") or result
        raise RuntimeError(f"Outlook OAuth failed: {err}")

    return str(result["access_token"])


def xoauth2_string(user: str, access_token: str) -> str:
    """Raw SASL XOAUTH2 payload (imaplib base64-encodes the callback return)."""
    return f"user={user}\x01auth=Bearer {access_token}\x01\x01"


def imap_authenticate_oauth(client, user: str, access_token: str) -> None:
    auth = xoauth2_string(user, access_token)
    typ, data = client.authenticate("XOAUTH2", lambda _challenge: auth)
    if typ != "OK":
        raise RuntimeError(f"IMAP XOAUTH2 failed: {data}")


def token_status(user: str, cache_dir: Path | None = None) -> dict[str, Any]:
    path = cache_path_for_user(user, cache_dir)
    if not path.exists():
        return {"user": user, "cached": False, "path": str(path)}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        accounts = list((raw.get("Account") or {}).keys()) if isinstance(raw, dict) else []
    except Exception:
        accounts = []
    return {
        "user": user,
        "cached": True,
        "path": str(path),
        "accounts": accounts,
    }
