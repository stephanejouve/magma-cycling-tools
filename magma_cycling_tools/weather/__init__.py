"""Public API for the weather module (contract with magma-cycling MCP handlers)."""

from __future__ import annotations

from magma_cycling_tools.weather.factory import (
    PROVIDER_ENV_VAR,
    UnknownProviderError,
    get_weather_provider,
)
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
from magma_cycling_tools.weather.providers.base import WeatherProvider
from magma_cycling_tools.weather.route_sampling import sample_route

__all__ = [
    "PROVIDER_ENV_VAR",
    "ForecastPoint",
    "MissingCircuitError",
    "RainForecast",
    "RainIntensity",
    "RainSlot",
    "RouteWeather",
    "RouteWeatherSegment",
    "RouteWeatherSummary",
    "SamplePoint",
    "UnknownProviderError",
    "VigilanceBulletin",
    "VigilanceColor",
    "VigilancePhenomenon",
    "VigilancePhenomenonType",
    "WeatherProvider",
    "get_weather_provider",
    "sample_route",
]
