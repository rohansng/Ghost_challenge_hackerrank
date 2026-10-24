"""
SQL / SQLite Evidence Extractor
Executes SQL dumps in SQLite memory databases and extracts structured observations across all tables.
"""

import sqlite3
import os
import json
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


class SqlExtractor:
    def __init__(self, evidence_manifest: Dict[str, Dict[str, Any]]):
        # manifest mapping: relative_file_path -> metadata dict (file_id, captured_at, etc.)
        self.manifest = evidence_manifest

    def extract_from_file(self, full_path: str, rel_path: str) -> List[EvidenceObservation]:
        observations = []
        meta = self.manifest.get(rel_path, {})
        file_id = meta.get("file_id", os.path.basename(full_path))
        captured_at = parse_iso(meta.get("captured_at"))

        conn = sqlite3.connect(":memory:")
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
        except Exception as e:
            conn.close()
            return observations

        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cursor.fetchall()]

        obs_counter = 0

        for t in tables:
            if t == "snapshot_scope":
                continue

            try:
                cursor.execute(f"PRAGMA table_info({t})")
                cols = [r[1] for r in cursor.fetchall()]
                cursor.execute(f"SELECT * FROM {t}")
                rows = cursor.fetchall()
            except Exception:
                continue

            for row in rows:
                obs_counter += 1
                row_dict = dict(zip(cols, row))
                obs = self._parse_row(
                    t, row_dict, file_id, rel_path, captured_at, obs_counter
                )
                if obs:
                    observations.append(obs)

        conn.close()
        return observations

    def _parse_row(
        self,
        table_name: str,
        row: Dict[str, Any],
        file_id: str,
        rel_path: str,
        captured_at: Optional[datetime],
        seq: int,
    ) -> Optional[EvidenceObservation]:
        obs_id = f"{file_id}_{table_name}_{seq}"
        updated_at = parse_iso(row.get("updated_at") or row.get("indexed_at")) or captured_at
        resource_id = row.get("resource_id", f"unknown_{seq}")

        # Check JSON replica tables
        if "customer_data_" in table_name:
            origin_sys = row.get("origin_system", "account_service")
            collection = row.get("collection_name", "")
            record_raw = row.get("record_json", "{}")
            try:
                rec_json = json.loads(record_raw)
            except Exception:
                rec_json = {}

            res_id = rec_json.get("resource_id", resource_id)
            user_id = rec_json.get("user_id") or rec_json.get("customer_reference") or rec_json.get("subject_reference")
            email = rec_json.get("email") or rec_json.get("customer_email") or rec_json.get("requester_email") or rec_json.get("owner_email")
            phone = rec_json.get("phone") or rec_json.get("owner_phone") or rec_json.get("requester_phone")
            email_hash = rec_json.get("email_hash")

            # Determine category & state
            if "analytics" in collection or "analytics" in origin_sys:
                cat = "ANALYTICS_PROFILE"
                # If email/phone/user_id are null -> anonymized
                if not email and not phone and not user_id and not email_hash:
                    state = ObservedState.ANONYMIZED
                else:
                    state = ObservedState.PRESENT
            elif "security" in collection or "security" in origin_sys:
                cat = "SECURITY_AUDIT_LOG"
                state = ObservedState.PRESENT
            elif "support" in collection or "support" in origin_sys:
                cat = "SUPPORT_MESSAGE"
                state = ObservedState.PRESENT
            else:
                cat = "USER_PROFILE"
                state = ObservedState.PRESENT

            return EvidenceObservation(
                observation_id=obs_id,
                evidence_id=file_id,
                source_file=rel_path,
                source_location=f"table:{table_name}",
                extraction_method="sqlite_replica_json",
                captured_at=captured_at,
                event_time=updated_at,
                system_id=origin_sys,
                resource_id=res_id,
                resource_type=cat,
                data_category=cat,
                observed_state=state,
                user_id=user_id,
                matched_identifier=email,
                supporting_identifiers=[x for x in [phone, email_hash] if x],
                raw_payload=rec_json,
                semantic_interpretation=f"Extracted from {table_name} replica snapshot",
            )

        # Standard tables
        if table_name in ("customer_profiles", "customer_profiles_primary", "customer_profiles_failover_replica"):
            cust_ref = row.get("customer_reference") or row.get("user_id")
            email = row.get("email")
            phone = row.get("phone")
            email_hash = row.get("email_hash")
            acc_status = row.get("account_status", "")

            # Check tombstone
            if cust_ref and not email and not phone and not email_hash:
                cat = "ACCOUNT_TOMBSTONE"
                state = ObservedState.REDACTED
            elif email or phone:
                cat = "USER_PROFILE"
                state = ObservedState.PRESENT
            else:
                cat = "USER_PROFILE"
                state = ObservedState.ABSENT if acc_status == "DELETED" else ObservedState.PRESENT

            return EvidenceObservation(
                observation_id=obs_id,
                evidence_id=file_id,
                source_file=rel_path,
                source_location=f"table:{table_name}",
                extraction_method="sqlite_table",
                captured_at=captured_at,
                event_time=updated_at,
                system_id="account_service",
                resource_id=resource_id,
                resource_type=cat,
                data_category=cat,
                observed_state=state,
                user_id=cust_ref,
                matched_identifier=email,
                supporting_identifiers=[x for x in [phone, email_hash] if x],
                raw_payload=row,
                semantic_interpretation=f"Account profile record in {table_name}",
            )

        elif table_name in ("customer_search_documents", "search_documents_primary"):
            email = row.get("email")
            phone = row.get("phone")
            email_hash = row.get("email_hash")
            cust_ref = row.get("customer_reference")
            return EvidenceObservation(
                observation_id=obs_id,
                evidence_id=file_id,
                source_file=rel_path,
                source_location=f"table:{table_name}",
                extraction_method="sqlite_table",
                captured_at=captured_at,
                event_time=updated_at,
                system_id="search_service",
                resource_id=resource_id,
                resource_type="SEARCH_INDEX_ENTRY",
                data_category="SEARCH_INDEX_ENTRY",
                observed_state=ObservedState.PRESENT,
                user_id=cust_ref,
                matched_identifier=email,
                supporting_identifiers=[x for x in [phone, email_hash] if x],
                raw_payload=row,
                semantic_interpretation=f"Search document indexed in {table_name}",
            )

        elif table_name == "customer_analytics_profiles":
            email = row.get("email")
            phone = row.get("phone")
            email_hash = row.get("email_hash")
            cust_ref = row.get("customer_reference")
            if not email and not phone and not cust_ref and not email_hash:
                state = ObservedState.ANONYMIZED
            else:
                state = ObservedState.PRESENT

            return EvidenceObservation(
                observation_id=obs_id,
                evidence_id=file_id,
                source_file=rel_path,
                source_location=f"table:{table_name}",
                extraction_method="sqlite_table",
                captured_at=captured_at,
                event_time=updated_at,
                system_id="analytics_platform",
                resource_id=resource_id,
                resource_type="ANALYTICS_PROFILE",
                data_category="ANALYTICS_PROFILE",
                observed_state=state,
                user_id=cust_ref,
                matched_identifier=email,
                supporting_identifiers=[x for x in [phone, email_hash] if x],
                raw_payload=row,
                semantic_interpretation=f"Analytics profile record in {table_name}",
            )

        elif table_name == "support_records":
            req_email = row.get("requester_email")
            req_phone = row.get("requester_phone")
            req_name = row.get("requester_name")
            cust_ref = row.get("customer_reference")
            excerpt = row.get("message_excerpt", "")

            # Check if attachment or message
            is_attachment = "attachment" in excerpt.lower() or "upload" in excerpt.lower()
            cat = "SUPPORT_ATTACHMENT" if is_attachment else "SUPPORT_MESSAGE"

            # Check if redacted
            if not req_email and not req_phone and not req_name and cust_ref:
                state = ObservedState.REDACTED
            elif req_email or req_phone or req_name:
                state = ObservedState.PRESENT
            else:
                state = ObservedState.ABSENT

            return EvidenceObservation(
                observation_id=obs_id,
                evidence_id=file_id,
                source_file=rel_path,
                source_location=f"table:{table_name}",
                extraction_method="sqlite_table",
                captured_at=captured_at,
                event_time=updated_at,
                system_id="support_platform",
                resource_id=resource_id,
                resource_type=cat,
                data_category=cat,
                observed_state=state,
                user_id=cust_ref,
                matched_identifier=req_email,
                supporting_identifiers=[x for x in [req_phone, req_name] if x],
                raw_payload=row,
                semantic_interpretation=f"Support record in {table_name}",
            )

        elif table_name == "customer_exports":
            owner_email = row.get("owner_email")
            owner_phone = row.get("owner_phone")
            cust_ref = row.get("customer_reference")
            return EvidenceObservation(
                observation_id=obs_id,
                evidence_id=file_id,
                source_file=rel_path,
                source_location=f"table:{table_name}",
                extraction_method="sqlite_table",
                captured_at=captured_at,
                event_time=updated_at,
                system_id="export_service",
                resource_id=resource_id,
                resource_type="USER_EXPORT",
                data_category="USER_EXPORT",
                observed_state=ObservedState.PRESENT,
                user_id=cust_ref,
                matched_identifier=owner_email,
                supporting_identifiers=[x for x in [owner_phone] if x],
                raw_payload=row,
                semantic_interpretation=f"Customer export bundle in {table_name}",
            )

        elif table_name == "connector_subscriptions":
            cust_email = row.get("customer_email")
            cust_ref = row.get("customer_reference")
            enabled = bool(row.get("enabled", 0))
            return EvidenceObservation(
                observation_id=obs_id,
                evidence_id=file_id,
                source_file=rel_path,
                source_location=f"table:{table_name}",
                extraction_method="sqlite_table",
                captured_at=captured_at,
                event_time=updated_at,
                system_id="integration_service",
                resource_id=resource_id,
                resource_type="CONNECTOR_SUBSCRIPTION",
                data_category="CONNECTOR_SUBSCRIPTION",
                observed_state=ObservedState.ACTIVE if enabled else ObservedState.DISABLED,
                user_id=cust_ref,
                matched_identifier=cust_email,
                raw_payload=row,
                semantic_interpretation=f"Integration sync connector (enabled={enabled})",
            )

        elif table_name == "backup_restore_entries":
            cust_email = row.get("customer_email")
            cust_ref = row.get("customer_reference")
            restore_allowed = bool(row.get("restore_allowed", 0))
            return EvidenceObservation(
                observation_id=obs_id,
                evidence_id=file_id,
                source_file=rel_path,
                source_location=f"table:{table_name}",
                extraction_method="sqlite_table",
                captured_at=captured_at,
                event_time=updated_at,
                system_id="backup_service",
                resource_id=resource_id,
                resource_type="BACKUP_ARCHIVE",
                data_category="BACKUP_ARCHIVE",
                observed_state=ObservedState.ACTIVE if restore_allowed else ObservedState.BLOCKED,
                user_id=cust_ref,
                matched_identifier=cust_email,
                raw_payload=row,
                semantic_interpretation=f"Backup restore entry (restore_allowed={restore_allowed})",
            )

        elif table_name == "security_audit_records":
            subj_ref = row.get("subject_reference")
            return EvidenceObservation(
                observation_id=obs_id,
                evidence_id=file_id,
                source_file=rel_path,
                source_location=f"table:{table_name}",
                extraction_method="sqlite_table",
                captured_at=captured_at,
                event_time=updated_at,
                system_id="security_service",
                resource_id=resource_id,
                resource_type="SECURITY_AUDIT_LOG",
                data_category="SECURITY_AUDIT_LOG",
                observed_state=ObservedState.PRESENT,
                user_id=subj_ref,
                matched_identifier=subj_ref,
                raw_payload=row,
                semantic_interpretation=f"Security audit log record in {table_name}",
            )

        return None
