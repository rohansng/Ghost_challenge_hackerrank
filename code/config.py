"""
config.py — Centralized Configuration Management for Ghost Data Still Exists.
Provides typed configuration dataclasses, path resolution, and runtime defaults.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass(frozen=True)
class EngineConfig:
    """Immutable runtime configuration for the Deletion Audit Engine."""

    dataset_dir: str = "dataset"
    output_path: str = "output.csv"
    log_level: str = "INFO"
    enable_validation: bool = True
    strict_evidence_provenance: bool = True
    natural_sort_output: bool = True

    # Filenames within dataset_dir
    deletion_requests_file: str = "deletion_requests.csv"
    user_identities_file: str = "user_identities.csv"
    user_audit_log_file: str = "user_audit_log.csv"
    system_activity_file: str = "system_activity.csv"
    deletion_rules_file: str = "deletion_rules.csv"
    evidence_files_file: str = "evidence_files.csv"
    evidence_dir: str = "evidence"

    def get_dataset_path(self, filename: str) -> str:
        """Resolve absolute or relative path within dataset_dir."""
        return os.path.normpath(os.path.join(self.dataset_dir, filename))

    def get_evidence_path(self, relative_path: str) -> str:
        """Resolve evidence file path."""
        return os.path.normpath(os.path.join(self.dataset_dir, self.evidence_dir, relative_path))

    @classmethod
    def from_env(cls) -> "EngineConfig":
        """Instantiate configuration from environment variables if present."""
        return cls(
            dataset_dir=os.getenv("GHOST_DATASET_DIR", "dataset"),
            output_path=os.getenv("GHOST_OUTPUT_PATH", "output.csv"),
            log_level=os.getenv("GHOST_LOG_LEVEL", "INFO"),
            enable_validation=os.getenv("GHOST_ENABLE_VALIDATION", "1").lower() in ("1", "true", "yes"),
        )
