"""Community Météo-France provider via ``hacf-fr/meteofrance-api``.

This module wraps the community lib without reinventing any of its logic
(per spec §6 rule 6). Workarounds for known lib bugs, if any, MUST be
flagged inline with ``# WORKAROUND lib bug: <issue>`` and escalated.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from meteofrance_api import MeteoFranceClient
from meteofrance_api.const import ALERT_COLOR_LIST_FR, ALERT_TYPE_DICTIONARY_FR

from magma_cycling_tools.weather.models import (
    ForecastPoint,
    RainForecast,
    RainIntensity,
    RainSlot,
    VigilanceBulletin,
    VigilanceColor,
    VigilancePhenomenon,
    VigilancePhenomenonType,
)
from magma_cycling_tools.weather.providers.base import WeatherProvider

# Map lib alert type (FR label as returned by ALERT_TYPE_DICTIONARY_FR)
# to our enum. Lib value 4 "Inondation" maps to CRUES (semantic equivalent
# in our naming).
_PHENOMENON_FR_TO_TYPE: dict[str, VigilancePhenomenonType] = {
    "Vent violent": VigilancePhenomenonType.VENT,
    "Pluie-inondation": VigilancePhenomenonType.PLUIE,
    "Orages": VigilancePhenomenonType.ORAGES,
    "Inondation": VigilancePhenomenonType.CRUES,
    "Neige-verglas": VigilancePhenomenonType.NEIGE,
    "Canicule": VigilancePhenomenonType.CANICULE,
    "Grand-froid": VigilancePhenomenonType.GRAND_FROID,
    "Avalanches": VigilancePhenomenonType.AVALANCHES,
    "Vagues-submersion": VigilancePhenomenonType.VAGUES_SUBMERSION,
}

_COLOR_FR_TO_ENUM: dict[str, VigilanceColor] = {
    "Vert": VigilanceColor.VERT,
    "Jaune": VigilanceColor.JAUNE,
    "Orange": VigilanceColor.ORANGE,
    "Rouge": VigilanceColor.ROUGE,
}

# Rain intensity code returned by the lib: 1=dry, 2=light, 3=moderate, 4=heavy.
_RAIN_CODE_TO_INTENSITY: dict[int, RainIntensity] = {
    1: RainIntensity.SEC,
    2: RainIntensity.PLUIE_FAIBLE,
    3: RainIntensity.PLUIE_MODEREE,
    4: RainIntensity.PLUIE_FORTE,
}


def _epoch_to_aware(ts: int | float) -> datetime:
    """Convert an epoch integer to a UTC-aware datetime."""
    return datetime.fromtimestamp(int(ts), tz=UTC)


def _coerce_float(value: Any, default: float = 0.0) -> float:
    """Coerce a lib value to float, falling back to ``default`` on None/missing."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class MeteofranceCommunityProvider(WeatherProvider):
    """Provider backed by the community ``meteofrance-api`` lib."""

    def __init__(self, client: MeteoFranceClient | None = None) -> None:
        self._client: MeteoFranceClient = client or MeteoFranceClient()

    @property
    def provider_name(self) -> str:
        return "meteofrance_community"

    def get_forecast_point(self, lat: float, lon: float, when: datetime) -> ForecastPoint:
        if when.tzinfo is None:
            raise ValueError("`when` must be timezone-aware")
        forecast = self._client.get_forecast(latitude=lat, longitude=lon)
        target_epoch = int(when.timestamp())
        entries: list[dict[str, Any]] = list(getattr(forecast, "forecast", []) or [])
        if not entries:
            raise RuntimeError(
                f"meteofrance-api returned no hourly forecast entries for "
                f"({lat}, {lon}) at {when.isoformat()}"
            )
        nearest = min(
            entries,
            key=lambda e: abs(int(e.get("dt", 0)) - target_epoch),
        )
        return _forecast_entry_to_point(nearest)

    def get_rain_next_hour(self, lat: float, lon: float) -> RainForecast:
        rain = self._client.get_rain(latitude=lat, longitude=lon)
        raw_slots: list[dict[str, Any]] = list(getattr(rain, "forecast", []) or [])
        update_epoch = int(getattr(rain, "updated_on", 0) or 0)
        update_time = _epoch_to_aware(update_epoch) if update_epoch else datetime.now(tz=UTC)
        if not raw_slots:
            return RainForecast(
                lat=lat,
                lon=lon,
                slots=[],
                update_time=update_time,
            )
        base_epoch = int(raw_slots[0].get("dt", update_epoch or 0))
        slots: list[RainSlot] = []
        for entry in raw_slots:
            dt = int(entry.get("dt", base_epoch))
            minutes = max(0, min(60, (dt - base_epoch) // 60))
            code = int(entry.get("rain", 1) or 1)
            slots.append(
                RainSlot(
                    minutes_from_now=minutes,
                    intensity=_RAIN_CODE_TO_INTENSITY.get(code, RainIntensity.INCONNU),
                    intensity_code=code,
                )
            )
        return RainForecast(lat=lat, lon=lon, slots=slots, update_time=update_time)

    def get_vigilance(self, departement: str) -> VigilanceBulletin:
        phenomenons = self._client.get_warning_current_phenomenons(domain=departement)
        update_epoch = int(getattr(phenomenons, "update_time", 0) or 0)
        fetched_at = _epoch_to_aware(update_epoch) if update_epoch else datetime.now(tz=UTC)
        raw_colors = getattr(phenomenons, "phenomenons_max_colors", []) or []
        items: list[VigilancePhenomenon] = []
        max_color = VigilanceColor.VERT
        for item in raw_colors:
            phenom_id = str(item.get("phenomenon_id", "0"))
            color_id = int(item.get("phenomenon_max_color_id", 0) or 0)
            label_fr = ALERT_TYPE_DICTIONARY_FR.get(phenom_id)
            color_fr = (
                ALERT_COLOR_LIST_FR[color_id] if 0 < color_id < len(ALERT_COLOR_LIST_FR) else None
            )
            if label_fr is None or color_fr is None:
                continue
            phenom_type = _PHENOMENON_FR_TO_TYPE.get(label_fr)
            color = _COLOR_FR_TO_ENUM.get(color_fr)
            if phenom_type is None or color is None:
                continue
            items.append(
                VigilancePhenomenon(
                    type=phenom_type,
                    color=color,
                    description_fr=label_fr,
                )
            )
            if _color_rank(color) > _color_rank(max_color):
                max_color = color
        return VigilanceBulletin(
            departement=departement,
            max_color=max_color,
            phenomena=items,
            fetched_at=fetched_at,
        )


def _color_rank(color: VigilanceColor) -> int:
    return {
        VigilanceColor.VERT: 0,
        VigilanceColor.JAUNE: 1,
        VigilanceColor.ORANGE: 2,
        VigilanceColor.ROUGE: 3,
    }[color]


def _forecast_entry_to_point(entry: dict[str, Any]) -> ForecastPoint:
    """Map one lib forecast entry (raw dict) to our ForecastPoint model."""
    valid_at = _epoch_to_aware(int(entry.get("dt", 0)))
    temperature = entry.get("T") or {}
    wind = entry.get("wind") or {}
    rain = entry.get("rain") or {}
    weather = entry.get("weather") or {}
    return ForecastPoint(
        temperature_c=_coerce_float(temperature.get("value")),
        feels_like_c=_coerce_float(
            temperature.get("windchill"), default=_coerce_float(temperature.get("value"))
        ),
        humidity_pct=_coerce_float(entry.get("humidity")),
        wind_speed_kmh=_coerce_float(wind.get("speed")) * 3.6,
        wind_gust_kmh=_coerce_float(wind.get("gust")) * 3.6,
        wind_direction_deg=_coerce_float(wind.get("direction")) % 360,
        precipitation_mm=_coerce_float(rain.get("1h")),
        precipitation_probability_pct=_coerce_float(entry.get("precipitation_probability")),
        cloud_cover_pct=_coerce_float(entry.get("clouds")),
        weather_description_fr=str(weather.get("desc", "")),
        valid_at=valid_at,
    )
