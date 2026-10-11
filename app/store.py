from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

BID_ROOT = Path(r"D:\3.Work\Develop\bid")


def default_settings() -> dict[str, Any]:
    home = Path.home()
    chrome_user_data = home / "AppData" / "Local" / "Google" / "Chrome" / "User Data"
    ext_dir = BID_ROOT / "extension-deepseek"
    return {
        "extensionDir": str(ext_dir),
        "promptsDir": str(ext_dir / "prompts"),
        "profileContextDir": str(ext_dir / "profile-context"),
        "profilesJsonPath": str(ext_dir / "profiles.json"),
        "chromeUserDataDir": str(chrome_user_data),
        "theme": "system",
        # isolated = private profile copies (normal Chrome can stay open after first sync)
        # live = drive real Chrome profiles via CDP (other profile windows stay open)
        "browserMode": "isolated",
        "chromeDebugPort": 9222,
        "resumeServerPort": 615,
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

    ext_val = settings.get("extensionDir") or merged.get("extensionDir")
    if not ext_val or ext_val == str(BID_ROOT / "extension-deepseek"):
        if settings.get("profilesJsonPath"):
            ext_val = str(Path(settings["profilesJsonPath"]).parent)
        elif settings.get("promptsDir"):
            ext_val = str(Path(settings["promptsDir"]).parent)
        elif not ext_val:
            ext_val = str(BID_ROOT / "extension-deepseek")
    merged["extensionDir"] = ext_val

    ext_p = Path(merged["extensionDir"])
    merged["promptsDir"] = str(ext_p / "prompts")
    merged["profileContextDir"] = str(ext_p / "profile-context")
    merged["profilesJsonPath"] = str(ext_p / "profiles.json")

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
        ext_val = next_state["settings"].get("extensionDir")
        if ext_val:
            ext_p = Path(ext_val)
            next_state["settings"]["promptsDir"] = str(ext_p / "prompts")
            next_state["settings"]["profileContextDir"] = str(ext_p / "profile-context")
            next_state["settings"]["profilesJsonPath"] = str(ext_p / "profiles.json")
        for obs in ("mainPyPath", "resumeOutputDir", "pythonPath"):
            next_state["settings"].pop(obs, None)

    user_data.mkdir(parents=True, exist_ok=True)
    _state_path(user_data).write_text(
        json.dumps(next_state, indent=2),
        encoding="utf-8",
    )
    return next_state
