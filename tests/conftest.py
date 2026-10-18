import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sigwm import secret  # noqa: E402

PASSWORD = "example-only-pass-2026"
FIXTURE = Path(__file__).parent / "fixtures" / "signature.png"


@pytest.fixture(autouse=True)
def no_keyring(monkeypatch):
    # Tests must never read or write the developer's real OS keyring.
    monkeypatch.setattr(secret, "_keyring", lambda: None)


@pytest.fixture
def store(tmp_path):
    from sigwm.storage import Store
    s = Store(tmp_path / "data", True)
    yield s
    s.close()


@pytest.fixture
def signed(store):
    """Store with three records, one per translucent mode."""
    from sigwm import core, service
    outs = []
    for mode in ("translucent", "feathered", "feathered_texture"):
        o = service.embed_file(store, FIXTURE, PASSWORD, core.CarrierParams(mode=mode), "test")
        assert o.ok, o.error
        outs.append(o)
    return store, outs
