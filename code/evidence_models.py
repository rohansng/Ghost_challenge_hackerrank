"""
Phase 2 Evidence & Observation Models
Defines structured provenance, extracted observations, and resource state transitions.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Set
from enum import Enum


class ObservedState(Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    REDACTED = "REDACTED"
    ANONYMIZED = "ANONYMIZED"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    DISABLED = "DISABLED"
    ENABLED = "ENABLED"
    UNKNOWN = "UNKNOWN"


class TimelineEventType(Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    REDACT = "REDACT"
    ANONYMIZE = "ANONYMIZE"
    TOMBSTONE = "TOMBSTONE"
    SYNC = "SYNC"
    EXPORT = "EXPORT"
    IMPORT = "IMPORT"
    BACKUP = "BACKUP"
    RESTORE = "RESTORE"
    INDEX = "INDEX"
    ATTACH = "ATTACH"
    REPLICATE = "REPLICATE"
    AUDIT = "AUDIT"
    LOOKUP = "LOOKUP"


@dataclass
class EvidenceObservation:
    """Canonical model for every observation extracted from participant evidence."""
    observation_id: str
    evidence_id: str                   # file_id from evidence_files.csv (e.g. evidence_01)
    source_file: str                   # relative path (e.g. evidence/logs/service_events_ap_south_20260915.log)
    source_location: str               # line number, table name, json path, page number, etc.
    extraction_method: str             # sqlite, json_parser, log_regex, pdf_stream, image_ocr
    captured_at: Optional[datetime]    # evidence capture cutoff from manifest
    event_time: Optional[datetime]     # timestamp of the specific event/record inside evidence
    system_id: str                     # account_service, search_service, support_platform, etc.
    resource_id: str                   # account_005, search_001, etc.
    resource_type: str                 # USER_PROFILE, SEARCH_INDEX_ENTRY, etc.
    data_category: str                 # category mapped to deletion_rules.csv
    observed_state: ObservedState      # PRESENT, ABSENT, REDACTED, ANONYMIZED, etc.
    user_id: Optional[str] = None      # resolved user_id if present
    matched_identifier: Optional[str] = None # email, phone, hash, account_id
    supporting_identifiers: List[str] = field(default_factory=list)
    raw_payload: Dict[str, Any] = field(default_factory=dict)
    semantic_interpretation: str = ""  # natural language explanation
    confidence: float = 1.0            # 1.0 for deterministic match
    is_contradictory: bool = False     # flagged if conflicts with other observations


@dataclass
class ResourceStateSnapshot:
    """Represents proven state of a single resource at audit_at."""
    system_id: str
    resource_id: str
    data_category: str
    proven_state: ObservedState
    audit_at: datetime
    cited_evidence_id: str             # participant-visible evidence_id proving state
    observations_considered: List[EvidenceObservation] = field(default_factory=list)
    conflicting_observations: List[EvidenceObservation] = field(default_factory=list)
    resolution_rationale: str = ""
    is_compliant: bool = False
