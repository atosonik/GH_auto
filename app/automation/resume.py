from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

import pyperclip

# Serialize resume builds — Word/COM + clipboard cannot run safely in parallel.
_GENERATE_LOCK = threading.Lock()


class ResumeBridge:
    def __init__(self, settings: dict[str, Any]):
        self.settings = settings
        self._lock = threading.Lock()
        self.child: subprocess.Popen | None = None

    def ensure_watcher(self) -> None:
        with self._lock:
            if self.is_main_py_running():
                return

            main_py = Path(self.settings.get("mainPyPath") or "")
            if not main_py.exists():
                raise FileNotFoundError(f"main.py not found at {main_py}")

            python = self.settings.get("pythonPath") or "python"
            env = os.environ.copy()
            env["RESUME_WATCH_CLIPBOARD"] = "1"
            env["RESUME_OPEN_PDF"] = "0"
            if self.settings.get("resumeOutputDir"):
                env["RESUME_OUTPUT_DIR"] = str(self.settings["resumeOutputDir"])

            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self.child = subprocess.Popen(
                [str(python), str(main_py)],
                cwd=str(main_py.parent),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            time.sleep(1.2)

    def is_main_py_running(self) -> bool:
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                check=False,
            )
            text = (result.stdout or "").lower()
            return "main.py" in text or bool(self.child and self.child.poll() is None)
        except Exception:
            return bool(self.child and self.child.poll() is None)

    def output_root(self) -> Path:
        return Path(self.settings.get("resumeOutputDir") or ".")

    def list_pdfs(self, profile_name: str) -> list[dict[str, Any]]:
        root = self.output_root() / profile_name
        found: list[dict[str, Any]] = []
        if not root.exists():
            return found
        for path in root.rglob("*.pdf"):
            try:
                found.append(
                    {
                        "path": str(path),
                        "mtimeMs": path.stat().st_mtime * 1000,
                        "companyHint": path.parent.name,
                    }
                )
            except OSError:
                continue
        found.sort(key=lambda item: item["mtimeMs"], reverse=True)
        return found

    def find_resume_pdf(
        self,
        profile_name: str,
        company: str = "",
        after_ts: float | None = None,
    ) -> str | None:
        """
        Pick the best PDF for this run using company folder hint + timestamp.
        Output layout: <name>/<YYYY_MM_DD>/<HH_MM_SS>_<company>/<name>.pdf
        """
        company_key = re.sub(r"[^a-z0-9]+", "", (company or "").lower())
        after_ms = (after_ts or 0) * 1000
        candidates = self.list_pdfs(profile_name)
        if after_ms:
            candidates = [c for c in candidates if c["mtimeMs"] >= after_ms - 2000]

        if company_key:
            matched = [
                c
                for c in candidates
                if company_key in re.sub(r"[^a-z0-9]+", "", (c.get("companyHint") or "").lower())
                or company_key in re.sub(r"[^a-z0-9]+", "", Path(c["path"]).stem.lower())
            ]
            if matched:
                return matched[0]["path"]

        return candidates[0]["path"] if candidates else None

    def generate(
        self,
        profile_name: str,
        payload: dict[str, Any] | None,
        raw_text: str = "",
        company: str = "",
        on_status: Callable[[str], None] | None = None,
        timeout_ms: int = 240000,
    ) -> str:
        """
        Build a PDF without fighting over the clipboard across profiles.
        Uses a subprocess call into bid/main.py.generate_resume when possible.
        """
        if on_status:
            on_status("generating resume")

        started = time.time()
        company = company or ((payload or {}).get("target") or {}).get("company") or ""

        last_error = ""
        with _GENERATE_LOCK:
            try:
                pdf = self._generate_direct(payload, raw_text, timeout_ms=timeout_ms)
            except Exception as error:
                last_error = str(error)
                pdf = None
            if pdf and Path(pdf).exists():
                return pdf

            # Clipboard fallback (serialized by the same lock).
            if on_status:
                on_status("waiting for resume")
            text = raw_text
            if payload is not None:
                text = json.dumps(payload, indent=2, ensure_ascii=False)
            try:
                pdf = self.copy_and_wait(
                    profile_name,
                    text,
                    timeout_ms=min(timeout_ms, 180000),
                    on_status=on_status,
                )
            except Exception as error:
                detail = last_error or str(error)
                raise RuntimeError(
                    f'Could not generate resume PDF for "{profile_name}". {detail}'
                ) from error

        matched = self.find_resume_pdf(profile_name, company=company, after_ts=started)
        return matched or pdf

    def _generate_direct(
        self,
        payload: dict[str, Any] | None,
        raw_text: str,
        timeout_ms: int = 240000,
    ) -> str | None:
        main_py = Path(self.settings.get("mainPyPath") or "")
        if not main_py.exists():
            raise FileNotFoundError(f"main.py not found at {main_py}")

        python = self.settings.get("pythonPath") or "python"
        data = payload
        if data is None and raw_text.strip():
            try:
                data = json.loads(raw_text)
            except Exception:
                # Leave repair to main.py via a tiny wrapper that uses repair_json.
                data = None

        # Unwrap accidental parse_resume_json wrapper if it leaked through.
        if isinstance(data, dict) and "parsed" in data and "name" not in data:
            inner = data.get("parsed")
            if isinstance(inner, dict):
                data = inner

        with tempfile.TemporaryDirectory(prefix="gh_resume_") as tmp:
            tmp_path = Path(tmp)
            payload_path = tmp_path / "payload.json"
            out_path = tmp_path / "result.json"
            err_path = tmp_path / "error.txt"
            if data is not None:
                payload_path.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
                )
            else:
                payload_path.write_text(raw_text, encoding="utf-8")

            script = f"""
import json, sys, traceback
from pathlib import Path
sys.path.insert(0, r"{main_py.parent}")
import main as resume_main

err_path = Path(r"{err_path}")
try:
    raw = Path(r"{payload_path}").read_text(encoding="utf-8")
    data = None
    try:
        data = json.loads(raw)
    except Exception:
        repaired, _ = resume_main.repair_json(raw)
        data = json.loads(repaired)

    if isinstance(data, dict) and "parsed" in data and "name" not in data:
        inner = data.get("parsed")
        if isinstance(inner, dict):
            data = inner

    if isinstance(data, dict) and not (data.get("target") or {{}}).get("company"):
        data.setdefault("target", {{}})

    pdf = resume_main.generate_resume(data)
    Path(r"{out_path}").write_text(json.dumps({{"pdf": str(pdf)}}), encoding="utf-8")
    print(pdf)
except Exception as exc:
    err_path.write_text(f"{{exc}}\\n{{traceback.format_exc()}}", encoding="utf-8")
    raise
"""
            env = os.environ.copy()
            if self.settings.get("resumeOutputDir"):
                env["RESUME_OUTPUT_DIR"] = str(self.settings["resumeOutputDir"])
            env["RESUME_OPEN_PDF"] = "0"
            env["RESUME_WATCH_CLIPBOARD"] = "0"

            try:
                result = subprocess.run(
                    [str(python), "-c", script],
                    cwd=str(main_py.parent),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=timeout_ms / 1000.0,
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                raise TimeoutError(
                    f"generate_resume timed out after {timeout_ms / 1000:.0f}s"
                ) from error

            if out_path.exists():
                try:
                    pdf = json.loads(out_path.read_text(encoding="utf-8")).get("pdf")
                    if pdf and Path(pdf).exists():
                        return pdf
                except Exception:
                    pass

            line = (result.stdout or "").strip().splitlines()
            if line and line[-1].lower().endswith(".pdf") and Path(line[-1]).exists():
                return line[-1]

            detail = ""
            if err_path.exists():
                detail = err_path.read_text(encoding="utf-8").strip().splitlines()[0]
            elif result.stderr:
                detail = (result.stderr or "").strip().splitlines()[-1]
            raise RuntimeError(detail or "generate_resume failed with no PDF output")

    def copy_and_wait(
        self,
        profile_name: str,
        payload_text: str,
        timeout_ms: int = 180000,
        on_status: Callable[[str], None] | None = None,
    ) -> str:
        self.ensure_watcher()
        before = {item["path"] for item in self.list_pdfs(profile_name)}
        # Nudge clipboard so identical payloads still trigger the watcher.
        pyperclip.copy(" ")
        time.sleep(0.4)
        pyperclip.copy(payload_text)
        if on_status:
            on_status("waiting for resume")

        deadline = time.time() + (timeout_ms / 1000.0)
        while time.time() < deadline:
            for item in self.list_pdfs(profile_name):
                if item["path"] not in before:
                    return item["path"]
            time.sleep(0.8)

        raise TimeoutError(
            f"Timed out waiting for resume PDF for {profile_name}. Is main.py watching the clipboard?"
        )

    def stop(self) -> None:
        with self._lock:
            if self.child and self.child.poll() is None:
                self.child.terminate()
            self.child = None
