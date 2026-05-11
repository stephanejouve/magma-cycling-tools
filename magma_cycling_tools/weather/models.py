"""Pydantic v2 models for the weather module (ADR §4.3).

All datetime fields are timezone-aware (default tz: Europe/Paris when the
caller does not provide one). Metric units only (°C, km/h, mm, %, km).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MissingCircuitError(Exception):
    """Raised when a circuit lookup returns nothing (escalation, no fallback).

    Per spec §6 rule 1, the weather lib never substitutes default coordinates
    when a circuit is missing; the caller (handler) must surface the error to
    Claude as a structured escalation.
    """


class VigilanceColor(str, Enum):
    """Météo-France Vigilance four-tier color scale."""

    VERT = "vert"
    JAUNE = "jaune"
    ORANGE = "orange"
    ROUGE = "rouge"


class VigilancePhenomenonType(str, Enum):
    """Météo-France Vigilance phenomenon types (9 official categories)."""

    VENT = "vent"
    PLUIE = "pluie"
    ORAGES = "orages"
    NEIGE = "neige"
    CANICULE = "canicule"
    GRAND_FROID = "grand_froid"
    AVALANCHES = "avalanches"
    VAGUES_SUBMERSION = "vagues_submersion"
    CRUES = "crues"


class RainIntensity(str, Enum):
    """Rain intensity buckets returned by Météo-France 1-hour rain forecast."""

    SEC = "sec"
    PLUIE_FAIBLE = "pluie_faible"
    PLUIE_MODEREE = "pluie_moderee"
    PLUIE_FORTE = "pluie_forte"
    INCONNU = "inconnu"


class _TZAwareModel(BaseModel):
    """Shared base enforcing tz-aware datetime validation."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def _ensure_tz_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware (no naive datetime allowed)")
    return value


class ForecastPoint(_TZAwareModel):
    """Hourly-grained forecast for a single (lat, lon) point."""

    temperature_c: float
    feels_like_c: float
    humidity_pct: float = Field(ge=0, le=100)
    wind_speed_kmh: float = Field(ge=0)
    wind_gust_kmh: float = Field(ge=0)
    wind_direction_deg: float = Field(ge=0, lt=360)
    precipitation_mm: float = Field(ge=0)
    precipitation_probability_pct: float = Field(ge=0, le=100)
    cloud_cover_pct: float = Field(ge=0, le=100)
    weather_description_fr: str
    valid_at: datetime

    @field_validator("valid_at")
    @classmethod
    def _check_tz_aware(cls, v: datetime) -> datetime:
        return _ensure_tz_aware(v)


class RainSlot(_TZAwareModel):
    """One 5-minute slot of the 60-minute rain forecast."""

    minutes_from_now: int = Field(ge=0, le=60)
    intensity: RainIntensity
    intensity_code: int = Field(ge=0)


class RainForecast(_TZAwareModel):
    """60-minute rain forecast at 5-minute resolution."""

    lat: float
    lon: float
    slots: list[RainSlot]
    update_time: datetime

    @field_validator("update_time")
    @classmethod
    def _check_tz_aware(cls, v: datetime) -> datetime:
        return _ensure_tz_aware(v)


class VigilancePhenomenon(_TZAwareModel):
    """One phenomenon entry inside a Vigilance bulletin."""

    type: VigilancePhenomenonType
    color: VigilanceColor
    start_at: datetime | None = None
    end_at: datetime | None = None
    description_fr: str = ""

    @field_validator("start_at", "end_at")
    @classmethod
    def _check_tz_aware_optional(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        return _ensure_tz_aware(v)


class VigilanceBulletin(_TZAwareModel):
    """Vigilance bulletin for a single département."""

    departement: str
    max_color: VigilanceColor
    phenomena: list[VigilancePhenomenon]
    fetched_at: datetime

    @field_validator("fetched_at")
    @classmethod
    def _check_tz_aware(cls, v: datetime) -> datetime:
        return _ensure_tz_aware(v)


class SamplePoint(_TZAwareModel):
    """One sampled point along a circuit (output of route_sampling.sample_route)."""

    sample_index: int = Field(ge=0)
    lat: float
    lon: float
    km_marker: float = Field(ge=0)
    elevation_m: float
    cumulative_time_min: float = Field(ge=0)


class RouteWeatherSegment(_TZAwareModel):
    """One enriched segment along a route: position + forecast at passage time."""

    segment_index: int = Field(ge=0)
    lat: float
    lon: float
    km_marker: float = Field(ge=0)
    elevation_m: float
    forecast: ForecastPoint


class RouteWeatherSummary(_TZAwareModel):
    """Aggregate weather summary across all segments of a route."""

    avg_wind_kmh: float = Field(ge=0)
    max_wind_gust_kmh: float = Field(ge=0)
    cumulative_precipitation_mm: float = Field(ge=0)
    max_precipitation_probability_pct: float = Field(ge=0, le=100)
    min_temperature_c: float
    max_temperature_c: float
    has_alerts: bool = False


class RouteWeather(_TZAwareModel):
    """Complete route weather: per-segment forecasts + global summary."""

    circuit_id: str
    start_time: datetime
    estimated_duration_min: float = Field(ge=0)
    segments: list[RouteWeatherSegment]
    summary: RouteWeatherSummary

    @field_validator("start_time")
    @classmethod
    def _check_tz_aware(cls, v: datetime) -> datetime:
        return _ensure_tz_aware(v)
