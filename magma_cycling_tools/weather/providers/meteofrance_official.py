"""Stub for the official Météo-France provider (MAIF/meteole portal).

Signature is aligned with :class:`WeatherProvider` so the factory can wire
it once the official client is implemented. Until then, every method raises
``NotImplementedError`` to make the missing capability explicit.
"""

from __future__ import annotations

from datetime import datetime

from magma_cycling_tools.weather.models import (
    ForecastPoint,
    RainForecast,
    VigilanceBulletin,
)
from magma_cycling_tools.weather.providers.base import WeatherProvider


class MeteofranceOfficialProvider(WeatherProvider):
    """Stub provider for the official Météo-France API (token-based)."""

    @property
    def provider_name(self) -> str:
        return "meteofrance_official"

    def get_forecast_point(
        self, lat: float, lon: float, when: datetime
    ) -> ForecastPoint:
        raise NotImplementedError(
            "Official Météo-France provider not implemented in PoC. "
            "Use MAGMA_WEATHER_PROVIDER=meteofrance_community."
        )

    def get_rain_next_hour(self, lat: float, lon: float) -> RainForecast:
        raise NotImplementedError(
            "Official Météo-France provider not implemented in PoC. "
            "Use MAGMA_WEATHER_PROVIDER=meteofrance_community."
        )

    def get_vigilance(self, departement: str) -> VigilanceBulletin:
        raise NotImplementedError(
            "Official Météo-France provider not implemented in PoC. "
            "Use MAGMA_WEATHER_PROVIDER=meteofrance_community."
        )
