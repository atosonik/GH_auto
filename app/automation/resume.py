from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from app.automation.deepseek import copy_resume_to_clipboard
from app.automation.resume_server import (
    start_resume_server,
    wait_for_resume_notification,
)

logger = logging.getLogger(__name__)


class ResumeBridge:
    """
    Bridge that coordinates resume PDF generation with an external exporter tool.
    DeepSeek outputs the resume JSON -> valid JSON is copied to the clipboard ->
    the external exporter tool generates the PDF and sends a success notification
    to http://localhost:615/notify -> this bridge returns the received PDF location.
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
        company = company or ((payload or {}).get("target") or {}).get("company") or ""
        role = role or ((payload or {}).get("target") or {}).get("role") or ""

        # Make sure the clipboard contains the full JSON for the external exporter tool
        text = raw_text
        if payload is not None:
            text = json.dumps(payload, indent=2, ensure_ascii=False)
        if text:
            copy_resume_to_clipboard(text)

        if on_status:
            on_status(f"waiting for resume from exporter tool on localhost:{port}")

        # Wait for the external exporter tool to POST success notification to localhost:615
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
            f'Exporter tool notification on localhost:{port} did not specify a valid resume location for "{profile_name}".'
        )

    def stop(self) -> None:
        pass
