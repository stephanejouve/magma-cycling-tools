# `magma_cycling_tools.weather` — PoC météo (lib pure)

Lib provider-agnostic exposant la météo Météo-France à `magma-cycling` (qui
fournit les handlers MCP côté serveur). Cette PR livre **uniquement** la lib ;
les 4 handlers MCP (`get-weather-for-session`, `get-weather-along-route`,
`get-rain-next-hour`, `get-vigilance`) sont scope Leader follow-up dans
`magma-cycling`.

## API publique

```python
from magma_cycling_tools.weather import (
    get_weather_provider,           # factory
    sample_route,                   # échantillonnage circuit
    # Pydantic v2 models
    ForecastPoint,
    RainForecast,
    VigilanceBulletin,
    RouteWeather,
    RouteWeatherSegment,
    # exception métier
    MissingCircuitError,
)
```

## Configuration

Une seule variable d'environnement contrôle le provider :

| Variable                  | Valeurs                                              | Défaut                  |
|---------------------------|------------------------------------------------------|-------------------------|
| `MAGMA_WEATHER_PROVIDER`  | `meteofrance_community` \| `meteofrance_official`    | `meteofrance_community` |

Le provider `meteofrance_official` est un **stub** (`NotImplementedError`) en
attendant l'implémentation du portail MAIF/meteole.

## Exemples

### Prévision horaire pour un point

```python
from datetime import datetime, timezone
from magma_cycling_tools.weather import get_weather_provider

provider = get_weather_provider()  # meteofrance_community par défaut
forecast = provider.get_forecast_point(
    lat=45.69, lon=3.34,
    when=datetime(2026, 5, 11, 14, 0, tzinfo=timezone.utc),
)
print(forecast.temperature_c, forecast.weather_description_fr)
```

### Pluie sur 60 minutes

```python
rain = provider.get_rain_next_hour(lat=45.69, lon=3.34)
for slot in rain.slots:
    print(f"+{slot.minutes_from_now} min : {slot.intensity.value}")
```

### Vigilance département

```python
bulletin = provider.get_vigilance(departement="63")
print(bulletin.max_color, [p.type for p in bulletin.phenomena])
```

### Échantillonnage d'un circuit

```python
from magma_cycling_tools.weather import sample_route

samples = sample_route(circuit, n_points=10, avg_speed_kmh=25.0)
for s in samples:
    print(f"km {s.km_marker:.1f} → t+{s.cumulative_time_min:.0f} min")
```

`circuit` est duck-typé : tout objet exposant un attribut `points` itérable
(liste de tuples `(lat, lon[, elevation_m])` ou dicts `{lat, lon, elevation_m}`)
est accepté. Le contrat type fort vit côté `magma-cycling` et adaptera la
signature dans la PR follow-up.

## Comportement et invariants

- **Datetimes timezone-aware obligatoires** sur tous les modèles. Les
  datetimes naïfs lèvent `ValidationError`.
- **Métrique uniquement** : °C, km/h, mm, %, km. Aucune unité impériale.
- **Aucun effet de bord** : la lib ne touche pas à Intervals.icu, ne lit ni
  n'écrit de fichier athlète.
- **Aucun appel LLM** : data brut uniquement.
- **Aucune persistance** : cache mémoire `lru_cache` autorisé, pas de disk.

## Escalade

`sample_route(circuit=None)` lève `MissingCircuitError` — **jamais de
fallback silencieux** sur des coordonnées par défaut. C'est l'appelant
(handler MCP) qui doit traduire cette exception en message structuré pour
Claude (escalation explicite).

## Limites connues du PoC

- **Progression linéaire constante** dans `sample_route` : le temps de
  passage à chaque point est dérivé de `avg_speed_kmh` (défaut 25 km/h),
  sans modélisation pente/vent. À enrichir dans une PR suivante si la démo
  Stéphane le justifie.
- **Pluie 1h Chas/Puy-de-Dôme** : la lib `meteofrance-api` peut ne pas
  retourner de données pour certaines zones rurales (issue Home Assistant
  connue). Le module retourne alors `RainForecast(slots=[], …)` sans
  exception — l'appelant décide du fallback applicatif.
- **Pas de provider officiel** : `meteofrance_official` est un stub. Le
  basculement se fera quand la lib `meteole` (MAIF) sera intégrée.
- **Pas de cache disque** : chaque appel handler refait un round-trip lib
  vers Météo-France. La couche cache disque viendra avec la PR handlers MCP.

## Stack et tests

- Python ≥ 3.11
- `meteofrance-api >= 1.3` (lib communautaire `hacf-fr`)
- `pydantic >= 2`
- Tests : 44 cas, **97.6 % de couverture** sur `magma_cycling_tools/weather`,
  `mypy --strict` clean. Aucun appel réseau réel dans les tests
  (mocks `unittest.mock` sur le client lib).
