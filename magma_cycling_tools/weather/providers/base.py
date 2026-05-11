"""Abstract base class for weather providers (ADR §4.1)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from magma_cycling_tools.weather.models import (
    ForecastPoint,
    RainForecast,
    VigilanceBulletin,
)


class WeatherProvider(ABC):
    """Interface for weather data sources.

    Every implementation MUST expose its provider name (used in `_metadata`
    of MCP responses as runtime source-of-truth, never inferred).
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Short identifier, e.g. ``meteofrance_community``."""

    @abstractmethod
    def get_forecast_point(
        self, lat: float, lon: float, when: datetime
    ) -> ForecastPoint:
        """Hourly forecast closest to ``when`` for the given (lat, lon)."""

    @abstractmethod
    def get_rain_next_hour(self, lat: float, lon: float) -> RainForecast:
        """60-minute rain forecast at 5-minute granularity."""

    @abstractmethod
    def get_vigilance(self, departement: str) -> VigilanceBulletin:
        """Vigilance bulletin for a French département (e.g. ``"63"``)."""
