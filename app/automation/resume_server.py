from __future__ import annotations

import json
import logging
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

DEFAULT_RESUME_PORT = 615


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _find_pdf_in_dir(directory: Path) -> Path | None:
    if not directory.exists() or not directory.is_dir():
        return None
    try:
        pdfs = list(directory.glob("*.pdf"))
    except OSError:
        return None
    if not pdfs:
        return None

    # Prefer a file containing "resume", excluding "cover"
    resumes = [p for p in pdfs if "resume" in p.stem.lower() and "cover" not in p.stem.lower()]
    if resumes:
        return resumes[0]

    # Exclude cover letter
    non_cover = [p for p in pdfs if "cover" not in p.stem.lower()]
    if non_cover:
        non_cover.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return non_cover[0]

    # Any pdf sorted by modification time
    pdfs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return pdfs[0]


def resolve_resume_location(payload: dict[str, Any]) -> str | None:
    """Extract resume file path from arbitrary notification payload."""
    if not isinstance(payload, dict):
        return None

    # 1. Direct path fields
    path_keys = [
        "exact_resume_location",
        "resume_path",
        "pdf_path",
        "path",
        "resume_file",
        "resume",
        "file",
    ]
    for key in path_keys:
        val = payload.get(key)
        if val and isinstance(val, str) and val.strip():
            cleaned = val.strip().strip('"').strip("'")
            p = Path(cleaned)
            if p.exists() and p.is_file():
                return str(p.resolve())
            if p.exists() and p.is_dir():
                found = _find_pdf_in_dir(p)
                if found:
                    return str(found.resolve())
            # Path might be currently being finalized by the generator
            if cleaned.lower().endswith(".pdf"):
                return str(p)

    # 2. Folder fields
    folder_keys = ["folder", "resume_folder", "directory", "dir"]
    for key in folder_keys:
        val = payload.get(key)
        if val and isinstance(val, str) and val.strip():
            cleaned = val.strip().strip('"').strip("'")
            p = Path(cleaned)
            if p.exists() and p.is_dir():
                found = _find_pdf_in_dir(p)
                if found:
                    return str(found.resolve())

    return None


class SafeHTTPServer(HTTPServer):
    # On Windows, allow_reuse_address allows multiple processes to bind to the
    # same port without an error, but packets only go to the first process.
    allow_reuse_address = False


def _notification_cache_file() -> Path:
    return Path(__file__).resolve().parents[2] / ".app-data" / "last_resume_notification.json"


