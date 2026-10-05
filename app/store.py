from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

BID_ROOT = Path(r"D:\3.Work\Develop\bid")


def default_settings() -> dict[str, Any]:
    home = Path.home()
    chrome_user_data = home / "AppData" / "Local" / "Google" / "Chrome" / "User Data"
    venv_python = BID_ROOT / ".venv" / "Scripts" / "python.exe"
    return {
        "promptsDir": str(BID_ROOT / "extension-deepseek" / "prompts"),
        "profileContextDir": str(BID_ROOT / "extension-deepseek" / "profile-context"),
        "profilesJsonPath": str(BID_ROOT / "extension-deepseek" / "profiles.json"),
        "mainPyPath": str(BID_ROOT / "main.py"),
        "resumeOutputDir": str(BID_ROOT / "output"),
        "pythonPath": str(venv_python if venv_python.exists() else "python"),
        "chromeUserDataDir": str(chrome_user_data),
        "theme": "system",
        # isolated = private profile copies (normal Chrome can stay open after first sync)
        # live = drive real Chrome profiles via CDP (other profile windows stay open)
        "browserMode": "isolated",
        "chromeDebugPort": 9222,
    }


def _state_path(user_data: Path) -> Path:
    return user_data / "app-state.json"


def load_state(user_data: Path) -> dict[str, Any]:
    defaults = {
        "urls": [],
        "profiles": [],
        "settings": default_settings(),
    }
    path = _state_path(user_data)
    if not path.exists():
        return deepcopy(defaults)

    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return deepcopy(defaults)

    if not isinstance(parsed, dict):
        return deepcopy(defaults)

    state = deepcopy(defaults)
    state["urls"] = parsed.get("urls") if isinstance(parsed.get("urls"), list) else []
    state["profiles"] = (
        parsed.get("profiles") if isinstance(parsed.get("profiles"), list) else []
    )
    settings = parsed.get("settings") if isinstance(parsed.get("settings"), dict) else {}
    merged = default_settings()
    merged.update({k: v for k, v in settings.items() if isinstance(v, (str, int, float, bool))})
    state["settings"] = merged
    return state


def save_state(user_data: Path, partial: dict[str, Any]) -> dict[str, Any]:
    current = load_state(user_data)
    next_state = deepcopy(current)
    if "urls" in partial and isinstance(partial["urls"], list):
        next_state["urls"] = partial["urls"]
    if "profiles" in partial and isinstance(partial["profiles"], list):
        next_state["profiles"] = partial["profiles"]
    if "settings" in partial and isinstance(partial["settings"], dict):
        next_state["settings"].update(partial["settings"])

    user_data.mkdir(parents=True, exist_ok=True)
    _state_path(user_data).write_text(
        json.dumps(next_state, indent=2),
        encoding="utf-8",
    )
    return next_state
