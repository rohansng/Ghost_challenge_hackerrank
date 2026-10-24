"""
Text Evidence Extractor
Parses handover notes and pipe-delimited text evidence into EvidenceObservation records.
"""

import os
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from code.evidence_models import EvidenceObservation, ObservedState


def parse_iso(ts_str: Optional[str]) -> Optional[datetime]:
    if not ts_str:
        return None
    try:
        clean = ts_str.strip().replace("Z", "+00:00")
        return datetime.fromisoformat(clean)
    except Exception:
        return None


class TextExtractor:
    def __init__(self, evidence_manifest: Dict[str, Dict[str, Any]]):
        self.manifest = evidence_manifest

    def extract_from_file(self, full_path: str, rel_path: str) -> List[EvidenceObservation]:
        observations = []
        meta = self.manifest.get(rel_path, {})
        file_id = meta.get("file_id", os.path.basename(full_path))
        manifest_captured_at = parse_iso(meta.get("captured_at"))

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            return observations

        for line_no, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line or not line.startswith("-") or "|" not in line:
                continue

            # Strip leading dash
            clean_line = line.lstrip("-").strip()
            parts = [p.strip() for p in clean_line.split("|")]
            if len(parts) < 6:
                continue

            ts_str, sys_name, res_id, rec_type, status, subj_ref = parts[:6]
            event_time = parse_iso(ts_str) or manifest_captured_at

            email = subj_ref if "@" in subj_ref else None
            user_id = subj_ref if subj_ref and not "@" in subj_ref else None

            # Map status to ObservedState
            status_upper = status.upper()
            if status_upper in ("NOT_FOUND", "ABSENT", "DELETED"):
                state = ObservedState.ABSENT
            elif status_upper in ("FOUND", "PRESENT", "IDENTIFIABLE"):
                state = ObservedState.PRESENT
            elif status_upper in ("REDACTED", "TOMBSTONE"):
                state = ObservedState.REDACTED
            elif status_upper in ("ANONYMOUS", "ANONYMIZED"):
                state = ObservedState.ANONYMIZED
            elif status_upper in ("ENABLED", "ACTIVE"):
                state = ObservedState.ACTIVE
            elif status_upper in ("DISABLED", "STOPPED"):
                state = ObservedState.DISABLED
            elif status_upper in ("BLOCKED",):
                state = ObservedState.BLOCKED
            elif status_upper in ("RETAINED",):
                state = ObservedState.PRESENT
            else:
                state = ObservedState.UNKNOWN

            # Map record_type to category
            rec_type_upper = rec_type.upper()
            if "PROFILE" in rec_type_upper:
                cat = "USER_PROFILE"
            elif "SEARCH" in rec_type_upper:
                cat = "SEARCH_INDEX_ENTRY"
            elif "ANALYTICS" in rec_type_upper:
                cat = "ANALYTICS_PROFILE"
            elif "ATTACHMENT" in rec_type_upper:
                cat = "SUPPORT_ATTACHMENT"
            elif "MESSAGE" in rec_type_upper:
                cat = "SUPPORT_MESSAGE"
            elif "CONNECTOR" in rec_type_upper or "SUBSCRIPTION" in rec_type_upper:
                cat = "CONNECTOR_SUBSCRIPTION"
            elif "BACKUP" in rec_type_upper:
                cat = "BACKUP_ARCHIVE"
            elif "AUDIT" in rec_type_upper or "SECURITY" in rec_type_upper:
                cat = "SECURITY_AUDIT_LOG"
            elif "EXPORT" in rec_type_upper:
                cat = "USER_EXPORT"
            else:
                cat = rec_type_upper

            obs = EvidenceObservation(
                observation_id=f"{file_id}_{line_no}",
                evidence_id=file_id,
                source_file=rel_path,
                source_location=f"line:{line_no}",
                extraction_method="text_handover_parser",
                captured_at=manifest_captured_at,
                event_time=event_time,
                system_id=sys_name,
                resource_id=res_id,
                resource_type=cat,
                data_category=cat,
                observed_state=state,
                user_id=user_id,
                matched_identifier=email,
                raw_payload={"raw_line": line, "status": status, "subject_reference": subj_ref},
                semantic_interpretation=f"Handover report: {sys_name} {res_id} status={status}",
            )
            observations.append(obs)

        return observations
