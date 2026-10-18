"""Watermark password storage: OS keyring first, data-folder fallback."""
from __future__ import annotations

from pathlib import Path

from .storage import Store

SERVICE = "SigWatermark"
ACCOUNT = "watermark-password"


def _keyring():
    try:
        import keyring
        from keyring.backends.fail import Keyring as FailKeyring
        kr = keyring.get_keyring()
        if isinstance(kr, FailKeyring) or "fail" in type(kr).__module__ or "null" in type(kr).__module__:
            return None
        return keyring
    except Exception:  # noqa: BLE001 - any backend error means "no keyring"
        return None


def keyring_available() -> bool:
    return _keyring() is not None


def get_password(store: Store) -> str:
    kr = _keyring()
    if kr is not None:
        try:
            v = kr.get_password(SERVICE, f"{ACCOUNT}:{store.root}")
            if v:
                return v
        except Exception:  # noqa: BLE001
            pass
    return store.settings.password_fallback or ""


def set_password(store: Store, password: str) -> str:
    """Returns where it was stored: 'keyring' or 'file'."""
    kr = _keyring()
    if kr is not None:
        try:
            kr.set_password(SERVICE, f"{ACCOUNT}:{store.root}", password)
            if store.settings.password_fallback:
                store.settings.password_fallback = ""
                store.save_settings()
            return "keyring"
        except Exception:  # noqa: BLE001
            pass
    store.settings.password_fallback = password
    store.save_settings()
    return "file"


def legacy_env_password(folder: Path) -> str:
    """WATERMARK_PASSWORD from the old script's .env, if one sits next to the program."""
    env = folder / ".env"
    if not env.exists():
        return ""
    for raw in env.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if line.startswith("WATERMARK_PASSWORD") and "=" in line:
            v = line.split("=", 1)[1].strip().strip("'\"")
            if v and not v.startswith("CHANGE_THIS"):
                return v
    return ""
