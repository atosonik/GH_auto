from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

COPY_ITEMS = (
    "Cookies",
    "Cookies-journal",
    "Login Data",
    "Login Data-journal",
    "Web Data",
    "Web Data-journal",
    "Preferences",
    "Secure Preferences",
    "Bookmarks",
    "Favicons",
    "History",
    "Network",
    "Local Storage",
    "Session Storage",
    "IndexedDB",
)

# Journals are often locked while Chrome is open — skip them during soft sync.
SOFT_SKIP = {"Cookies-journal", "Login Data-journal", "Web Data-journal"}

DEFAULT_CDP_PORT = 9222


def chrome_exe_candidates() -> list[Path]:
    local = os.environ.get("LOCALAPPDATA", "")
    program = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    program86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    return [
        Path(program) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(program86) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(local) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]


def find_chrome_executable() -> str:
    for candidate in chrome_exe_candidates():
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError("Google Chrome was not found")


def chrome_directory_name(number: int | str) -> str:
    n = int(number)
    return "Default" if n == 0 else f"Profile {n}"


def list_chrome_profiles(user_data_dir: str | None = None) -> list[dict[str, Any]]:
    root = Path(user_data_dir) if user_data_dir else (
        Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data"
    )
    profiles: list[dict[str, Any]] = []
    try:
        parsed = json.loads((root / "Local State").read_text(encoding="utf-8"))
        info = (((parsed or {}).get("profile") or {}).get("info_cache") or {})
        for directory, meta in info.items():
            if directory == "Default":
                number = 0
            else:
                parts = directory.split(" ")
                number = int(parts[-1]) if len(parts) >= 2 and parts[-1].isdigit() else -1
            profiles.append(
                {
                    "directory": directory,
                    "number": number,
                    "displayName": (meta or {}).get("name") or directory,
                }
            )
        profiles.sort(key=lambda p: p.get("number", 0))
        return profiles
    except (OSError, json.JSONDecodeError, ValueError):
        return [{"directory": "Default", "number": 0, "displayName": "Default"}]


