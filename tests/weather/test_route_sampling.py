"""Tests for route_sampling.sample_route."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from magma_cycling_tools.weather.models import MissingCircuitError
from magma_cycling_tools.weather.providers.meteofrance_community import (
    MeteofranceCommunityProvider,
)
from magma_cycling_tools.weather.route_sampling import sample_route


@dataclass
class FakeCircuit:
    points: list[Any] = field(default_factory=list)


class TestEscalation:
    def test_circuit_none_raises_missing(self) -> None:
        with pytest.raises(MissingCircuitError, match="circuit=None"):
            sample_route(None)

    def test_empty_points_raises_missing(self) -> None:
        with pytest.raises(MissingCircuitError, match="empty points"):
            sample_route(FakeCircuit(points=[]))


class TestValidation:
    def test_n_points_too_low_rejected(self) -> None:
        circuit = FakeCircuit(points=[(45.0, 3.0, 0.0), (45.1, 3.1, 0.0)])
        with pytest.raises(ValueError, match="n_points must be >= 2"):
            sample_route(circuit, n_points=1)

    def test_zero_speed_rejected(self) -> None:
        circuit = FakeCircuit(points=[(45.0, 3.0, 0.0), (45.1, 3.1, 0.0)])
        with pytest.raises(ValueError, match="avg_speed_kmh must be > 0"):
            sample_route(circuit, avg_speed_kmh=0)


class TestEquidistance:
    def test_endpoints_preserved(self) -> None:
        # 4-point straight line ~ 4 km apart along lat
        points = [(45.0, 3.0, 0.0), (45.04, 3.0, 10.0), (45.08, 3.0, 20.0), (45.12, 3.0, 30.0)]
        samples = sample_route(FakeCircuit(points=points), n_points=5)
        assert len(samples) == 5
        # first sample = start
        assert samples[0].lat == pytest.approx(45.0)
        # last sample = end
        assert samples[-1].lat == pytest.approx(45.12)
        # km markers are equidistant
        total = samples[-1].km_marker
        step = total / 4
        for i, s in enumerate(samples):
            assert s.km_marker == pytest.approx(step * i, abs=0.01)

    def test_dict_points_accepted(self) -> None:
        points = [
            {"lat": 45.0, "lon": 3.0, "elevation_m": 100},
            {"lat": 45.1, "lon": 3.0, "elevation_m": 200},
        ]
        samples = sample_route(FakeCircuit(points=points), n_points=3)
        assert samples[0].elevation_m == pytest.approx(100)
        assert samples[-1].elevation_m == pytest.approx(200)
        # midpoint interpolates elevation
        assert samples[1].elevation_m == pytest.approx(150, abs=0.1)

    def test_unsupported_point_format_rejected(self) -> None:
        with pytest.raises(TypeError, match="unsupported point format"):
            sample_route(FakeCircuit(points=["nope"]), n_points=2)

    def test_single_point_circuit_replicates(self) -> None:
        samples = sample_route(FakeCircuit(points=[(45.0, 3.0, 100.0)]), n_points=3)
        assert all(s.lat == 45.0 and s.lon == 3.0 for s in samples)
        assert all(s.km_marker == 0.0 for s in samples)

    def test_cumulative_time_linear(self) -> None:
        # 10 km straight; 30 km/h ⇒ 20 min total
        points = [(45.0, 3.0, 0.0), (45.09, 3.0, 0.0)]  # ~10 km
        samples = sample_route(FakeCircuit(points=points), n_points=3, avg_speed_kmh=30)
        # last cumulative_time ≈ km_marker / 30 * 60
        expected = samples[-1].km_marker / 30 * 60
        assert samples[-1].cumulative_time_min == pytest.approx(expected, rel=0.01)


class TestFullFlowIntegration:
    def test_full_flow_circuit_to_route_weather(self, mf_forecast_chas: dict[str, Any]) -> None:
        """Integration: sample_route → mocked provider → consistent timestamps."""
        # Build a 2-point circuit (~5 km)
        points = [(45.69, 3.34, 300.0), (45.73, 3.34, 320.0)]
        samples = sample_route(FakeCircuit(points=points), n_points=4, avg_speed_kmh=25.0)
        assert len(samples) == 4

        # Mock the provider to return fixture forecast
        client = MagicMock()
        forecast_obj = MagicMock()
        forecast_obj.forecast = mf_forecast_chas["forecast"]
        client.get_forecast.return_value = forecast_obj
        provider = MeteofranceCommunityProvider(client=client)

        start = datetime(2026, 5, 11, 8, 0, tzinfo=UTC)
        forecasts = []
        for s in samples:
            from datetime import timedelta

            t_pass = start + timedelta(minutes=s.cumulative_time_min)
            forecasts.append(provider.get_forecast_point(s.lat, s.lon, t_pass))

        # All forecasts came back with tz-aware valid_at; client called per sample
        assert all(f.valid_at.tzinfo is not None for f in forecasts)
        assert client.get_forecast.call_count == len(samples)
        # Sample timestamps strictly increase
        for i in range(1, len(samples)):
            assert samples[i].cumulative_time_min > samples[i - 1].cumulative_time_min
