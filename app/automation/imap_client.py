from __future__ import annotations

import email
import imaplib
import re
import time
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from typing import Any


def _strip_html(text: str) -> str:
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text or "")
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|&#160;", " ", text, flags=re.I)
    text = re.sub(r"&amp;", "&", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_code(text: str) -> str | None:
    raw = text or ""
    plain = _strip_html(raw) if "<" in raw else raw
    # Greenhouse uses alphanumeric codes like 4uIDHJRR; others use 4-8 digits.
    patterns = [
        r"copy and paste this code[^:]{0,120}:\s*([A-Za-z0-9]{6,12})",
        r"security code field[^:]{0,80}:\s*([A-Za-z0-9]{6,12})",
        r"(?:security\s*code|verification\s*code|one[- ]time(?:\s*code)?|otp)[^A-Za-z0-9]{0,60}([A-Za-z0-9]{6,12})",
        r"(?:code|otp|verification)\D{0,20}(\d{4,8})",
        r"\b(\d{6})\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, plain, re.I):
            code = match.group(1).strip()
            if re.fullmatch(r"20\d{2}", code):  # years
                continue
            if code.lower() in {"greenhouse", "security", "application", "resubmit"}:
                continue
            if code in {"0000", "000000", "1234", "123456", "10011"}:
                continue
            # Prefer mixed alnum Greenhouse-style or pure numeric OTP.
            if re.fullmatch(r"\d{4,8}", code) or re.fullmatch(r"[A-Za-z0-9]{6,12}", code):
                return code
    return None


def _decode_subject(raw) -> str:
    parts = decode_header(raw or "")
    out: list[str] = []
    for part, enc in parts:
        if isinstance(part, bytes):
            out.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(str(part))
    return " ".join(out)


def _normalize_config(imap_config: dict[str, Any] | None) -> dict[str, Any]:
    cfg = dict(imap_config or {})
    user = str(cfg.get("user") or "").strip()
    password = re.sub(r"\s+", "", str(cfg.get("password") or ""))
    preset = str(cfg.get("preset") or "").strip().lower()
    host = str(cfg.get("host") or "").strip()
    if not host:
        host = "imap.gmail.com" if preset == "gmail" else "outlook.office365.com"
    port = int(cfg.get("port") or 993)
    auth = str(cfg.get("auth") or "").strip().lower()
    # Outlook defaults to OAuth (Thunderbird-style) because basic auth is disabled.
    if not auth:
        if preset == "gmail" or "gmail.com" in host:
            auth = "password"
        elif "outlook" in host or "office365" in host or preset == "outlook":
            auth = "oauth"
        else:
            auth = "password" if password else "oauth"
    return {
        "user": user,
        "password": password,
        "host": host,
        "port": port,
        "preset": preset or ("gmail" if auth == "password" and "gmail" in host else "outlook"),
        "auth": auth,
        "client_id": str(cfg.get("client_id") or "").strip() or None,
    }


def connect_imap(
    imap_config: dict[str, Any],
    *,
    interactive_oauth: bool = False,
) -> imaplib.IMAP4_SSL:
    """
    Open an authenticated IMAP session.
    Outlook: IMAP + OAuth2 XOAUTH2 (Thunderbird method).
    Gmail: app-password login.
    """
    cfg = _normalize_config(imap_config)
    user = cfg["user"]
    host = cfg["host"]
    port = cfg["port"]
    if not user:
        raise RuntimeError("IMAP mailbox email is not configured")

    client = imaplib.IMAP4_SSL(host, port)
    try:
        if cfg["auth"] == "oauth":
            from app.automation.outlook_oauth import (
                acquire_access_token,
                imap_authenticate_oauth,
            )

            token = acquire_access_token(
                user,
                interactive=interactive_oauth,
                client_id=cfg.get("client_id"),
            )
            imap_authenticate_oauth(client, user, token)
        else:
            password = cfg["password"]
            if not password:
                raise RuntimeError(
                    "IMAP app password is not configured for this profile"
                )
            typ, data = client.login(user, password)
            if typ != "OK":
                raise RuntimeError(f"IMAP login failed: {data}")
        return client
    except Exception:
        try:
            client.logout()
        except Exception:
            pass
        raise


def _message_blob(message) -> tuple[str, str, str, str]:
    subject = _decode_subject(message.get("Subject"))
    from_addr = message.get("From") or ""
    date = message.get("Date") or ""
    blob = ""
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True) or b""
                blob += payload.decode("utf-8", errors="replace") + "\n"
                break
        if not blob:
            for part in message.walk():
                if part.get_content_type() == "text/html":
                    payload = part.get_payload(decode=True) or b""
                    blob += payload.decode("utf-8", errors="replace") + "\n"
                    break
    else:
        payload = message.get_payload(decode=True) or b""
        blob = payload.decode("utf-8", errors="replace")
    return subject, from_addr, date, blob


def fetch_recent_messages(
    imap_config: dict[str, Any],
    limit: int = 8,
    *,
    interactive_oauth: bool = False,
) -> list[dict[str, Any]]:
    """
    Connect once and return the newest inbox messages (subject/from/date/snippet).
    Used for IMAP smoke tests — not for OTP waiting.
    """
    cfg = _normalize_config(imap_config)
    if not cfg["user"]:
        raise RuntimeError(
            "IMAP is not configured (need mailbox email; Outlook uses OAuth login)"
        )
    if cfg["auth"] == "password" and not cfg["password"]:
        raise RuntimeError(
            "IMAP is not configured (need user and app password for Gmail)"
        )

    client = connect_imap(imap_config, interactive_oauth=interactive_oauth)
    try:
        typ, _ = client.select("INBOX")
        if typ != "OK":
            raise RuntimeError("Could not select INBOX")

        status, data = client.search(None, "ALL")
        if status != "OK":
            raise RuntimeError("IMAP SEARCH failed")
        ids = data[0].split()
        if not ids:
            return []

        out: list[dict[str, Any]] = []
        for msg_id in reversed(ids[-(max(1, int(limit))) :]):
            status, fetched = client.fetch(msg_id, "(RFC822)")
            if status != "OK" or not fetched or not fetched[0]:
                continue
            message = email.message_from_bytes(fetched[0][1])
            subject, from_addr, date, blob = _message_blob(message)
            snippet = re.sub(r"\s+", " ", blob).strip()[:160]
            code = None
            if re.search(r"verif|security|code|otp|greenhouse|confirm", blob + subject, re.I):
                code = extract_code(subject + "\n" + blob)
            out.append(
                {
                    "id": msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id),
                    "from": from_addr,
                    "subject": subject,
                    "date": date,
                    "snippet": snippet,
                    "possible_code": code,
                }
            )
        return out
    finally:
        try:
            client.logout()
        except Exception:
            pass


