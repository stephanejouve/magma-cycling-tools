"""Tests for circuits.models (PR1 schemas-only).

Coverage : Pydantic validation (bornes, frozen, extra=forbid), invariants
métier (max >= min duration, regex prescription_id, n_proposals 1-5,
proposals count cap), round-trip JSON.

PR2-4 (Junior) will add tests against the métier modules (catalog,
composer, scorer) that consume these schemas.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from magma_cycling_tools.circuits import (
    BlockPlacement,
    CandidateSegment,
    CircuitDraft,
    FindSuitableCircuitsInput,
    FindSuitableCircuitsOutput,
    GeoPoint,
    Proposal,
    ProposalStatus,
    SurfaceType,
    TerrainConstraints,
)


class TestGeoPoint:
    """Lat/lon bounds, frozen, extra=forbid."""

    def test_valid_point(self):
        p = GeoPoint(lat=45.7831, lon=3.0828, label="Orcines")
        assert p.lat == 45.7831
        assert p.label == "Orcines"

    def test_label_optional(self):
        p = GeoPoint(lat=0.0, lon=0.0)
        assert p.label is None

    @pytest.mark.parametrize("lat", [-91.0, 91.0, 200.0, -200.0])
    def test_lat_out_of_bounds_rejected(self, lat):
        with pytest.raises(ValidationError):
            GeoPoint(lat=lat, lon=0.0)

    @pytest.mark.parametrize("lon", [-181.0, 181.0, 200.0])
    def test_lon_out_of_bounds_rejected(self, lon):
        with pytest.raises(ValidationError):
            GeoPoint(lat=0.0, lon=lon)

    def test_frozen(self):
        p = GeoPoint(lat=45.0, lon=3.0)
        with pytest.raises(ValidationError):
            p.lat = 50.0  # type: ignore[misc]

    def test_extra_forbidden(self):
        with pytest.raises(ValidationError):
            GeoPoint(lat=45.0, lon=3.0, elevation=500.0)  # type: ignore[call-arg]


class TestTerrainConstraints:
    """Effort type literal, intensity range, max >= min duration, gradient bounds."""

    def _minimal_valid(self, **overrides):
        defaults = {
            "effort_type": "SS",
            "intensity_pct_ftp": 92.0,
            "min_block_duration_min": 8.0,
            "max_block_duration_min": 15.0,
            "target_gradient_pct": 5.0,
            "gradient_tolerance_pct": 1.0,
            "min_gradient_regularity": 0.7,
        }
        defaults.update(overrides)
        return TerrainConstraints(**defaults)

    def test_valid_default_surfaces(self):
        c = self._minimal_valid()
        assert c.preferred_surface == [SurfaceType.ASPHALT, SurfaceType.COMPACTED]

    @pytest.mark.parametrize("effort", ["Z2", "SS", "VO2", "TEMPO", "REC", "INT", "TEST"])
    def test_all_effort_types_accepted(self, effort):
        c = self._minimal_valid(effort_type=effort)
        assert c.effort_type == effort

    def test_unknown_effort_type_rejected(self):
        with pytest.raises(ValidationError):
            self._minimal_valid(effort_type="SWEET_SPOT_LONG")

    def test_max_below_min_rejected(self):
        with pytest.raises(ValidationError, match="max_block_duration_min"):
            self._minimal_valid(min_block_duration_min=20.0, max_block_duration_min=15.0)

    def test_max_equal_min_accepted(self):
        c = self._minimal_valid(min_block_duration_min=10.0, max_block_duration_min=10.0)
        assert c.max_block_duration_min == 10.0

    @pytest.mark.parametrize("intensity", [39.0, 131.0])
    def test_intensity_out_of_bounds(self, intensity):
        with pytest.raises(ValidationError):
            self._minimal_valid(intensity_pct_ftp=intensity)

    @pytest.mark.parametrize("regularity", [-0.1, 1.1])
    def test_regularity_out_of_bounds(self, regularity):
        with pytest.raises(ValidationError):
            self._minimal_valid(min_gradient_regularity=regularity)

    def test_frozen(self):
        c = self._minimal_valid()
        with pytest.raises(ValidationError):
            c.intensity_pct_ftp = 100.0  # type: ignore[misc]


class TestCandidateSegment:
    """Length > 0, gradient bounds, surface enum, regularity 0-1."""

    def _minimal_valid(self, **overrides):
        defaults = {
            "segment_id": "SEG_001",
            "name": "Côte de Saint-Amand",
            "start": GeoPoint(lat=45.7, lon=3.4),
            "end": GeoPoint(lat=45.72, lon=3.42),
            "length_km": 5.8,
            "gradient_avg_pct": 5.2,
            "gradient_regularity": 0.85,
            "surface": SurfaceType.ASPHALT,
            "min_duration_at_ftp_min": 9.5,
        }
        defaults.update(overrides)
        return CandidateSegment(**defaults)

    def test_valid_segment(self):
        s = self._minimal_valid()
        assert s.segment_id == "SEG_001"
        assert s.tags == []

    def test_empty_segment_id_rejected(self):
        with pytest.raises(ValidationError):
            self._minimal_valid(segment_id="")

    def test_negative_length_rejected(self):
        with pytest.raises(ValidationError):
            self._minimal_valid(length_km=-1.0)

    def test_zero_length_rejected(self):
        with pytest.raises(ValidationError):
            self._minimal_valid(length_km=0.0)

    def test_tags_extensibility(self):
        s = self._minimal_valid(tags=["climbfinder_curated", "auvergne", "popular"])
        assert "popular" in s.tags


class TestCircuitDraft:
    """At least 1 segment, distance > 0, elevation >= 0."""

    def _minimal_valid(self, **overrides):
        defaults = {
            "draft_id": "DRAFT_001",
            "start_location": GeoPoint(lat=45.78, lon=3.08, label="Orcines"),
            "segments_used": ["SEG_001", "SEG_002"],
            "total_distance_km": 62.4,
            "total_elevation_m": 1140.0,
            "estimated_duration_min": 198.0,
        }
        defaults.update(overrides)
        return CircuitDraft(**defaults)

    def test_valid_draft(self):
        d = self._minimal_valid()
        assert len(d.segments_used) == 2

    def test_empty_segments_rejected(self):
        with pytest.raises(ValidationError):
            self._minimal_valid(segments_used=[])

    def test_zero_distance_rejected(self):
        with pytest.raises(ValidationError):
            self._minimal_valid(total_distance_km=0.0)

    def test_flat_circuit_zero_elevation_ok(self):
        d = self._minimal_valid(total_elevation_m=0.0)
        assert d.total_elevation_m == 0.0


class TestProposal:
    """Rank 1-5, scores 0-1, gpx_xml non-empty, optional weather/timing scores."""

    def _minimal_valid(self, **overrides):
        defaults = {
            "rank": 1,
            "name": "Boucle Saint-Amand par le Forez",
            "distance_km": 62.4,
            "elevation_m": 1140.0,
            "estimated_duration_min": 198.0,
            "gpx_xml": '<?xml version="1.0"?><gpx version="1.1"><trk></trk></gpx>',
            "workout_fit_score": 0.92,
            "overall_score": 0.91,
            "narrative": "Boucle de 62 km avec rampe principale 11'40 @ 5.8% régulier.",
        }
        defaults.update(overrides)
        return Proposal(**defaults)

    def test_valid_proposal(self):
        p = self._minimal_valid()
        assert p.rank == 1
        assert p.weather_score is None
        assert p.blocks_placement == []
        assert p.caveats == []

    @pytest.mark.parametrize("rank", [0, 6, -1, 100])
    def test_rank_out_of_bounds_rejected(self, rank):
        with pytest.raises(ValidationError):
            self._minimal_valid(rank=rank)

    @pytest.mark.parametrize("score", [-0.1, 1.1, 2.0])
    def test_score_out_of_bounds_rejected(self, score):
        with pytest.raises(ValidationError):
            self._minimal_valid(workout_fit_score=score)

    def test_empty_gpx_xml_rejected(self):
        with pytest.raises(ValidationError):
            self._minimal_valid(gpx_xml="")

    def test_empty_narrative_rejected(self):
        with pytest.raises(ValidationError):
            self._minimal_valid(narrative="")

    def test_with_optional_scores(self):
        p = self._minimal_valid(weather_score=0.85, timing_score=1.0)
        assert p.weather_score == 0.85
        assert p.timing_score == 1.0

    def test_with_blocks_and_caveats(self):
        p = self._minimal_valid(
            blocks_placement=[
                BlockPlacement(block="SS #1-2", location="Côte de Saint-Amand, km 18-30"),
            ],
            caveats=["Surface dégradée vers Olliergues, max 50 km/h"],
        )
        assert p.blocks_placement[0].block == "SS #1-2"
        assert len(p.caveats) == 1


class TestBlockPlacement:
    """Both fields non-empty."""

    def test_valid(self):
        b = BlockPlacement(block="VO2 #1", location="Pas de Peyrol, km 42-47")
        assert b.block == "VO2 #1"

    @pytest.mark.parametrize("field", ["block", "location"])
    def test_empty_field_rejected(self, field):
        payload = {"block": "SS #1", "location": "Côte X"}
        payload[field] = ""
        with pytest.raises(ValidationError):
            BlockPlacement(**payload)


class TestFindSuitableCircuitsInput:
    """Regex prescription_id, n_proposals 1-5, defaults."""

    def test_minimal_valid(self):
        i = FindSuitableCircuitsInput(prescription_id="S089-04")
        assert i.from_location is None
        assert i.n_proposals == 3
        assert i.weather_check is True
        assert i.preferred_surface == [SurfaceType.ASPHALT, SurfaceType.COMPACTED]

    @pytest.mark.parametrize(
        "pid",
        ["S089-04", "S001-01", "S999-99", "S089-04a", "S089-04z"],
    )
    def test_valid_prescription_id(self, pid):
        i = FindSuitableCircuitsInput(prescription_id=pid)
        assert i.prescription_id == pid

    @pytest.mark.parametrize(
        "pid",
        ["S89-04", "S0890-04", "S089-4", "s089-04", "S089_04", "S089-04A", "", "garbage"],
    )
    def test_invalid_prescription_id_rejected(self, pid):
        with pytest.raises(ValidationError, match="must match pattern"):
            FindSuitableCircuitsInput(prescription_id=pid)

    @pytest.mark.parametrize("n", [0, 6, -1, 10])
    def test_n_proposals_out_of_bounds(self, n):
        with pytest.raises(ValidationError):
            FindSuitableCircuitsInput(prescription_id="S089-04", n_proposals=n)

    def test_from_location_override(self):
        i = FindSuitableCircuitsInput(
            prescription_id="S089-04",
            from_location=GeoPoint(lat=45.78, lon=3.08, label="Holiday spot"),
        )
        assert i.from_location is not None
        assert i.from_location.label == "Holiday spot"


class TestFindSuitableCircuitsOutput:
    """Status enum, proposals count cap at 5, metadata required."""

    def _metadata(self, **overrides):
        defaults = {
            "tool_version": "0.3.0",
            "prescription_id": "S089-04",
            "generated_at": "2026-05-14T07:30:00+02:00",
        }
        defaults.update(overrides)
        return defaults

    def test_status_ok_with_proposals(self):
        proposal = Proposal(
            rank=1,
            name="Test",
            distance_km=50.0,
            elevation_m=500.0,
            estimated_duration_min=120.0,
            gpx_xml="<gpx/>",
            workout_fit_score=0.9,
            overall_score=0.85,
            narrative="ok",
        )
        out = FindSuitableCircuitsOutput(
            status=ProposalStatus.OK,
            proposals=[proposal],
            _metadata=self._metadata(),  # type: ignore[arg-type]
        )
        assert out.status == ProposalStatus.OK
        assert len(out.proposals) == 1

    def test_needs_location_empty_proposals(self):
        out = FindSuitableCircuitsOutput(
            status=ProposalStatus.NEEDS_LOCATION,
            _metadata=self._metadata(),  # type: ignore[arg-type]
        )
        assert out.proposals == []

    def test_no_match_status(self):
        out = FindSuitableCircuitsOutput(
            status=ProposalStatus.NO_MATCH,
            _metadata=self._metadata(),  # type: ignore[arg-type]
        )
        assert out.status == ProposalStatus.NO_MATCH

    def test_weather_blocked_status(self):
        out = FindSuitableCircuitsOutput(
            status=ProposalStatus.WEATHER_BLOCKED,
            _metadata=self._metadata(),  # type: ignore[arg-type]
        )
        assert out.status == ProposalStatus.WEATHER_BLOCKED

    def test_proposals_count_cap_at_5(self):
        proposal = Proposal(
            rank=1,
            name="X",
            distance_km=10.0,
            elevation_m=10.0,
            estimated_duration_min=30.0,
            gpx_xml="<gpx/>",
            workout_fit_score=0.5,
            overall_score=0.5,
            narrative="x",
        )
        with pytest.raises(ValidationError, match="at most 5"):
            FindSuitableCircuitsOutput(
                status=ProposalStatus.OK,
                proposals=[proposal] * 6,
                _metadata=self._metadata(),  # type: ignore[arg-type]
            )


class TestRoundTripJSON:
    """Pydantic v2 serialization round-trip stability."""

    def test_proposal_round_trip(self):
        p = Proposal(
            rank=1,
            name="Test",
            distance_km=50.0,
            elevation_m=500.0,
            estimated_duration_min=120.0,
            gpx_xml="<gpx/>",
            workout_fit_score=0.9,
            weather_score=0.85,
            overall_score=0.88,
            narrative="round trip",
        )
        as_json = p.model_dump_json()
        re_loaded = Proposal.model_validate_json(as_json)
        assert re_loaded == p

    def test_terrain_constraints_round_trip(self):
        c = TerrainConstraints(
            effort_type="SS",
            intensity_pct_ftp=92.0,
            min_block_duration_min=8.0,
            max_block_duration_min=15.0,
            target_gradient_pct=5.0,
            gradient_tolerance_pct=1.0,
            min_gradient_regularity=0.7,
        )
        as_json = c.model_dump_json()
        re_loaded = TerrainConstraints.model_validate_json(as_json)
        assert re_loaded == c
