"""Tests for the weather provider factory."""

from __future__ import annotations

import pytest

from magma_cycling_tools.weather.factory import (
    DEFAULT_PROVIDER,
    PROVIDER_ENV_VAR,
    UnknownProviderError,
    get_weather_provider,
)
from magma_cycling_tools.weather.providers.meteofrance_community import (
    MeteofranceCommunityProvider,
)
from magma_cycling_tools.weather.providers.meteofrance_official import (
    MeteofranceOfficialProvider,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(PROVIDER_ENV_VAR, raising=False)


class TestProviderResolution:
    def test_default_is_meteofrance_community(self) -> None:
        provider = get_weather_provider()
        assert isinstance(provider, MeteofranceCommunityProvider)
        assert provider.provider_name == DEFAULT_PROVIDER

    def test_env_var_overrides_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PROVIDER_ENV_VAR, "meteofrance_official")
        provider = get_weather_provider()
        assert isinstance(provider, MeteofranceOfficialProvider)

    def test_explicit_name_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PROVIDER_ENV_VAR, "meteofrance_official")
        provider = get_weather_provider(name="meteofrance_community")
        assert isinstance(provider, MeteofranceCommunityProvider)

    def test_unknown_raises(self) -> None:
        with pytest.raises(UnknownProviderError, match="Unknown weather provider"):
            get_weather_provider(name="not_a_real_provider")

    def test_whitespace_in_env_is_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PROVIDER_ENV_VAR, "  meteofrance_community  ")
        provider = get_weather_provider()
        assert isinstance(provider, MeteofranceCommunityProvider)


class TestStubBehavior:
    def test_official_stub_get_forecast_raises(self) -> None:
        from datetime import datetime, timezone

        provider = MeteofranceOfficialProvider()
        with pytest.raises(NotImplementedError):
            provider.get_forecast_point(0, 0, datetime.now(tz=timezone.utc))

    def test_official_stub_get_rain_raises(self) -> None:
        provider = MeteofranceOfficialProvider()
        with pytest.raises(NotImplementedError):
            provider.get_rain_next_hour(0, 0)

    def test_official_stub_get_vigilance_raises(self) -> None:
        provider = MeteofranceOfficialProvider()
        with pytest.raises(NotImplementedError):
            provider.get_vigilance("63")

    def test_official_stub_provider_name(self) -> None:
        assert MeteofranceOfficialProvider().provider_name == "meteofrance_official"
