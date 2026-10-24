"""
exceptions.py — Domain Exception Hierarchy for Ghost Data Still Exists.
Replaces generic ValueError / RuntimeError with clear typed errors.
"""

from typing import Optional, Any


class GhostDataError(Exception):
    """Base exception for all Ghost Data Still Exists domain errors."""

    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(message)
        self.message = message
        self.details = details

    def __str__(self) -> str:
        if self.details is not None:
            return f"{self.message} (details={self.details})"
        return self.message


class DatasetLoadingError(GhostDataError):
    """Raised when dataset CSV files or evidence manifests fail to parse or validate."""
    pass


class IdentityResolutionError(GhostDataError):
    """Raised when identity graph resolution encounters invalid, cyclic, or unresolvable data."""
    pass


class EvidenceExtractionError(GhostDataError):
    """Raised when evidence files (PDF, image, log, SQL, JSON) cannot be parsed or normalized."""
    pass


class TemporalReconstructionError(GhostDataError):
    """Raised when temporal state machine encounters malformed timestamps or invalid sequences."""
    pass


class PolicyEvaluationError(GhostDataError):
    """Raised when deletion policy evaluation encounters contradictory or malformed rules."""
    pass


class RecreationAnalysisError(GhostDataError):
    """Raised when system activity graph traversal or sync/restore path detection fails."""
    pass


class DecisionProofError(GhostDataError):
    """Raised when the 11-point decision proof checklist cannot be evaluated."""
    pass


class OutputValidationError(GhostDataError):
    """Raised when generated output.csv fails schema, ordering, or provenance constraints."""
    pass
