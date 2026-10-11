from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


def _extension_paths(extension_dir: str) -> dict[str, str]:
    folder = str(extension_dir or "").strip()
    if not folder:
        return {
            "extensionDir": "",
            "promptsDir": "",
            "profileContextDir": "",
            "profilesJsonPath": "",
        }
    root = Path(folder)
    return {
        "extensionDir": str(root),
        "promptsDir": str(root / "prompts"),
        "profileContextDir": str(root / "profile-context"),
        "profilesJsonPath": str(root / "profiles.json"),
    }


def default_settings() -> dict[str, Any]:
    chrome_user_data = Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data"
    settings = _extension_paths("")
    settings.update(
        {
            "chromeUserDataDir": str(chrome_user_data),
            "theme": "system",
            # isolated = private profile copies (normal Chrome can stay open after first sync)
            # live = drive real Chrome profiles via CDP (other profile windows stay open)
            "browserMode": "isolated",
            "chromeDebugPort": 9222,
            "resumeServerPort": 615,
        }
    )
    return settings


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

    ext_val = str(settings.get("extensionDir") or "").strip()
    if not ext_val:
        profiles_json = str(settings.get("profilesJsonPath") or "").strip()
        prompts_dir = str(settings.get("promptsDir") or "").strip()
        if profiles_json:
            ext_val = str(Path(profiles_json).parent)
        elif prompts_dir:
            ext_val = str(Path(prompts_dir).parent)
    merged.update(_extension_paths(ext_val))

    for obs in ("mainPyPath", "resumeOutputDir", "pythonPath"):
        merged.pop(obs, None)

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
        next_state["settings"].update(
            _extension_paths(str(next_state["settings"].get("extensionDir") or ""))
        )
        for obs in ("mainPyPath", "resumeOutputDir", "pythonPath"):
            next_state["settings"].pop(obs, None)

    user_data.mkdir(parents=True, exist_ok=True)
    _state_path(user_data).write_text(
        json.dumps(next_state, indent=2),
        encoding="utf-8",
    )
    return next_state