def _copy_item(src: Path, dest: Path) -> None:
    if src.is_dir():
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(src, dest, dirs_exist_ok=False)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def ensure_profile_clone(
    chrome_user_data_dir: str,
    profile_number: int,
    clone_root: str | Path,
    *,
    force: bool = False,
) -> str:
    """
    Isolated automation profile. Once cloned, your normal Chrome can stay open —
    later runs reuse this folder and do not touch the live User Data.
    """
    source_name = chrome_directory_name(profile_number)
    source_dir = Path(chrome_user_data_dir) / source_name
    user_data_dir = Path(clone_root) / f"profile-{profile_number}"
    target_dir = user_data_dir / "Default"
    marker = target_dir / ".cloned"

    if not source_dir.exists():
        raise FileNotFoundError(f"Chrome profile folder missing: {source_dir}")

    user_data_dir.mkdir(parents=True, exist_ok=True)
    if target_dir.exists() and marker.exists() and not force:
        return str(user_data_dir)

    if target_dir.exists() and force:
        shutil.rmtree(target_dir, ignore_errors=True)
    target_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    locked: list[str] = []
    for item in COPY_ITEMS:
        if item in SOFT_SKIP:
            continue
        src = source_dir / item
        dest = target_dir / item
        if not src.exists():
            continue
        try:
            _copy_item(src, dest)
            copied += 1
        except OSError:
            locked.append(item)

    # Essential session files — retry once; if still locked, keep going if we
    # already have a previous clone, otherwise fail with a clear message.
    essential = {"Cookies", "Login Data", "Local Storage", "Preferences"}
    missing_essential = [name for name in essential if not (target_dir / name).exists() and (source_dir / name).exists()]
    if missing_essential and not marker.exists():
        raise RuntimeError(
            "Could not copy Chrome login data while Chrome is using those files.\n\n"
            "Two options:\n"
            "1) Paths → Browser mode → Live (keeps your open Chrome; needs debug port), or\n"
            "2) Close Chrome once, Start again to create an isolated copy — after that "
            "your normal Chrome can stay open."
        )

    marker.write_text(
        json.dumps(
            {
                "source": str(source_dir),
                "clonedAt": __import__("datetime").datetime.utcnow().isoformat() + "Z",
                "copied": copied,
                "skippedLocked": locked,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return str(user_data_dir)


def tile_bounds(work_area: dict[str, int], index: int, count: int) -> dict[str, int]:
    """
    Side-by-side columns: each window gets full screen height and equal width.
    (Vertical splitters — not stacked top/bottom.)
    """
    count = max(count, 1)
    width = max(320, int(work_area["width"] // count))
    x = int(work_area["x"]) + index * width
    last = index == count - 1
    if last:
        width = int(work_area["x"]) + int(work_area["width"]) - x
    return {
        "x": x,
        "y": int(work_area["y"]),
        "width": width,
        "height": int(work_area["height"]),
    }


def cdp_available(port: int = DEFAULT_CDP_PORT) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1.2) as res:
            return res.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def chrome_process_running() -> bool:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        return "chrome.exe" in (result.stdout or "").lower()
    except Exception:
        return False


def ensure_live_debugging(
    executable_path: str,
    chrome_user_data_dir: str,
    port: int = DEFAULT_CDP_PORT,
) -> int:
    """
    Attach to an already-debuggable Chrome, or start Chrome with debugging
    when it is not running. Does not kill an existing normal Chrome session.
    """
    if cdp_available(port):
        return port

    if chrome_process_running():
        raise RuntimeError(
            "Your Chrome is already open without a debug port, so Greenhouse "
            "cannot drive those live windows.\n\n"
            "Keep using your open profiles with either:\n"
            "• Browser mode = Isolated (default): uses private copies; your "
            "normal Chrome stays open after the first sync, or\n"
            "• Close Chrome once, Start again — we'll reopen it with debugging "
            "for Live mode."
        )

    subprocess.Popen(
        [
            executable_path,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={chrome_user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-session-crashed-bubble",
            "--hide-crash-restore-bubble",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.time() + 20
    while time.time() < deadline:
        if cdp_available(port):
            return port
        time.sleep(0.35)

    raise RuntimeError(f"Chrome did not open debug port {port}.")


def launch_profile_browser(
    playwright,
    executable_path: str,
    user_data_dir: str,
    bounds: dict[str, int],
):
    """Isolated mode: one Playwright-owned Chrome per profile clone."""
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        executable_path=executable_path,
        headless=False,
        no_viewport=True,
        args=[
            f"--window-position={bounds['x']},{bounds['y']}",
            f"--window-size={bounds['width']},{bounds['height']}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-session-crashed-bubble",
            "--hide-crash-restore-bubble",
        ],
    )
    page = context.pages[0] if context.pages else context.new_page()
    return context, page, None


def launch_live_profile_browser(
    playwright,
    executable_path: str,
    chrome_user_data_dir: str,
    profile_number: int,
    bounds: dict[str, int],
    port: int = DEFAULT_CDP_PORT,
):
    """
    Live mode: open the real Chrome profile as a new window (other profiles stay open)
    and attach through CDP.
    """
    ensure_live_debugging(executable_path, chrome_user_data_dir, port)
    browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")

    before = set()
    for context in browser.contexts:
        for page in context.pages:
            before.add(id(page))

    profile_dir = chrome_directory_name(profile_number)
    subprocess.Popen(
        [
            executable_path,
            f"--profile-directory={profile_dir}",
            f"--window-position={bounds['x']},{bounds['y']}",
            f"--window-size={bounds['width']},{bounds['height']}",
            "--new-window",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    page = None
    deadline = time.time() + 15
    while time.time() < deadline and page is None:
        for context in browser.contexts:
            for candidate in context.pages:
                if id(candidate) in before:
                    continue
                page = candidate
                break
            if page:
                break
        time.sleep(0.25)

    if page is None:
        # Fall back to any page in the newest context
        if not browser.contexts:
            raise RuntimeError("Connected to Chrome but found no profile windows.")
        context = browser.contexts[-1]
        page = context.pages[-1] if context.pages else context.new_page()
    else:
        context = page.context

    try:
        # CDP cannot always resize foreign windows; best-effort via CDP.
        page.evaluate(
            """([x, y, w, h]) => {
                try { window.moveTo(x, y); window.resizeTo(w, h); } catch (e) {}
            }""",
            [bounds["x"], bounds["y"], bounds["width"], bounds["height"]],
        )
    except Exception:
        pass

    return context, page, browser


def focus_page(page, retries: int = 3) -> None:
    """Force a Playwright page/tab (and its Chrome window) to the front."""
    for attempt in range(max(1, retries)):
        try:
            page.bring_to_front()
        except Exception:
            pass
        try:
            cdp = page.context.new_cdp_session(page)
            try:
                cdp.send("Page.bringToFront")
            finally:
                try:
                    cdp.detach()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            page.evaluate(
                """() => {
                  try { window.focus(); } catch (e) {}
                  try { window.moveTo(window.screenX, window.screenY); } catch (e) {}
                }"""
            )
        except Exception:
            pass
        time.sleep(0.2 + attempt * 0.15)


def open_job_page(context, job_url: str, existing: dict | None = None):
    if existing and existing.get("greenhouse_page"):
        greenhouse_page = existing["greenhouse_page"]
    else:
        pages = list(context.pages)
        greenhouse_page = pages[0] if pages else context.new_page()

    greenhouse_page.goto(job_url, wait_until="domcontentloaded", timeout=120000)
    focus_page(greenhouse_page)
    return greenhouse_page


def open_deepseek_tab(context, existing: dict | None = None):
    if existing and existing.get("deepseek_page"):
        deepseek_page = existing["deepseek_page"]
    else:
        deepseek_page = context.new_page()

    deepseek_page.goto("https://chat.deepseek.com/", wait_until="domcontentloaded", timeout=120000)
    try:
        deepseek_page.wait_for_load_state("domcontentloaded", timeout=30000)
    except Exception:
        pass
    focus_page(deepseek_page)
    return deepseek_page


def open_job_and_chat(context, job_url: str, existing: dict | None = None):
    greenhouse_page = open_job_page(context, job_url, existing)
    deepseek_page = open_deepseek_tab(context, existing)
    return {"greenhouse_page": greenhouse_page, "deepseek_page": deepseek_page}
