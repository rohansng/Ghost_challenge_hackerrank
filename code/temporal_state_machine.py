"""
Temporal State Machine & Conflict Resolution
Reconstructs the verified state of every resource at audit_at using deterministic timeline analysis.
"""

from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

from code.evidence_models import (
    EvidenceObservation,
    ResourceStateSnapshot,
    ObservedState,
)


class TemporalStateMachine:
    """Deterministic timeline reconstructor evaluating resource states at audit_at cutoff."""

    def __init__(self):
        pass

    def evaluate_resource_states_at_audit(
        self,
        observations: List[EvidenceObservation],
        audit_at: datetime,
    ) -> Dict[str, ResourceStateSnapshot]:
        """
        Reconstructs the proven state of each observed resource strictly bounded by audit_at.
        Filters out any observation captured or occurring after audit_at.
        """
        # 1. Filter observations to strictly <= audit_at
        valid_obs = []
        for o in observations:
            obs_time = o.event_time or o.captured_at
            cap_time = o.captured_at or o.event_time
            
            # Strict temporal barrier
            if obs_time and obs_time > audit_at:
                continue
            if cap_time and cap_time > audit_at:
                continue
            valid_obs.append(o)

        # 2. Group by resource_id
        grouped: Dict[str, List[EvidenceObservation]] = defaultdict(list)
        for o in valid_obs:
            if o.resource_id:
                grouped[o.resource_id].append(o)

        snapshots: Dict[str, ResourceStateSnapshot] = {}

        for res_id, res_obs in grouped.items():
            snapshot = self._resolve_single_resource_state(res_id, res_obs, audit_at)
            if snapshot:
                snapshots[res_id] = snapshot

        return snapshots

    def _resolve_single_resource_state(
        self,
        resource_id: str,
        observations: List[EvidenceObservation],
        audit_at: datetime,
    ) -> Optional[ResourceStateSnapshot]:
        if not observations:
            return None

        # Sort chronologically by event_time, then observation_id
        sorted_obs = sorted(
            observations,
            key=lambda o: (o.event_time or datetime.min, o.observation_id),
        )

        # Separate direct physical evidence (SQL, JSON, PDF, Image, Text) from activity claims
        direct_evidence = [
            o for o in sorted_obs if o.extraction_method != "system_activity_stream"
        ]

        system_id = sorted_obs[-1].system_id
        data_cat = sorted_obs[-1].data_category

        # Conflict resolution logic:
        # Rule 1: Direct physical evidence takes precedence over activity claims.
        # Rule 2: If multiple direct evidence observations exist, the latest snapshot strictly <= audit_at dictates state.
        # Rule 3: Replicas and restores recreate data: if a delete occurred at T1, but replica/snapshot at T2 shows PRESENT (T1 < T2 <= audit_at), PRESENT wins.
        
        chosen_obs = None
        conflicts = []

        if direct_evidence:
            # Check if any direct evidence proves record presence
            presence_obs = [o for o in direct_evidence if o.observed_state in (ObservedState.PRESENT, ObservedState.ACTIVE)]
            absent_obs = [o for o in direct_evidence if o.observed_state in (ObservedState.ABSENT, ObservedState.DISABLED, ObservedState.BLOCKED, ObservedState.ANONYMIZED, ObservedState.REDACTED)]

            # Check for conflicting observations
            if presence_obs and absent_obs:
                # Compare timestamps
                latest_presence = max(presence_obs, key=lambda o: o.event_time or datetime.min)
                latest_absence = max(absent_obs, key=lambda o: o.event_time or datetime.min)

                t_pres = latest_presence.event_time or latest_presence.captured_at or datetime.min
                t_abs = latest_absence.event_time or latest_absence.captured_at or datetime.min

                if t_pres > t_abs:
                    chosen_obs = latest_presence
                    conflicts.extend(absent_obs)
                else:
                    chosen_obs = latest_absence
                    conflicts.extend(presence_obs)
            else:
                chosen_obs = direct_evidence[-1]
        else:
            # Only activity claims available
            chosen_obs = sorted_obs[-1]

        proven_state = chosen_obs.observed_state
        cited_evidence_id = chosen_obs.evidence_id if chosen_obs.extraction_method != "system_activity_stream" else ""

        # Determine compliance based on category
        is_compliant = self._check_compliance(data_cat, proven_state)

        return ResourceStateSnapshot(
            system_id=system_id,
            resource_id=resource_id,
            data_category=data_cat,
            proven_state=proven_state,
            audit_at=audit_at,
            cited_evidence_id=cited_evidence_id,
            observations_considered=sorted_obs,
            conflicting_observations=conflicts,
            resolution_rationale=f"Resolved via {chosen_obs.extraction_method} at {chosen_obs.event_time}",
            is_compliant=is_compliant,
        )

    def _check_compliance(self, category: str, state: ObservedState) -> bool:
        cat_upper = category.upper()
        if "USER_PROFILE" in cat_upper or "SEARCH" in cat_upper or "EXPORT" in cat_upper or "CACHE" in cat_upper or "MARKETING" in cat_upper or "ATTACHMENT" in cat_upper:
            return state == ObservedState.ABSENT
        elif "ANALYTICS" in cat_upper or "TELEMETRY" in cat_upper:
            return state == ObservedState.ANONYMIZED
        elif "SUPPORT_MESSAGE" in cat_upper or "TOMBSTONE" in cat_upper or "DELIVERY_LOG" in cat_upper:
            return state in (ObservedState.REDACTED, ObservedState.ABSENT)
        elif "CONNECTOR" in cat_upper or "DATA_FLOW" in cat_upper:
            return state == ObservedState.DISABLED
        elif "BACKUP" in cat_upper:
            return state == ObservedState.BLOCKED
        elif "SECURITY" in cat_upper or "LEGAL" in cat_upper:
            return state == ObservedState.PRESENT
        return state == ObservedState.ABSENT
