from __future__ import annotations

import json
import uuid
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


def empty_imap() -> dict[str, Any]:
    return {
        "preset": "outlook",
        "host": "outlook.office365.com",
        "port": 993,
        "user": "",
        "password": "",
        "auth": "oauth",
    }


def new_profile() -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "name": "",
        "chromeProfileNumber": 0,
        "chromeDisplayName": "Default",
        "active": False,
        "imap": empty_imap(),
    }


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_profile(raw: Any) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    imap_raw = source.get("imap") if isinstance(source.get("imap"), dict) else {}
    imap = empty_imap()
    preset = str(imap_raw.get("preset") or imap["preset"]).strip().lower() or "outlook"
    imap["preset"] = preset
    imap["host"] = str(imap_raw.get("host") or imap["host"]).strip() or imap["host"]
    imap["port"] = _as_int(imap_raw.get("port"), 993) or 993
    imap["user"] = str(imap_raw.get("user") or "").strip()
    imap["password"] = str(imap_raw.get("password") or "")
    imap["auth"] = str(imap_raw.get("auth") or "oauth").strip() or "oauth"

    if "active" in source:
        active = bool(source.get("active"))
    else:
        # Older builds used one checkbox for both ready and include-in-run.
        active = bool(source.get("selected", True))

    number = _as_int(source.get("chromeProfileNumber"), 0)
    display = str(source.get("chromeDisplayName") or "").strip()
    if not display:
        display = "Default" if number == 0 else f"Profile {number}"

    return {
        "id": str(source.get("id") or uuid.uuid4()),
        "name": str(source.get("name") or ""),
        "chromeProfileNumber": number,
        "chromeDisplayName": display,
        "active": active,
        "imap": imap,
    }


def normalize_url(raw: Any) -> dict[str, str] | None:
    if isinstance(raw, str):
        url = raw.strip()
        if not url:
            return None
        return {"id": str(uuid.uuid4()), "url": url}
    if not isinstance(raw, dict):
        return None
    url = str(raw.get("url") or "").strip()
    if not url:
        return None
    return {"id": str(raw.get("id") or uuid.uuid4()), "url": url}


def _normalize_id_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _state_path(user_data: Path) -> Path:
    return user_data / "app-state.json"


def load_state(user_data: Path) -> dict[str, Any]:
    defaults = {
        "urls": [],
        "profiles": [],
        "selectedProfileIds": [],
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

    raw_profiles = parsed.get("profiles") if isinstance(parsed.get("profiles"), list) else []
    profiles: list[dict[str, Any]] = []
    legacy_selected: list[str] = []
    for raw in raw_profiles:
        profile = normalize_profile(raw)
        profiles.append(profile)
        if isinstance(raw, dict) and bool(raw.get("selected", False)):
            legacy_selected.append(profile["id"])

    selected = _normalize_id_list(parsed.get("selectedProfileIds"))
    if not selected and legacy_selected:
        selected = legacy_selected
    if not selected:
        selected = [str(p["id"]) for p in profiles if p.get("active")]

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

    # Fresh job session every launch: never restore URLs or run progress.
    return {
        "urls": [],
        "profiles": profiles,
        "selectedProfileIds": selected,
        "settings": merged,
    }


def save_state(user_data: Path, partial: dict[str, Any]) -> dict[str, Any]:
    current = load_state(user_data)
    next_state = deepcopy(current)

    if "profiles" in partial and isinstance(partial["profiles"], list):
        next_state["profiles"] = [normalize_profile(item) for item in partial["profiles"]]
    if "selectedProfileIds" in partial:
        next_state["selectedProfileIds"] = _normalize_id_list(partial["selectedProfileIds"])
    if "urls" in partial and isinstance(partial["urls"], list):
        # Persist for this session on disk if needed, but load_state clears them.
        urls: list[dict[str, str]] = []
        for item in partial["urls"]:
            normalized = normalize_url(item)
            if normalized:
                urls.append(normalized)
        next_state["urls"] = urls
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


def active_profiles(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [profile for profile in state.get("profiles") or [] if profile.get("active")]


def checked_profiles(state: dict[str, Any]) -> list[dict[str, Any]]:
    selected = {str(item) for item in state.get("selectedProfileIds") or []}
    return [
        profile
        for profile in active_profiles(state)
        if str(profile.get("id") or "") in selected
    ]
