"""Provider factory keyed by the ``MAGMA_WEATHER_PROVIDER`` env var (spec §4.2)."""

from __future__ import annotations

import os

from magma_cycling_tools.weather.providers.base import WeatherProvider
from magma_cycling_tools.weather.providers.meteofrance_community import (
    MeteofranceCommunityProvider,
)
from magma_cycling_tools.weather.providers.meteofrance_official import (
    MeteofranceOfficialProvider,
)

PROVIDER_ENV_VAR = "MAGMA_WEATHER_PROVIDER"
DEFAULT_PROVIDER = "meteofrance_community"

_REGISTRY: dict[str, type[WeatherProvider]] = {
    "meteofrance_community": MeteofranceCommunityProvider,
    "meteofrance_official": MeteofranceOfficialProvider,
}


class UnknownProviderError(ValueError):
    """Raised when ``MAGMA_WEATHER_PROVIDER`` references an unregistered name."""


def get_weather_provider(name: str | None = None) -> WeatherProvider:
    """Return an instance of the configured weather provider.

    Priority for the provider name:
      1. Explicit ``name`` argument (caller override, used in tests).
      2. ``MAGMA_WEATHER_PROVIDER`` environment variable.
      3. :data:`DEFAULT_PROVIDER` (``meteofrance_community``).
    """
    resolved = (name or os.getenv(PROVIDER_ENV_VAR) or DEFAULT_PROVIDER).strip()
    if resolved not in _REGISTRY:
        raise UnknownProviderError(
            f"Unknown weather provider {resolved!r}. " f"Registered: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[resolved]()
