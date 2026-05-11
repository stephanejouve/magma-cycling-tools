"""Route sampling: pick N equidistant-by-km points along a circuit (spec §10).

The PoC uses a linear progression model (constant speed). Limitations are
documented in ``docs/weather-module.md``.

A ``Circuit`` is duck-typed for PoC simplicity — any object exposing a
``points`` attribute as a list of ``(lat, lon, elevation_m)`` tuples (or
mapping-like) is accepted. The expected production type lives in
``magma-cycling`` and will adapt this contract in the follow-up PR.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from magma_cycling_tools.weather.models import MissingCircuitError, SamplePoint

_EARTH_RADIUS_KM = 6371.0088


@runtime_checkable
class CircuitLike(Protocol):
    """Minimal contract for a terrain circuit.

    ``points`` is an ordered sequence of trackpoints, each carrying at least
    a latitude and a longitude (elevation optional, defaults to 0.0).
    """

    @property
    def points(self) -> Sequence[Any]: ...


@dataclass(frozen=True)
class _Track:
    lat: float
    lon: float
    elevation_m: float


def _coerce_point(raw: Any) -> _Track:
    """Accept tuple ``(lat, lon[, elev])`` or mapping ``{lat, lon, elevation_m}``."""
    if isinstance(raw, _Track):
        return raw
    if isinstance(raw, dict):
        return _Track(
            lat=float(raw["lat"]),
            lon=float(raw["lon"]),
            elevation_m=float(raw.get("elevation_m", 0.0)),
        )
    if isinstance(raw, (tuple, list)) and len(raw) >= 2:
        lat = float(raw[0])
        lon = float(raw[1])
        elev = float(raw[2]) if len(raw) >= 3 else 0.0
        return _Track(lat=lat, lon=lon, elevation_m=elev)
    raise TypeError(f"unsupported point format: {type(raw).__name__}")


def _haversine_km(a: _Track, b: _Track) -> float:
    lat1 = math.radians(a.lat)
    lat2 = math.radians(b.lat)
    dlat = lat2 - lat1
    dlon = math.radians(b.lon - a.lon)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def _cumulative_km(tracks: Sequence[_Track]) -> list[float]:
    cum = [0.0]
    for i in range(1, len(tracks)):
        cum.append(cum[-1] + _haversine_km(tracks[i - 1], tracks[i]))
    return cum


def _interpolate(tracks: Sequence[_Track], cum: Sequence[float], target_km: float) -> _Track:
    """Linear interpolation between the two enclosing trackpoints."""
    if target_km <= cum[0]:
        return tracks[0]
    if target_km >= cum[-1]:
        return tracks[-1]
    lo = 0
    hi = len(cum) - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if cum[mid] <= target_km:
            lo = mid
        else:
            hi = mid
    span = cum[hi] - cum[lo]
    if span == 0:
        return tracks[lo]
    ratio = (target_km - cum[lo]) / span
    a, b = tracks[lo], tracks[hi]
    return _Track(
        lat=a.lat + (b.lat - a.lat) * ratio,
        lon=a.lon + (b.lon - a.lon) * ratio,
        elevation_m=a.elevation_m + (b.elevation_m - a.elevation_m) * ratio,
    )


def sample_route(
    circuit: CircuitLike | None,
    n_points: int = 10,
    avg_speed_kmh: float = 25.0,
) -> list[SamplePoint]:
    """Sample ``n_points`` equidistant-by-km points along a circuit.

    Raises:
        MissingCircuitError: when ``circuit`` is None or has no points
          (per spec §6 rule 1, no silent fallback).
        ValueError: when ``n_points`` < 2 or ``avg_speed_kmh`` <= 0.
    """
    if circuit is None:
        raise MissingCircuitError(
            "sample_route called with circuit=None — escalation required, no fallback"
        )
    if n_points < 2:
        raise ValueError(f"n_points must be >= 2, got {n_points}")
    if avg_speed_kmh <= 0:
        raise ValueError(f"avg_speed_kmh must be > 0, got {avg_speed_kmh}")

    raw_points: Iterable[Any] = getattr(circuit, "points", None) or []
    tracks = [_coerce_point(p) for p in raw_points]
    if not tracks:
        raise MissingCircuitError(
            "circuit has an empty points list — escalation required, no fallback"
        )
    if len(tracks) == 1:
        return [
            SamplePoint(
                sample_index=i,
                lat=tracks[0].lat,
                lon=tracks[0].lon,
                km_marker=0.0,
                elevation_m=tracks[0].elevation_m,
                cumulative_time_min=0.0,
            )
            for i in range(n_points)
        ]

    cum = _cumulative_km(tracks)
    total_km = cum[-1]
    step = total_km / (n_points - 1)
    samples: list[SamplePoint] = []
    for i in range(n_points):
        target = step * i
        track = _interpolate(tracks, cum, target)
        samples.append(
            SamplePoint(
                sample_index=i,
                lat=track.lat,
                lon=track.lon,
                km_marker=target,
                elevation_m=track.elevation_m,
                cumulative_time_min=(target / avg_speed_kmh) * 60.0,
            )
        )
    return samples
