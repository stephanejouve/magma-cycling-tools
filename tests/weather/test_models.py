"""Tests for Pydantic v2 models (tz-aware enforcement + invariants)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from magma_cycling_tools.weather.models import (
    ForecastPoint,
    MissingCircuitError,
    RainForecast,
    RainIntensity,
    RainSlot,
    RouteWeather,
    RouteWeatherSegment,
    RouteWeatherSummary,
    SamplePoint,
    VigilanceBulletin,
    VigilanceColor,
    VigilancePhenomenon,
    VigilancePhenomenonType,
)


def _make_forecast(valid_at: datetime | None = None) -> ForecastPoint:
    return ForecastPoint(
        temperature_c=17.0,
        feels_like_c=16.0,
        humidity_pct=60,
        wind_speed_kmh=15.0,
        wind_gust_kmh=25.0,
        wind_direction_deg=240,
        precipitation_mm=0.2,
        precipitation_probability_pct=20,
        cloud_cover_pct=50,
        weather_description_fr="Eclaircies",
        valid_at=valid_at or datetime.now(tz=timezone.utc),
    )


class TestTimezoneAwareness:
    def test_forecast_naive_datetime_rejected(self) -> None:
        with pytest.raises(ValidationError, match="timezone-aware"):
            _make_forecast(valid_at=datetime(2026, 5, 11, 14, 0))

    def test_forecast_aware_datetime_accepted(self) -> None:
        fp = _make_forecast(valid_at=datetime(2026, 5, 11, 14, 0, tzinfo=timezone.utc))
        assert fp.valid_at.tzinfo is not None

    def test_rain_forecast_naive_update_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RainForecast(
                lat=45.0, lon=3.0, slots=[], update_time=datetime(2026, 5, 11)
            )

    def test_vigilance_naive_fetched_at_rejected(self) -> None:
        with pytest.raises(ValidationError):
            VigilanceBulletin(
                departement="63",
                max_color=VigilanceColor.VERT,
                phenomena=[],
                fetched_at=datetime(2026, 5, 11),
            )

    def test_route_weather_naive_start_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RouteWeather(
                circuit_id="x",
                start_time=datetime(2026, 5, 11),
                estimated_duration_min=60,
                segments=[],
                summary=RouteWeatherSummary(
                    avg_wind_kmh=0,
                    max_wind_gust_kmh=0,
                    cumulative_precipitation_mm=0,
                    max_precipitation_probability_pct=0,
                    min_temperature_c=0,
                    max_temperature_c=0,
                ),
            )

    def test_vigilance_phenomenon_optional_naive_rejected(self) -> None:
        with pytest.raises(ValidationError):
            VigilancePhenomenon(
                type=VigilancePhenomenonType.VENT,
                color=VigilanceColor.JAUNE,
                start_at=datetime(2026, 5, 11),
            )

    def test_vigilance_phenomenon_none_start_accepted(self) -> None:
        p = VigilancePhenomenon(
            type=VigilancePhenomenonType.VENT,
            color=VigilanceColor.VERT,
            start_at=None,
        )
        assert p.start_at is None


class TestValidationConstraints:
    def test_humidity_above_100_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ForecastPoint(
                temperature_c=10,
                feels_like_c=10,
                humidity_pct=120,
                wind_speed_kmh=0,
                wind_gust_kmh=0,
                wind_direction_deg=0,
                precipitation_mm=0,
                precipitation_probability_pct=0,
                cloud_cover_pct=0,
                weather_description_fr="",
                valid_at=datetime.now(tz=timezone.utc),
            )

    def test_wind_direction_360_rejected(self) -> None:
        # Boundary: must be < 360 (lt=360)
        with pytest.raises(ValidationError):
            ForecastPoint(
                temperature_c=10,
                feels_like_c=10,
                humidity_pct=50,
                wind_speed_kmh=0,
                wind_gust_kmh=0,
                wind_direction_deg=360,
                precipitation_mm=0,
                precipitation_probability_pct=0,
                cloud_cover_pct=0,
                weather_description_fr="",
                valid_at=datetime.now(tz=timezone.utc),
            )

    def test_rain_slot_minutes_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RainSlot(
                minutes_from_now=70,
                intensity=RainIntensity.SEC,
                intensity_code=1,
            )

    def test_models_are_frozen(self) -> None:
        fp = _make_forecast()
        with pytest.raises(ValidationError):
            fp.temperature_c = 99  # type: ignore[misc]


class TestRouteWeather:
    def test_route_weather_roundtrip(self) -> None:
        fp = _make_forecast()
        seg = RouteWeatherSegment(
            segment_index=0, lat=45.0, lon=3.0, km_marker=0.0, elevation_m=300.0, forecast=fp
        )
        rw = RouteWeather(
            circuit_id="circuit-test",
            start_time=datetime(2026, 5, 11, 8, 0, tzinfo=timezone.utc),
            estimated_duration_min=120,
            segments=[seg],
            summary=RouteWeatherSummary(
                avg_wind_kmh=12,
                max_wind_gust_kmh=20,
                cumulative_precipitation_mm=0.2,
                max_precipitation_probability_pct=25,
                min_temperature_c=15,
                max_temperature_c=19,
            ),
        )
        assert rw.segments[0].forecast.temperature_c == 17.0
        # extra fields rejected (extra="forbid")
        with pytest.raises(ValidationError):
            RouteWeatherSegment(  # type: ignore[call-arg]
                segment_index=0,
                lat=45.0,
                lon=3.0,
                km_marker=0.0,
                elevation_m=0.0,
                forecast=fp,
                bogus="x",
            )


class TestSamplePoint:
    def test_sample_point_negative_index_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SamplePoint(
                sample_index=-1,
                lat=0,
                lon=0,
                km_marker=0,
                elevation_m=0,
                cumulative_time_min=0,
            )


def test_missing_circuit_error_is_exception() -> None:
    assert issubclass(MissingCircuitError, Exception)
    with pytest.raises(MissingCircuitError):
        raise MissingCircuitError("ko")
