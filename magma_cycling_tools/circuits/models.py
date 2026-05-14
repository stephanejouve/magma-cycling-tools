"""Pydantic v2 schemas for find-suitable-circuits (MCT-XXX-1, PR1 Leader scope).

Limite stricte PR1 schemas-only (addendum v2bis ticket section C) : pas de
fonction métier, uniquement les types et leurs invariants (``__init__``,
``model_validator``, ``Literal``/``Enum``). PR2-4 Junior implémentent
``segment_catalog.query()``, ``circuit_composer.compose()``, ``scorer.rank()``
contre ces schemas.

Frontière lib/handler (addendum v2bis ticket section F.3) :

- ``Proposal`` lib-side porte ``gpx_xml: str`` (contenu inline).
- ``MCPProposal`` handler-side (côté magma-cycling, hors de ce module)
  substitue ce champ par ``gpx_path: str`` après persistence sur
  ``training-logs/data/proposals/`` portable.

La transformation lib → handler est mécanique (write GPX + rewrite payload),
mais elle DOIT être prévue dès J1 du contrat car les deux types partagent
les autres champs.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProposalStatus(str, Enum):
    """Status values returned by ``find_suitable_circuits()``.

    - OK              : at least one proposal returned with overall_score >= 0.75
    - NEEDS_LOCATION  : athlete.home_location absent AND from_location absent
    - NO_MATCH        : no segment in catalog matches the prescription constraints
    - WEATHER_BLOCKED : weather forecast blocks all candidates (storm, T° < 0°C,
                        wind > 50 km/h, etc.)
    """

    OK = "OK"
    NEEDS_LOCATION = "NEEDS_LOCATION"
    NO_MATCH = "NO_MATCH"
    WEATHER_BLOCKED = "WEATHER_BLOCKED"


class SurfaceType(str, Enum):
    """Road surface classification (used for filtering + scoring)."""

    ASPHALT = "asphalt"
    COMPACTED = "compacted"
    GRAVEL = "gravel"
    MIXED = "mixed"


# Regex for prescription session ID (e.g. "S089-04" or "S089-04a"). Aligned
# with the schema used elsewhere in magma-cycling MCP handlers.
_SESSION_ID_PATTERN = re.compile(r"^S\d{3}-\d{2}[a-z]?$")


class _BaseModel(BaseModel):
    """Shared base : Pydantic v2 strict (frozen, extra=forbid)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class GeoPoint(_BaseModel):
    """WGS84 geographic point (decimal degrees).

    Stateless, immutable. Used for athlete home_location, segment endpoints,
    circuit start, etc.
    """

    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude WGS84 (decimal degrees)")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude WGS84 (decimal degrees)")
    label: str | None = Field(default=None, description="Optional human label (e.g. 'Chas')")


class TerrainConstraints(_BaseModel):
    """Terrain constraints derived from a workout prescription.

    Output of ``workout_to_terrain_constraints()`` (PR2 Junior scope) — a
    lookup table mapping ``effort_type`` × ``intensity_pct_ftp`` to expected
    terrain shape (gradient, regularity, block duration).

    Used downstream by ``segment_catalog.query()`` to filter candidate
    segments matching the workout.
    """

    effort_type: Literal["Z2", "SS", "VO2", "TEMPO", "REC", "INT", "TEST"] = Field(
        ..., description="Workout effort type (aligned with magma-cycling SessionType)"
    )
    intensity_pct_ftp: float = Field(
        ..., ge=40.0, le=130.0, description="Target intensity as percentage of FTP"
    )
    min_block_duration_min: float = Field(
        ..., gt=0.0, le=120.0, description="Minimum block duration in minutes"
    )
    max_block_duration_min: float = Field(
        ..., gt=0.0, le=240.0, description="Maximum block duration in minutes"
    )
    target_gradient_pct: float = Field(
        ...,
        ge=-15.0,
        le=15.0,
        description=(
            "Target average gradient in percent (e.g. 5.0 for SS climbing," " 0.0 for Z2 flat)"
        ),
    )
    gradient_tolerance_pct: float = Field(
        ..., ge=0.0, le=10.0, description="Tolerance around target gradient"
    )
    min_gradient_regularity: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum gradient regularity required (1.0 = perfectly steady," " 0.0 = chaotic)"
        ),
    )
    preferred_surface: list[SurfaceType] = Field(
        default_factory=lambda: [SurfaceType.ASPHALT, SurfaceType.COMPACTED]
    )

    @field_validator("max_block_duration_min")
    @classmethod
    def _max_ge_min(cls, v: float, info) -> float:
        min_val = info.data.get("min_block_duration_min")
        if min_val is not None and v < min_val:
            raise ValueError(
                f"max_block_duration_min ({v}) must be >= min_block_duration_min ({min_val})"
            )
        return v


class CandidateSegment(_BaseModel):
    """A catalog segment matching the terrain constraints.

    Pure data : metadata only, no routing computation. The composer
    consumes a list of these to compose loop circuits via ORS.
    """

    segment_id: str = Field(..., min_length=1, description="Unique segment identifier")
    name: str = Field(..., min_length=1, description="Human-readable name")
    start: GeoPoint
    end: GeoPoint
    length_km: float = Field(..., gt=0.0, description="Segment length in kilometers")
    gradient_avg_pct: float = Field(..., ge=-25.0, le=25.0)
    gradient_regularity: float = Field(
        ..., ge=0.0, le=1.0, description="1.0 = perfectly steady, 0.0 = chaotic"
    )
    surface: SurfaceType
    min_duration_at_ftp_min: float = Field(
        ..., gt=0.0, description="Minimum duration when ridden at FTP (minutes)"
    )
    tags: list[str] = Field(
        default_factory=list, description="Free-form catalog tags for extensibility"
    )


