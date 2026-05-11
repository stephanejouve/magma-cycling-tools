"""Tests for the community Météo-France provider (no real network)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from magma_cycling_tools.weather.models import (
    RainIntensity,
    VigilanceColor,
    VigilancePhenomenonType,
)
from magma_cycling_tools.weather.providers.meteofrance_community import (
    MeteofranceCommunityProvider,
)


def _make_provider(client: MagicMock) -> MeteofranceCommunityProvider:
    return MeteofranceCommunityProvider(client=client)


class TestGetForecastPoint:
    def test_picks_nearest_entry(self, mf_forecast_chas: dict[str, Any]) -> None:
        client = MagicMock()
        forecast_obj = MagicMock()
        forecast_obj.forecast = mf_forecast_chas["forecast"]
        client.get_forecast.return_value = forecast_obj

        provider = _make_provider(client)
        # target = 1778508000 → second entry (exact match)
        when = datetime.fromtimestamp(1778508000, tz=UTC)
        fp = provider.get_forecast_point(45.69, 3.34, when)

        assert fp.temperature_c == 18.1
        assert fp.weather_description_fr == "Ciel voile"
        # wind speed lib m/s → our model km/h: 5.0 * 3.6 = 18.0
        assert fp.wind_speed_kmh == pytest.approx(18.0)
        assert fp.wind_direction_deg == 250.0
        assert fp.valid_at.tzinfo is not None
        client.get_forecast.assert_called_once_with(latitude=45.69, longitude=3.34)

    def test_naive_when_rejected(self) -> None:
        provider = _make_provider(MagicMock())
        with pytest.raises(ValueError, match="timezone-aware"):
            provider.get_forecast_point(0, 0, datetime(2026, 5, 11, 14, 0))

    def test_empty_forecast_raises(self) -> None:
        client = MagicMock()
        forecast_obj = MagicMock()
        forecast_obj.forecast = []
        client.get_forecast.return_value = forecast_obj
        provider = _make_provider(client)
        with pytest.raises(RuntimeError, match="no hourly forecast"):
            provider.get_forecast_point(0, 0, datetime.now(tz=UTC))

    def test_missing_subdicts_default_safely(self) -> None:
        client = MagicMock()
        forecast_obj = MagicMock()
        forecast_obj.forecast = [{"dt": 1778508000}]
        client.get_forecast.return_value = forecast_obj
        provider = _make_provider(client)
        fp = provider.get_forecast_point(0, 0, datetime.fromtimestamp(1778508000, tz=UTC))
        assert fp.temperature_c == 0.0
        assert fp.weather_description_fr == ""
        assert fp.wind_direction_deg == 0


class TestGetRainNextHour:
    def test_maps_intensity_codes(self, mf_rain_1h_chas: dict[str, Any]) -> None:
        client = MagicMock()
        rain_obj = MagicMock()
        rain_obj.forecast = mf_rain_1h_chas["forecast"]
        rain_obj.updated_on = mf_rain_1h_chas["updated_on"]
        client.get_rain.return_value = rain_obj
        provider = _make_provider(client)
        rain = provider.get_rain_next_hour(45.69, 3.34)
        assert len(rain.slots) == 12
        assert rain.slots[0].intensity == RainIntensity.SEC
        assert rain.slots[2].intensity == RainIntensity.PLUIE_FAIBLE
        assert rain.slots[4].intensity == RainIntensity.PLUIE_MODEREE
        assert rain.slots[0].minutes_from_now == 0
        assert rain.slots[-1].minutes_from_now == 55
        assert rain.update_time.tzinfo is not None

    def test_empty_rain_forecast(self) -> None:
        client = MagicMock()
        rain_obj = MagicMock()
        rain_obj.forecast = []
        rain_obj.updated_on = 0
        client.get_rain.return_value = rain_obj
        provider = _make_provider(client)
        rain = provider.get_rain_next_hour(0, 0)
        assert rain.slots == []
        assert rain.update_time.tzinfo is not None

    def test_unknown_intensity_code_falls_back(self) -> None:
        client = MagicMock()
        rain_obj = MagicMock()
        rain_obj.forecast = [{"dt": 1778500800, "rain": 9}]
        rain_obj.updated_on = 1778500800
        client.get_rain.return_value = rain_obj
        provider = _make_provider(client)
        rain = provider.get_rain_next_hour(0, 0)
        assert rain.slots[0].intensity == RainIntensity.INCONNU


class TestGetVigilance:
    def test_parses_phenomenons_and_max(self, mf_vigilance_63: dict[str, Any]) -> None:
        client = MagicMock()
        warning_obj = MagicMock()
        warning_obj.phenomenons_max_colors = mf_vigilance_63["phenomenons_max_colors"]
        warning_obj.update_time = mf_vigilance_63["update_time"]
        client.get_warning_current_phenomenons.return_value = warning_obj
        provider = _make_provider(client)
        bulletin = provider.get_vigilance("63")
        assert bulletin.departement == "63"
        # Highest in fixture: phenomenon 3 = orages, color 3 = orange
        assert bulletin.max_color == VigilanceColor.ORANGE
        types = {p.type for p in bulletin.phenomena}
        assert VigilancePhenomenonType.ORAGES in types
        assert VigilancePhenomenonType.VENT in types
        assert bulletin.fetched_at.tzinfo is not None
        client.get_warning_current_phenomenons.assert_called_once_with(domain="63")

    def test_all_green_max_is_vert(self) -> None:
        client = MagicMock()
        warning_obj = MagicMock()
        warning_obj.phenomenons_max_colors = [
            {"phenomenon_id": "1", "phenomenon_max_color_id": 1},
        ]
        warning_obj.update_time = 1778500800
        client.get_warning_current_phenomenons.return_value = warning_obj
        provider = _make_provider(client)
        bulletin = provider.get_vigilance("63")
        assert bulletin.max_color == VigilanceColor.VERT

    def test_unknown_phenomenon_skipped(self) -> None:
        client = MagicMock()
        warning_obj = MagicMock()
        warning_obj.phenomenons_max_colors = [
            {"phenomenon_id": "99", "phenomenon_max_color_id": 2},
            {"phenomenon_id": "1", "phenomenon_max_color_id": 1},
        ]
        warning_obj.update_time = 1778500800
        client.get_warning_current_phenomenons.return_value = warning_obj
        provider = _make_provider(client)
        bulletin = provider.get_vigilance("63")
        # Only the wind (id=1) phenomenon kept; unknown id=99 dropped.
        assert len(bulletin.phenomena) == 1
        assert bulletin.phenomena[0].type == VigilancePhenomenonType.VENT


class TestProviderName:
    def test_provider_name(self) -> None:
        provider = _make_provider(MagicMock())
        assert provider.provider_name == "meteofrance_community"
