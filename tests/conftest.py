"""Shared test setup.

`pytest-homeassistant-custom-component`'s `hass` fixture hardcodes its
config_dir to `<installed package>/testing_config`, regardless of where
pytest is actually run from - so a repo's own `custom_components/` isn't
found by Home Assistant's integration loader unless it's also reachable
from that fixed location. `pytest_configure` below makes it reachable by
symlinking this repo's `custom_components/lotto` into that location once
per test session.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPONENT_DIR = REPO_ROOT / "custom_components" / "lotto"


def pytest_configure(config: pytest.Config) -> None:
    import pytest_homeassistant_custom_component

    package_dir = Path(pytest_homeassistant_custom_component.__file__).resolve().parent
    target = package_dir / "testing_config" / "custom_components" / "lotto"
    target.parent.mkdir(parents=True, exist_ok=True)

    already_linked = target.is_symlink() and target.resolve() == COMPONENT_DIR.resolve()
    if not already_linked:
        if target.is_symlink() or target.exists():
            target.unlink()
        target.symlink_to(COMPONENT_DIR)

    # Only relevant when pytest runs against a Home Assistant older than
    # 2024.7 (StaticPathConfig's introduction); no-op on any current
    # install. panel.py needs it importable, but the actual call is mocked
    # out in tests (see test_integration.py) since the bare `hass` test
    # fixture doesn't set up the http component.
    import homeassistant.components.http as ha_http

    if not hasattr(ha_http, "StaticPathConfig"):

        class StaticPathConfig:
            def __init__(self, url_path, path, cache_headers=True):
                self.url_path = url_path
                self.path = path
                self.cache_headers = cache_headers

        ha_http.StaticPathConfig = StaticPathConfig


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


class FakeConnection:
    """Minimal stand-in for websocket_api.ActiveConnection."""

    def __init__(self) -> None:
        self.results: list = []
        self.errors: list = []

    def send_result(self, msg_id, result=None) -> None:
        self.results.append(result)

    def send_error(self, msg_id, code, message) -> None:
        self.errors.append((code, message))


@pytest.fixture
def ws_connection() -> FakeConnection:
    return FakeConnection()
