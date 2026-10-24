"""
JSON Evidence Extractor
Parses structured JSON exports, bundles, and reports into EvidenceObservation records.
"""

import json
import os
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


class JsonExtractor:
    def __init__(self, evidence_manifest: Dict[str, Dict[str, Any]]):
        self.manifest = evidence_manifest

    def extract_from_file(self, full_path: str, rel_path: str) -> List[EvidenceObservation]:
        observations = []
        meta = self.manifest.get(rel_path, {})
        file_id = meta.get("file_id", os.path.basename(full_path))
        manifest_captured_at = parse_iso(meta.get("captured_at"))

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return observations

        if not isinstance(data, dict):
            return observations

        # 1. service_resource_export_*.json
        if "service_exports" in data:
            exported_at = parse_iso(data.get("exported_at")) or manifest_captured_at
            for svc_name, svc_data in data["service_exports"].items():
                if isinstance(svc_data, dict):
                    for sub_cat, items in svc_data.items():
                        if isinstance(items, list):
                            for idx, item in enumerate(items):
                                obs = self._parse_service_export_item(
                                    svc_name, sub_cat, item, file_id, rel_path, manifest_captured_at, idx
                                )
                                if obs:
                                    observations.append(obs)

        # 2. customer_data_snapshot_bundle_*.json
        elif "snapshots" in data:
            exported_at = parse_iso(data.get("exported_at")) or manifest_captured_at
            for s_idx, snapshot in enumerate(data["snapshots"]):
                data_store = snapshot.get("data_store", "account_service")
                collection = snapshot.get("collection", "")
                snap_time = parse_iso(snapshot.get("captured_at")) or exported_at
                records = snapshot.get("records", [])
                for r_idx, rec in enumerate(records):
                    obs = self._parse_snapshot_record(
                        data_store, collection, rec, file_id, rel_path, manifest_captured_at, f"{s_idx}_{r_idx}", snap_time=snap_time
                    )
                    if obs:
                        observations.append(obs)

        # 3. records list files (e.g. connector_configurations, security_audit_ledger, customer_export_jobs)
        elif "records" in data:
            collection = data.get("collection", "")
            for idx, rec in enumerate(data["records"]):
                obs = self._parse_generic_record(
                    rec, file_id, rel_path, manifest_captured_at, collection, idx
                )
                if obs:
                    observations.append(obs)

        return observations

    def _parse_service_export_item(
        self,
        system_id: str,
        category: str,
        item: Dict[str, Any],
        file_id: str,
        rel_path: str,
        captured_at: Optional[datetime],
        seq: int,
    ) -> Optional[EvidenceObservation]:
        obs_time = parse_iso(item.get("observed_at")) or captured_at
        res_id = item.get("resource_id", f"{system_id}_{seq}")
        obs_id = f"{file_id}_{system_id}_{seq}"

        if system_id == "account_service":
            status_code = item.get("status_code", 200)
            prof = item.get("profile") or {}
            email = prof.get("email")
            user_id = prof.get("customer_reference")
            state = ObservedState.ABSENT if status_code == 404 else ObservedState.PRESENT
            return EvidenceObservation(
                observation_id=obs_id,
                evidence_id=file_id,
                source_file=rel_path,
                source_location=f"service_exports.account_service[{seq}]",
                extraction_method="json_service_export",
                captured_at=captured_at,
                event_time=obs_time,
                system_id=system_id,
                resource_id=res_id,
                resource_type="USER_PROFILE",
                data_category="USER_PROFILE",
                observed_state=state,
                user_id=user_id,
                matched_identifier=email,
                raw_payload=item,
                semantic_interpretation=f"Profile lookup result: http_status={status_code}",
            )

        elif system_id == "analytics_platform":
            email = item.get("email")
            phone = item.get("phone")
            user_id = item.get("customer_reference")
            email_hash = item.get("email_hash")
            is_anon = not email and not phone and not user_id and not email_hash
            state = ObservedState.ANONYMIZED if is_anon else ObservedState.PRESENT
            return EvidenceObservation(
                observation_id=obs_id,
                evidence_id=file_id,
                source_file=rel_path,
                source_location=f"service_exports.analytics_platform[{seq}]",
                extraction_method="json_service_export",
                captured_at=captured_at,
                event_time=obs_time,
                system_id=system_id,
                resource_id=res_id,
                resource_type="ANALYTICS_PROFILE",
                data_category="ANALYTICS_PROFILE",
                observed_state=state,
                user_id=user_id,
                matched_identifier=email,
                supporting_identifiers=[x for x in [phone, email_hash] if x],
                raw_payload=item,
                semantic_interpretation=f"Analytics profile: state={state.value}",
            )

        elif system_id == "backup_service":
            restore_allowed = item.get("restore_allowed", False)
            user_id = item.get("customer_reference")
            email = item.get("customer_email")
            state = ObservedState.ACTIVE if restore_allowed else ObservedState.BLOCKED
            return EvidenceObservation(
                observation_id=obs_id,
                evidence_id=file_id,
                source_file=rel_path,
                source_location=f"service_exports.backup_service[{seq}]",
                extraction_method="json_service_export",
                captured_at=captured_at,
                event_time=obs_time,
                system_id=system_id,
                resource_id=res_id,
                resource_type="BACKUP_ARCHIVE",
                data_category="BACKUP_ARCHIVE",
                observed_state=state,
                user_id=user_id,
                matched_identifier=email or user_id,
                raw_payload=item,
                semantic_interpretation=f"Backup restore entry: restore_allowed={restore_allowed}",
            )

        elif system_id == "integration_service":
            enabled = item.get("enabled", False)
            user_id = item.get("customer_reference")
            email = item.get("customer_email")
            state = ObservedState.ACTIVE if enabled else ObservedState.DISABLED
            return EvidenceObservation(
                observation_id=obs_id,
                evidence_id=file_id,
                source_file=rel_path,
                source_location=f"service_exports.integration_service[{seq}]",
                extraction_method="json_service_export",
                captured_at=captured_at,
                event_time=obs_time,
                system_id=system_id,
                resource_id=res_id,
                resource_type="CONNECTOR_SUBSCRIPTION",
                data_category="CONNECTOR_SUBSCRIPTION",
                observed_state=state,
                user_id=user_id,
                matched_identifier=email or user_id,
                raw_payload=item,
                semantic_interpretation=f"Connector sync subscription: enabled={enabled}",
            )

        elif system_id == "search_service":
            hits = item.get("hits", {})
            total_hits = hits.get("total", 0)
            docs = hits.get("documents", [])
            doc_email = docs[0].get("email") if docs else item.get("query")
            doc_user = docs[0].get("customer_reference") if docs else None
            state = ObservedState.PRESENT if total_hits > 0 else ObservedState.ABSENT
            return EvidenceObservation(
                observation_id=obs_id,
                evidence_id=file_id,
                source_file=rel_path,
                source_location=f"service_exports.search_service[{seq}]",
                extraction_method="json_service_export",
                captured_at=captured_at,
                event_time=obs_time,
                system_id=system_id,
                resource_id=res_id,
                resource_type="SEARCH_INDEX_ENTRY",
                data_category="SEARCH_INDEX_ENTRY",
                observed_state=state,
                user_id=doc_user,
                matched_identifier=doc_email,
                raw_payload=item,
                semantic_interpretation=f"Search index query: hits={total_hits}",
            )

        elif system_id == "security_service":
            subj_ref = item.get("subject_reference")
            return EvidenceObservation(
                observation_id=obs_id,
                evidence_id=file_id,
                source_file=rel_path,
                source_location=f"service_exports.security_service[{seq}]",
                extraction_method="json_service_export",
                captured_at=captured_at,
                event_time=obs_time,
                system_id=system_id,
                resource_id=res_id,
                resource_type="SECURITY_AUDIT_LOG",
                data_category="SECURITY_AUDIT_LOG",
                observed_state=ObservedState.PRESENT,
                user_id=subj_ref,
                matched_identifier=subj_ref,
                raw_payload=item,
                semantic_interpretation="Security audit record in service export",
            )

        elif system_id == "support_platform":
            req_email = item.get("requester_email")
            user_id = item.get("customer_reference")
            # If email is null and customer_reference is set -> REDACTED
            state = ObservedState.REDACTED if (not req_email and user_id) else ObservedState.PRESENT
            return EvidenceObservation(
                observation_id=obs_id,
                evidence_id=file_id,
                source_file=rel_path,
                source_location=f"service_exports.support_platform[{seq}]",
                extraction_method="json_service_export",
                captured_at=captured_at,
                event_time=obs_time,
                system_id=system_id,
                resource_id=res_id,
                resource_type="SUPPORT_MESSAGE",
                data_category="SUPPORT_MESSAGE",
                observed_state=state,
                user_id=user_id,
                matched_identifier=req_email,
                raw_payload=item,
                semantic_interpretation=f"Support ticket: state={state.value}",
            )

        elif system_id == "export_service":
            owner_email = item.get("owner_email")
            user_id = item.get("customer_reference")
            return EvidenceObservation(
                observation_id=obs_id,
                evidence_id=file_id,
                source_file=rel_path,
                source_location=f"service_exports.export_service[{seq}]",
                extraction_method="json_service_export",
                captured_at=captured_at,
                event_time=obs_time,
                system_id=system_id,
                resource_id=res_id,
                resource_type="USER_EXPORT",
                data_category="USER_EXPORT",
                observed_state=ObservedState.PRESENT,
                user_id=user_id,
                matched_identifier=owner_email,
                raw_payload=item,
                semantic_interpretation="User export in service export",
            )

        return None

    def _parse_snapshot_record(
        self,
        system_id: str,
        collection: str,
        rec: Dict[str, Any],
        file_id: str,
        rel_path: str,
        captured_at: Optional[datetime],
        seq: str,
        snap_time: Optional[datetime] = None,
    ) -> Optional[EvidenceObservation]:
        system_override = rec.get("system") or rec.get("service")
        if system_override:
            system_id = system_override
        res_id = rec.get("resource_id", f"{system_id}_{seq}")
        obs_id = f"{file_id}_{system_id}_{seq}"
        user_id = rec.get("customer_reference") or rec.get("user_id") or rec.get("subject_reference") or rec.get("subject_ref")
        email = (
            rec.get("email")
            or rec.get("owner_email")
            or rec.get("customer_email")
            or rec.get("requester_email")
            or rec.get("lookup_value")
            or rec.get("lookup_key")
        )
        phone = rec.get("phone") or rec.get("owner_phone") or rec.get("requester_phone")
        email_hash = rec.get("email_hash")
        obs_time = parse_iso(rec.get("recorded_at") or rec.get("updated_at") or rec.get("captured_at")) or snap_time or captured_at

        # Determine category
        rec_type = rec.get("record_type")
        if rec_type:
            cat = rec_type
        elif "tombstone" in collection or "deleted_customer" in collection or system_id == "identity_service" or res_id.startswith("tombstone_"):
            cat = "ACCOUNT_TOMBSTONE"
        elif "profile" in collection or system_id == "account_service":
            cat = "USER_PROFILE"
        elif "search" in collection or system_id == "search_service":
            cat = "SEARCH_INDEX_ENTRY"
        elif "analytics" in collection or system_id == "analytics_platform":
            cat = "ANALYTICS_PROFILE"
        elif "support" in collection or system_id == "support_platform":
            is_att = "attachment" in collection.lower()
            cat = "SUPPORT_ATTACHMENT" if is_att else "SUPPORT_MESSAGE"
        elif "export" in collection or system_id == "export_service":
            cat = "USER_EXPORT"
        elif "connector" in collection or system_id == "integration_service":
            cat = "CONNECTOR_SUBSCRIPTION"
        elif "backup" in collection or system_id == "backup_service":
            cat = "BACKUP_ARCHIVE"
        elif "security" in collection or system_id == "security_service":
            cat = "SECURITY_AUDIT_LOG"
        else:
            cat = "USER_PROFILE"

        # Determine state
        res_val = str(rec.get("result", "")).upper()
        if res_val in ("NOT_FOUND", "MISS"):
            state = ObservedState.ABSENT
        elif res_val in ("FOUND", "HIT", "IDENTIFIABLE"):
            state = ObservedState.PRESENT
        elif cat == "ACCOUNT_TOMBSTONE":
            has_pii = bool(email or phone or email_hash)
            state = ObservedState.PRESENT if has_pii else ObservedState.REDACTED
        elif cat == "USER_PROFILE":
            state = ObservedState.PRESENT
            if user_id and not email and not phone:
                cat = "ACCOUNT_TOMBSTONE"
                state = ObservedState.REDACTED
        elif cat == "ANALYTICS_PROFILE":
            state = ObservedState.ANONYMIZED if (not email and not phone and not user_id and not email_hash) else ObservedState.PRESENT
        elif cat in ("SUPPORT_MESSAGE", "SUPPORT_ATTACHMENT"):
            state = ObservedState.REDACTED if (not email and not phone and user_id) else ObservedState.PRESENT
        elif cat == "CONNECTOR_SUBSCRIPTION":
            enabled = rec.get("enabled", False)
            state = ObservedState.ACTIVE if enabled else ObservedState.DISABLED
        elif cat == "BACKUP_ARCHIVE":
            restore_allowed = rec.get("restore_allowed", False)
            state = ObservedState.ACTIVE if restore_allowed else ObservedState.BLOCKED
        else:
            state = ObservedState.PRESENT

        return EvidenceObservation(
            observation_id=obs_id,
            evidence_id=file_id,
            source_file=rel_path,
            source_location=f"snapshots.{collection}[{seq}]",
            extraction_method="json_snapshot_bundle",
            captured_at=captured_at,
            event_time=obs_time,
            system_id=system_id,
            resource_id=res_id,
            resource_type=cat,
            data_category=cat,
            observed_state=state,
            user_id=user_id,
            matched_identifier=email,
            supporting_identifiers=[x for x in [phone, email_hash] if x],
            raw_payload=rec,
            semantic_interpretation=f"Snapshot bundle record in {collection}",
        )

    def _parse_generic_record(
        self,
        rec: Dict[str, Any],
        file_id: str,
        rel_path: str,
        captured_at: Optional[datetime],
        collection: str,
        seq: int,
    ) -> Optional[EvidenceObservation]:
        res_id = rec.get("resource_id", f"record_{seq}")
        obs_id = f"{file_id}_{seq}"
        sys_name = rec.get("system") or rec.get("origin_system") or "account_service"
        rec_type = rec.get("record_type", "")
        result = rec.get("result", "")
        subj_ref = rec.get("subject_reference") or rec.get("customer_reference")
        email = rec.get("owner_email") or rec.get("customer_email") or (subj_ref if "@" in str(subj_ref) else None)
        user_id = subj_ref if subj_ref and not "@" in str(subj_ref) else None
        event_time = parse_iso(rec.get("recorded_at") or rec.get("created_at")) or captured_at

        # Check export jobs
        if "export" in collection.lower() or "export" in rel_path.lower():
            is_avail = rec.get("download_available", True)
            return EvidenceObservation(
                observation_id=obs_id,
                evidence_id=file_id,
                source_file=rel_path,
                source_location=f"records[{seq}]",
                extraction_method="json_records",
                captured_at=captured_at,
                event_time=event_time,
                system_id="export_service",
                resource_id=res_id,
                resource_type="USER_EXPORT",
                data_category="USER_EXPORT",
                observed_state=ObservedState.PRESENT if is_avail else ObservedState.ABSENT,
                user_id=user_id,
                matched_identifier=email,
                raw_payload=rec,
                semantic_interpretation=f"Customer export job: available={is_avail}",
            )

        # Check audit ledger
        if result:
            state = ObservedState.ABSENT if result == "NOT_FOUND" else ObservedState.PRESENT
            return EvidenceObservation(
                observation_id=obs_id,
                evidence_id=file_id,
                source_file=rel_path,
                source_location=f"records[{seq}]",
                extraction_method="json_records",
                captured_at=captured_at,
                event_time=event_time,
                system_id=sys_name,
                resource_id=res_id,
                resource_type=rec_type or "USER_PROFILE",
                data_category=rec_type or "USER_PROFILE",
                observed_state=state,
                user_id=user_id,
                matched_identifier=email,
                raw_payload=rec,
                semantic_interpretation=f"Ledger record check: result={result}",
            )

        return None
