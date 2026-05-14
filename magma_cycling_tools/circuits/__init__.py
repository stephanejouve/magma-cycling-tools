"""Public API for the circuits module — find-suitable-circuits feature (MCT-XXX-1).

Lib pure stateless: schemas Pydantic v2 only at this stage (PR1 Leader scope).
Métier implementation (catalog query, circuit composer, scorer) follows in
PR2-4 (Junior scope, doctrine standard tools-side).

See ticket `/Users/Shared/MCT-find-suitable-circuits-backlog.md` for the full
spec, addendum v2bis section F for the lib/handler frontier with the
`Proposal` (lib-side, gpx_xml inline) vs `MCPProposal` (handler-side, gpx_path
persisted) distinction. `MCPProposal` lives on the magma-cycling handler side,
not here (this module stays stateless).
"""

from __future__ import annotations

from magma_cycling_tools.circuits.models import (
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

__all__ = [
    "BlockPlacement",
    "CandidateSegment",
    "CircuitDraft",
    "FindSuitableCircuitsInput",
    "FindSuitableCircuitsOutput",
    "GeoPoint",
    "Proposal",
    "ProposalStatus",
    "SurfaceType",
    "TerrainConstraints",
]
