from __future__ import annotations

import json
import time
from typing import Any, Callable

from app.automation.deepseek import copy_resume_to_clipboard
from app.automation.resume_server import (
    start_resume_server,
    wait_for_resume_notification,
)


class ResumeBridge:
    """
    DeepSeek JSON is copied to the clipboard. An external exporter builds the PDF
    and posts a success notification; this bridge returns that PDF path.
    """

    def __init__(self, settings: dict[str, Any]):
        self.settings = settings

    def generate(
        self,
        profile_name: str,
        payload: dict[str, Any] | None,
        raw_text: str = "",
        company: str = "",
        role: str = "",
        started_at: float | None = None,
        on_status: Callable[[str], None] | None = None,
        timeout_ms: int = 300000,
        stop_requested: Callable[[], bool] | None = None,
    ) -> str:
        port = int(self.settings.get("resumeServerPort") or 615)
        start_resume_server(port)

        started = started_at or time.time()
        company = company or str((payload or {}).get("target_company") or "").strip()
        if not company:
            company = ((payload or {}).get("target") or {}).get("company") or ""
        role = role or str((payload or {}).get("target_role") or "").strip()
        if not role:
            role = ((payload or {}).get("target") or {}).get("role") or ""

        text = raw_text
        if payload is not None:
            text = json.dumps(payload, indent=2, ensure_ascii=False)
        if text:
            copy_resume_to_clipboard(text)

        if on_status:
            on_status(f"waiting for resume from exporter tool on localhost:{port}")

        notif = wait_for_resume_notification(
            name=profile_name,
            company=company,
            role=role,
            started_at=started,
            timeout_s=max(10.0, timeout_ms / 1000.0),
            on_status=on_status,
            stop_requested=stop_requested,
        )

        resume_path = notif.get("resume_path") or ""
        if resume_path:
            return resume_path

        raise RuntimeError(
            f'Exporter notification on localhost:{port} did not include a resume path for "{profile_name}".'
        )

    def stop(self) -> None:
        return None