class CircuitDraft(_BaseModel):
    """Draft circuit composed by the routing engine before scoring.

    Pure data : the result of ``circuit_composer.compose(...)`` (PR3 Junior
    scope). One draft = one candidate loop. The scorer ranks multiple drafts
    and selects N proposals.
    """

    draft_id: str = Field(..., min_length=1)
    start_location: GeoPoint
    segments_used: list[str] = Field(
        ..., min_length=1, description="Segment IDs traversed in order"
    )
    total_distance_km: float = Field(..., gt=0.0)
    total_elevation_m: float = Field(..., ge=0.0)
    estimated_duration_min: float = Field(..., gt=0.0)
    routing_metadata: dict[str, str] = Field(
        default_factory=dict, description="Provider + profile + version (e.g. 'ORS cycling-road')"
    )


class BlockPlacement(_BaseModel):
    """Where to execute a workout block along the circuit."""

    block: str = Field(..., min_length=1, description="Block label (e.g. 'SS #1-2')")
    location: str = Field(
        ..., min_length=1, description="Human-readable location (e.g. 'Côte de X, km 18-30')"
    )


class Proposal(_BaseModel):
    """A scored circuit proposal — lib-side view (gpx_xml inline).

    The handler-side equivalent (``MCPProposal``, defined in
    magma-cycling/_mcp/schemas/circuits.py) substitutes ``gpx_xml`` by
    ``gpx_path: str`` after persisting the XML to
    ``training-logs/data/proposals/`` portable.

    Frontière lib/handler explicite (addendum ticket v2bis section F.3) :
    lib n'importe pas le handler ; handler dépend de lib.
    """

    rank: int = Field(..., ge=1, le=5, description="1-indexed rank among returned proposals")
    name: str = Field(..., min_length=1)
    distance_km: float = Field(..., gt=0.0)
    elevation_m: float = Field(..., ge=0.0)
    estimated_duration_min: float = Field(..., gt=0.0)
    gpx_xml: str = Field(
        ...,
        min_length=1,
        description="Full GPX 1.1 XML content inline (lib-side). Handler persists and rewrites.",
    )
    workout_fit_score: float = Field(..., ge=0.0, le=1.0)
    weather_score: float | None = Field(default=None, ge=0.0, le=1.0)
    timing_score: float | None = Field(default=None, ge=0.0, le=1.0)
    overall_score: float = Field(..., ge=0.0, le=1.0, description="Weighted sum of sub-scores")
    narrative: str = Field(..., min_length=1, description="Coach IA narrative (Jinja2 rendered)")
    blocks_placement: list[BlockPlacement] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list, description="Known compromises to surface")


class FindSuitableCircuitsInput(_BaseModel):
    """Input contract for ``find_suitable_circuits()``."""

    prescription_id: str = Field(
        ..., description="Session ID from the weekly plan (e.g. 'S089-04')"
    )
    from_location: GeoPoint | None = Field(
        default=None,
        description=(
            "Override of athlete.home_location. If both are None,"
            " the tool returns status=NEEDS_LOCATION (no IP geolocation,"
            " no LLM guessing — strict, per ticket AC6)."
        ),
    )
    max_total_distance_km: float | None = Field(default=None, gt=0.0, le=500.0)
    max_total_elevation_m: float | None = Field(default=None, ge=0.0, le=10000.0)
    preferred_surface: list[SurfaceType] = Field(
        default_factory=lambda: [SurfaceType.ASPHALT, SurfaceType.COMPACTED]
    )
    n_proposals: int = Field(default=3, ge=1, le=5)
    weather_check: bool = Field(default=True)

    @field_validator("prescription_id")
    @classmethod
    def _validate_prescription_id(cls, v: str) -> str:
        if not _SESSION_ID_PATTERN.match(v):
            raise ValueError(
                f"prescription_id '{v}' must match pattern S<3 digits>-<2 digits>[a-z]?"
                " (e.g. 'S089-04' or 'S089-04a')"
            )
        return v


class _OutputMetadata(_BaseModel):
    """Metadata attached to every ``find_suitable_circuits()`` response.

    AC4 of the ticket : ``_metadata.provider`` must always be present
    (architectural rule post-PR #161-#162 magma-cycling, no derogation).
    """

    provider: str = Field(
        default="magma-cycling-tools",
        description="Provider name (always 'magma-cycling-tools' for this lib)",
    )
    tool_version: str = Field(..., min_length=1)
    prescription_id: str
    generated_at: str = Field(..., description="ISO 8601 timestamp of generation (tz-aware)")


class FindSuitableCircuitsOutput(_BaseModel):
    """Output contract for ``find_suitable_circuits()`` — lib-side view.

    The MCP handler-side view substitutes each ``Proposal.gpx_xml`` by
    ``MCPProposal.gpx_path``, and adds ``_metadata.response_timestamp``
    via the ``mcp_response()`` helper magma-cycling-side (AC6 plan
    iso-config, levier 1).
    """

    status: ProposalStatus
    proposals: list[Proposal] = Field(default_factory=list)
    metadata: _OutputMetadata = Field(..., alias="_metadata")

    @field_validator("proposals")
    @classmethod
    def _proposals_count_le_5(cls, v: list[Proposal]) -> list[Proposal]:
        if len(v) > 5:
            raise ValueError(f"proposals must contain at most 5 entries, got {len(v)}")
        return v