class ResumeServerManager:
    """
    Manages the background HTTP server on localhost:615 to receive
    resume generation notifications.
    """

    def __init__(self, port: int = DEFAULT_RESUME_PORT):
        self.port = port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._notifications: list[dict[str, Any]] = []
        self._running = False

    def is_running(self) -> bool:
        with self._lock:
            return self._running and self._server is not None

    def start(self) -> bool:
        with self._lock:
            if self._running and self._server is not None:
                return True

            manager = self

            class ResumeHandler(BaseHTTPRequestHandler):
                def do_OPTIONS(self):
                    self.send_response(200)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                    self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, *")
                    self.end_headers()

                def do_GET(self):
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    resp = json.dumps(
                        {
                            "status": "ok",
                            "service": "greenhouse-resume-server",
                            "port": manager.port,
                            "pending": len([n for n in manager._notifications if not n.get("consumed")]),
                        }
                    )
                    self.wfile.write(resp.encode("utf-8"))

                def do_POST(self):
                    try:
                        content_len = int(self.headers.get("Content-Length") or 0)
                        body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
                        data = json.loads(body) if body.strip() else {}
                    except Exception as err:
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": f"Invalid JSON: {err}"}).encode("utf-8"))
                        return

                    resume_loc = manager.record_notification(data)

                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    resp = json.dumps(
                        {
                            "status": "success",
                            "ok": True,
                            "received": True,
                            "resume_location": resume_loc,
                        }
                    )
                    self.wfile.write(resp.encode("utf-8"))

                def log_message(self, format, *args):
                    # Silence default HTTP server console noise
                    pass

            # Try 0.0.0.0 first, then 127.0.0.1
            for host in ("0.0.0.0", "127.0.0.1"):
                try:
                    server = SafeHTTPServer((host, self.port), ResumeHandler)
                    self._server = server
                    self._running = True
                    break
                except OSError:
                    continue

            if not self._server:
                # Port might already be running in another instance
                logger.warning(
                    "Resume server could not bind to port %s (already in use).", self.port
                )
                return False

            self._thread = threading.Thread(
                target=self._server.serve_forever,
                name="ResumeNotificationServer",
                daemon=True,
            )
            self._thread.start()
            logger.info("Resume notification server listening on port %s", self.port)
            return True

    def stop(self) -> None:
        with self._lock:
            if self._server:
                try:
                    self._server.shutdown()
                    self._server.server_close()
                except Exception:
                    pass
                self._server = None
            self._running = False
            self._cond.notify_all()

    def record_notification(self, payload: dict[str, Any]) -> str | None:
        """Store incoming notification and wake up any waiting threads."""
        resume_loc = resolve_resume_location(payload)
        cover_path = payload.get("cover_letter_path") or payload.get("cover_letter")
        folder = payload.get("folder") or payload.get("directory")

        entry = {
            "received_at": time.time(),
            "payload": payload,
            "resume_path": resume_loc or "",
            "exact_resume_location": payload.get("exact_resume_location") or resume_loc or "",
            "cover_letter_path": str(cover_path).strip() if cover_path else None,
            "folder": str(folder).strip() if folder else None,
            "name": str(payload.get("name") or "").strip(),
            "company": str(payload.get("company") or "").strip(),
            "role": str(payload.get("role") or "").strip(),
            "status": str(payload.get("status") or "").strip(),
            "consumed": False,
        }

        with self._lock:
            self._notifications.append(entry)
            self._cond.notify_all()

        try:
            cache_file = _notification_cache_file()
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

        return resume_loc

    def _matches(
        self,
        item: dict[str, Any],
        name: str,
        company: str = "",
        role: str = "",
    ) -> bool:
        if item.get("consumed"):
            return False

        item_name = item.get("name") or ""
        item_company = item.get("company") or ""
        item_role = item.get("role") or ""

        # If item has a candidate name, verify it matches
        if item_name and name:
            norm_item = _norm(item_name)
            norm_target = _norm(name)
            if norm_item not in norm_target and norm_target not in norm_item:
                return False

        # If item has a company, verify company match
        if item_company and company:
            norm_item_co = _norm(item_company)
            norm_target_co = _norm(company)
            if norm_item_co not in norm_target_co and norm_target_co not in norm_item_co:
                return False

        # If item has a role, optional verification
        if item_role and role and not item_name and not item_company:
            norm_item_role = _norm(item_role)
            norm_target_role = _norm(role)
            if norm_item_role not in norm_target_role and norm_target_role not in norm_item_role:
                return False

        return bool(item.get("resume_path"))

    def wait_for_resume(
        self,
        name: str,
        company: str = "",
        role: str = "",
        started_at: float = 0,
        timeout_s: float = 300,
        on_status: Callable[[str], None] | None = None,
        stop_requested: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """
        Wait for a resume generation success notification for `name` / `company`.
        Returns the notification entry dict with `resume_path`, `cover_letter_path`, etc.
        """
        deadline = time.time() + timeout_s
        min_ts = max(0.0, (started_at or time.time()) - 15.0)

        if on_status:
            on_status(f"waiting for resume notification on localhost:{self.port}")

        while time.time() < deadline:
            if stop_requested and stop_requested():
                raise RuntimeError("Resume wait cancelled: stop requested")

            with self._lock:
                # Find matching unconsumed notification
                matched = None
                for n in reversed(self._notifications):
                    if n.get("received_at", 0) >= min_ts and self._matches(n, name, company, role):
                        matched = n
                        break

                # Fallback: if only one unconsumed notification arrived since started_at, take it
                if not matched:
                    unconsumed = [
                        n for n in self._notifications
                        if not n.get("consumed") and n.get("received_at", 0) >= min_ts and n.get("resume_path")
                    ]
                    if len(unconsumed) == 1:
                        matched = unconsumed[0]

                # Disk cache fallback (in case notification was handled across instances)
                if not matched:
                    try:
                        cf = _notification_cache_file()
                        if cf.exists():
                            item = json.loads(cf.read_text(encoding="utf-8"))
                            if (
                                isinstance(item, dict)
                                and not item.get("consumed")
                                and item.get("received_at", 0) >= min_ts
                                and (self._matches(item, name, company, role) or bool(item.get("resume_path")))
                            ):
                                matched = item
                                item["consumed"] = True
                                cf.write_text(json.dumps(item, indent=2), encoding="utf-8")
                    except Exception:
                        pass

                if matched:
                    matched["consumed"] = True
                    resume_path = matched["resume_path"]

                    # Check if file exists, wait briefly if it's currently being written
                    p = Path(resume_path)
                    wait_disk = time.time()
                    while not p.exists() and time.time() - wait_disk < 5.0:
                        time.sleep(0.2)

                    return matched

                self._cond.wait(timeout=1.0)

        raise TimeoutError(
            f'Timed out waiting for resume notification for "{name}" ({company}) '
            f"on localhost:{self.port} after {int(timeout_s)}s"
        )


# Global singleton instance
_GLOBAL_RESUME_SERVER = ResumeServerManager(port=DEFAULT_RESUME_PORT)


def get_resume_server() -> ResumeServerManager:
    return _GLOBAL_RESUME_SERVER


def start_resume_server(port: int = DEFAULT_RESUME_PORT) -> bool:
    global _GLOBAL_RESUME_SERVER
    if _GLOBAL_RESUME_SERVER.port != port:
        _GLOBAL_RESUME_SERVER.stop()
        _GLOBAL_RESUME_SERVER = ResumeServerManager(port=port)
    return _GLOBAL_RESUME_SERVER.start()


def stop_resume_server() -> None:
    _GLOBAL_RESUME_SERVER.stop()


def wait_for_resume_notification(
    name: str,
    company: str = "",
    role: str = "",
    started_at: float = 0,
    timeout_s: float = 300,
    on_status: Callable[[str], None] | None = None,
    stop_requested: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    start_resume_server()
    return _GLOBAL_RESUME_SERVER.wait_for_resume(
        name=name,
        company=company,
        role=role,
        started_at=started_at,
        timeout_s=timeout_s,
        on_status=on_status,
        stop_requested=stop_requested,
    )
