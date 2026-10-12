from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _history_path(user_data: Path) -> Path:
    return user_data / "bid-history.json"


def load_bids(user_data: Path) -> list[dict[str, Any]]:
    path = _history_path(user_data)
    if not path.exists():
        return []
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    bids = parsed.get("bids") if isinstance(parsed, dict) else None
    if not isinstance(bids, list):
        return []
    return [item for item in bids if isinstance(item, dict) and item.get("url")]


def record_bids(
    user_data: Path,
    profile_id: str,
    profile_name: str,
    jobs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep the latest status for each profile and URL. Survives app restarts."""
    bids = load_bids(user_data)
    index = {
        (str(item.get("profileId") or ""), str(item.get("url") or "")): item
        for item in bids
    }
    now = datetime.now().isoformat(timespec="seconds")
    for job in jobs:
        url = str(job.get("url") or "").strip()
        if not url:
            continue
        key = (str(profile_id), url)
        current = index.get(key)
        state = str(job.get("state") or "queued")
        error = str(job.get("error") or "").strip()
        if current is None:
            current = {
                "profileId": str(profile_id),
                "profileName": profile_name or "Unnamed",
                "url": url,
                "state": state,
                "error": error,
                "startedAt": now,
                "updatedAt": now,
            }
            bids.append(current)
            index[key] = current
            continue
        current["profileName"] = profile_name or current.get("profileName") or "Unnamed"
        current["state"] = state
        current["error"] = error
        current["updatedAt"] = now

    path = _history_path(user_data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"bids": bids}, indent=2), encoding="utf-8")
    return bids
