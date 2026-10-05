from __future__ import annotations

import json
import re
from typing import Any

_CONTROL = {
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\b": "\\b",
    "\f": "\\f",
}


def _next_is_close(text: str, i: int) -> bool:
    while i < len(text) and text[i].isspace():
        i += 1
    return i < len(text) and text[i] in "}]"


def _closes_string(text: str, pos: int) -> bool:
    j = pos + 1
    while j < len(text) and text[j].isspace():
        j += 1
    if j >= len(text):
        return True
    return text[j] in ",:}]"


def repair_json(text: str) -> tuple[str, int]:
    """Best-effort repair of LLM resume JSON (trailing commas, bad escapes, etc.)."""
    out: list[str] = []
    i = 0
    in_string = False
    repairs = 0

    while i < len(text):
        ch = text[i]

        if not in_string:
            if ch == "," and _next_is_close(text, i + 1):
                repairs += 1
                i += 1
                continue
            out.append(ch)
            if ch == '"':
                in_string = True
            i += 1
            continue

        if ch == "\\":
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if nxt in '"\\/bfnrt':
                out.append(text[i : i + 2])
                i += 2
                continue
            if nxt == "u" and re.fullmatch(r"[0-9a-fA-F]{4}", text[i + 2 : i + 6] or ""):
                out.append(text[i : i + 6])
                i += 6
                continue
            out.append(nxt)
            repairs += 1
            i += 2
            continue

        if ch == '"':
            if _closes_string(text, i):
                in_string = False
                out.append(ch)
            else:
                out.append('\\"')
                repairs += 1
            i += 1
            continue

        if ch < " ":
            out.append(_CONTROL.get(ch) or "\\u%04x" % ord(ch))
            repairs += 1
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out), repairs


def looks_like_resume(text: str) -> bool:
    return bool(
        re.search(r'"name"\s*:', text or "", re.I)
        and re.search(r'"experience"\s*:', text or "", re.I)
    )


def parse_resume_json(text: str) -> dict[str, Any] | None:
    if not text or not text.strip():
        return None

    candidates: list[str] = []
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        candidates.append(fenced.group(1).strip())

    i = 0
    body = text
    while i < len(body):
        open_at = body.find("{", i)
        if open_at < 0:
            break
        depth = 0
        in_string = False
        escaped = False
        closed = -1
        for j in range(open_at, len(body)):
            ch = body[j]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    closed = j
                    break
        if closed < 0:
            # Unbalanced "{" (often UI chrome) — skip it and keep scanning.
            i = open_at + 1
            continue
        candidates.append(body[open_at : closed + 1])
        i = closed + 1

    # Prefer largest resume-shaped candidate.
    shaped = [c for c in candidates if looks_like_resume(c)]
    ordered = sorted(shaped or candidates, key=len, reverse=True)

    for candidate in ordered:
        for attempt in (candidate, repair_json(candidate)[0]):
            try:
                parsed = json.loads(attempt)
            except Exception:
                continue
            if isinstance(parsed, dict) and parsed.get("name") and (
                parsed.get("experience") is not None or parsed.get("summary")
            ):
                return {"raw": attempt, "parsed": parsed, "source": candidate}

    if shaped:
        repaired, _ = repair_json(shaped[0])
        try:
            parsed = json.loads(repaired)
            if isinstance(parsed, dict) and parsed.get("name"):
                return {"raw": repaired, "parsed": parsed, "source": shaped[0]}
        except Exception:
            pass
        return {"raw": repaired, "parsed": None, "source": shaped[0]}

    return None
