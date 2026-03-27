from __future__ import annotations

import sys
import types

import pytest

from edown.auth import initialize_earth_engine
from edown.errors import AuthenticationError


def test_initialize_earth_engine_uses_service_account(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_service_account_credentials(service_account: str, key_path: str) -> tuple[str, str]:
        return (service_account, key_path)

    def fake_initialize(**kwargs):
        calls.append(kwargs)

    fake_ee = types.SimpleNamespace(
        ServiceAccountCredentials=fake_service_account_credentials,
        Initialize=fake_initialize,
    )
    monkeypatch.setitem(sys.modules, "ee", fake_ee)
    monkeypatch.setenv("GEE_SERVICE_ACCOUNT", "svc@example.com")
    monkeypatch.setenv("GEE_SERVICE_ACCOUNT_KEY", "/tmp/key.json")

    mode = initialize_earth_engine("https://earthengine-highvolume.googleapis.com")

    assert mode == "service-account"
    assert calls
    assert calls[0]["credentials"] == ("svc@example.com", "/tmp/key.json")


def test_initialize_earth_engine_falls_back_to_adc(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    class FakeCredentials:
        quota_project_id = "quota-project"

    def fake_initialize(**kwargs):
        calls.append(kwargs)
        if "credentials" not in kwargs:
            raise RuntimeError("no persistent ee credentials")

    fake_ee = types.SimpleNamespace(
        ServiceAccountCredentials=lambda *_args, **_kwargs: None,
        Initialize=fake_initialize,
    )
    monkeypatch.setitem(sys.modules, "ee", fake_ee)
    monkeypatch.delenv("GEE_SERVICE_ACCOUNT", raising=False)
    monkeypatch.delenv("GEE_SERVICE_ACCOUNT_KEY", raising=False)
    monkeypatch.setattr(
        "google.auth.default",
        lambda scopes: (FakeCredentials(), "adc-project"),
    )

    mode = initialize_earth_engine("https://earthengine-highvolume.googleapis.com")

    assert mode == "adc"
    assert calls[-1]["project"] == "adc-project"
    assert calls[-1]["credentials"].__class__.__name__ == "FakeCredentials"


def test_initialize_earth_engine_raises_when_all_auth_paths_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_initialize(**_kwargs):
        raise RuntimeError("bad auth")

    fake_ee = types.SimpleNamespace(
        ServiceAccountCredentials=lambda *_args, **_kwargs: None,
        Initialize=fake_initialize,
    )
    monkeypatch.setitem(sys.modules, "ee", fake_ee)
    monkeypatch.delenv("GEE_SERVICE_ACCOUNT", raising=False)
    monkeypatch.delenv("GEE_SERVICE_ACCOUNT_KEY", raising=False)
    monkeypatch.setattr(
        "google.auth.default",
        lambda scopes: (_ for _ in ()).throw(RuntimeError("bad adc")),
    )

    with pytest.raises(AuthenticationError):
        initialize_earth_engine("https://earthengine-highvolume.googleapis.com")