def wait_for_security_code(imap_config: dict[str, Any], timeout_ms: int = 180000) -> str:
    cfg = _normalize_config(imap_config)
    if not cfg["user"]:
        raise RuntimeError("IMAP is not configured for this profile")
    if cfg["auth"] == "password" and not cfg["password"]:
        raise RuntimeError("IMAP is not configured for this profile")

    deadline = time.time() + (timeout_ms / 1000.0)
    since = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%d-%b-%Y")
    # First connection may need interactive OAuth if token missing.
    interactive_once = cfg["auth"] == "oauth"
    last_error: Exception | None = None
    blocked_hits = 0

    while time.time() < deadline:
        client = None
        try:
            client = connect_imap(imap_config, interactive_oauth=interactive_once)
            interactive_once = False
            client.select("INBOX")
            status, data = client.search(None, f'(SINCE "{since}")')
            if status == "OK":
                ids = data[0].split()
                for msg_id in reversed(ids[-40:]):
                    status, fetched = client.fetch(msg_id, "(RFC822)")
                    if status != "OK" or not fetched or not fetched[0]:
                        continue
                    message = email.message_from_bytes(fetched[0][1])
                    subject, _from, _date, body = _message_blob(message)
                    blob = subject + "\n" + body
                    if not re.search(
                        r"verif|security|code|otp|greenhouse|confirm", blob, re.I
                    ):
                        continue
                    code = extract_code(blob)
                    if code:
                        return code
        except Exception as error:
            last_error = error
            msg = str(error)
            # Microsoft mailbox circuit-breaker — retrying IMAP won't help.
            if re.search(r"authenticated but not connected", msg, re.I):
                blocked_hits += 1
                if blocked_hits >= 2:
                    raise RuntimeError(
                        "IMAP: User is authenticated but not connected "
                        f"for {cfg['user']}. Microsoft is blocking IMAP on this "
                        "mailbox (try captcha at "
                        "https://outlook.live.com/owa/0/captchachallenge.aspx)."
                    ) from error
            interactive_once = False
        finally:
            if client is not None:
                try:
                    client.logout()
                except Exception:
                    pass
        time.sleep(5)

    if last_error and re.search(
        r"authenticated but not connected", str(last_error), re.I
    ):
        raise RuntimeError(
            "IMAP: User is authenticated but not connected "
            f"for {cfg['user']}."
        ) from last_error
    raise TimeoutError("Timed out waiting for a security code email")
