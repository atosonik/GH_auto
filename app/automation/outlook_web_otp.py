"""
Fallback OTP reader via Outlook on the web (same Chrome profile).

Used when IMAP XOAUTH2 authenticates but Microsoft returns
"User is authenticated but not connected" (mailbox IMAP blocked).
"""

from __future__ import annotations

import re
import time
from typing import Any

from app.automation.imap_client import extract_code

OUTLOOK_INBOX = "https://outlook.live.com/mail/0/"
OUTLOOK_SEARCH = (
    "https://outlook.live.com/mail/0/"
    "?search=greenhouse%20security%20code"
)


def _page_text(page) -> str:
    try:
        return str(page.inner_text("body", timeout=4000) or "")
    except Exception:
        try:
            return str(page.evaluate("() => document.body && document.body.innerText || ''") or "")
        except Exception:
            return ""


def _find_code_in_text(text: str) -> str | None:
    if not text:
        return None
    if not re.search(r"verif|security|code|otp|greenhouse|confirm", text, re.I):
        return None
    return extract_code(text)


def fetch_security_code_from_outlook_web(
    context,
    *,
    mailbox: str = "",
    timeout_ms: int = 90000,
) -> str:
    """
    Open Outlook Web in the profile browser and pull a Greenhouse security code.
    Requires the Chrome profile to already be signed into Outlook.
    """
    deadline = time.time() + (timeout_ms / 1000.0)
    page = context.new_page()
    last_error = "Outlook web mail did not show a security code"
    try:
        try:
            page.goto(OUTLOOK_SEARCH, wait_until="domcontentloaded", timeout=45000)
        except Exception as error:
            last_error = f"Could not open Outlook web: {error}"
            try:
                page.goto(OUTLOOK_INBOX, wait_until="domcontentloaded", timeout=45000)
            except Exception as error2:
                raise RuntimeError(f"{last_error}; inbox also failed: {error2}") from error2

        time.sleep(2.0)
        # Signed-out / interstitial?
        href = (page.url or "").lower()
        body = _page_text(page)
        if "login.live.com" in href or "login.microsoftonline.com" in href:
            raise RuntimeError(
                "Outlook web is not signed in on this Chrome profile. "
                "Sign into outlook.live.com once in this profile, or fix IMAP "
                f"for {mailbox or 'this mailbox'} "
                "(Microsoft error: User is authenticated but not connected)."
            )

        # Prefer search box if landing on inbox without results.
        try:
            search = page.locator(
                "input[aria-label*='Search'], input[placeholder*='Search'], #topSearchInput"
            ).first
            if search.count() > 0 and search.is_visible():
                search.click(timeout=2000)
                search.fill("greenhouse security code")
                page.keyboard.press("Enter")
                time.sleep(2.0)
        except Exception:
            pass

        while time.time() < deadline:
            body = _page_text(page)
            code = _find_code_in_text(body)
            if code:
                return code

            # Click the newest message that looks like Greenhouse verification.
            try:
                rows = page.locator(
                    "[role='option'], [role='listitem'], "
                    "[aria-label*='Greenhouse'], [aria-label*='security'], "
                    "[aria-label*='verification'], [aria-label*='code']"
                )
                count = min(rows.count(), 12)
                for i in range(count):
                    row = rows.nth(i)
                    try:
                        label = (
                            (row.get_attribute("aria-label") or "")
                            + " "
                            + (row.inner_text(timeout=800) or "")
                        )
                    except Exception:
                        continue
                    if not re.search(
                        r"greenhouse|security|verif|code|confirm", label, re.I
                    ):
                        continue
                    try:
                        row.click(timeout=2000)
                        time.sleep(1.2)
                    except Exception:
                        continue
                    reading = _page_text(page)
                    code = _find_code_in_text(reading)
                    if code:
                        return code
            except Exception as error:
                last_error = str(error)

            time.sleep(3.0)

        raise TimeoutError(
            f"Timed out waiting for Greenhouse security code in Outlook web "
            f"({mailbox or 'mailbox'}). Last: {last_error}"
        )
    finally:
        try:
            page.close()
        except Exception:
            pass


def wait_for_security_code_with_fallback(
    imap_config: dict[str, Any],
    *,
    browser_context=None,
    timeout_ms: int = 180000,
) -> str:
    """
    Prefer IMAP; if Microsoft blocks the mailbox session, fall back to Outlook web
    in the Chrome profile.
    """
    from app.automation.imap_client import wait_for_security_code

    imap_budget = min(45000, max(15000, timeout_ms // 3))
    try:
        return wait_for_security_code(imap_config, timeout_ms=imap_budget)
    except Exception as imap_error:
        imap_msg = str(imap_error)
        blocked = re.search(
            r"authenticated but not connected|IMAP is not configured|timed out",
            imap_msg,
            re.I,
        )
        if browser_context is None or not blocked:
            raise
        mailbox = str((imap_config or {}).get("user") or "")
        remaining = max(20000, timeout_ms - imap_budget)
        try:
            return fetch_security_code_from_outlook_web(
                browser_context,
                mailbox=mailbox,
                timeout_ms=remaining,
            )
        except Exception as web_error:
            raise RuntimeError(
                f"Could not read Greenhouse security code. "
                f"IMAP: {imap_msg}. Outlook web: {web_error}. "
                "For IMAP 'authenticated but not connected', open "
                "https://outlook.live.com/owa/0/captchachallenge.aspx "
                "while signed into this mailbox, enable IMAP, then retry."
            ) from web_error
