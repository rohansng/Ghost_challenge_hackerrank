"""
loaders.py - Robust Data Ingestion for Ghost Data Still Exists.
Handles explicit schemas, type normalization, timestamp parsing,
duplicate detection, null checking, and diagnostic logging.
"""

import csv
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

from code.exceptions import DatasetLoadingError
from code.models import (
    UserIdentityRecord,
    AuditLogRecord,
    SystemActivityRecord,
    DeletionRuleRecord,
    EvidenceFileRecord,
    DeletionRequestRecord,
)

logger = logging.getLogger("ghost_data.loaders")


def parse_iso_datetime(dt_str: Optional[str]) -> datetime:
    """Parse ISO 8601 string to timezone-aware UTC datetime."""
    if not dt_str or not dt_str.strip():
        raise ValueError("Cannot parse empty datetime string")
    cleaned = dt_str.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    return datetime.fromisoformat(cleaned).astimezone(timezone.utc)


def normalize_email(email: Optional[str]) -> str:
    """Normalize email address: strip whitespace and lowercase."""
    if not email:
        return ""
    return email.strip().lower()


def normalize_phone(phone: Optional[str]) -> str:
    """Normalize phone number: strip extra whitespace while preserving country code."""
    if not phone:
        return ""
    return " ".join(phone.strip().split())


class DataLoader:
    """Central repository data loader with schema validation and diagnostic tracking."""

    def __init__(self, dataset_dir: str = "dataset"):
        self.dataset_dir = dataset_dir
        self.diagnostics: Dict[str, Any] = {
            "load_errors": [],
            "warnings": [],
            "counts": {},
            "duplicates": {},
        }

    def load_deletion_requests(self, filename: str = "deletion_requests.csv") -> List[DeletionRequestRecord]:
        """Loads and validates deletion requests."""
        path = os.path.join(self.dataset_dir, filename)
        records: List[DeletionRequestRecord] = []
        seen_case_ids: Dict[str, int] = {}
        expected_cols = {"case_id", "email", "requested_at", "reported_status", "reported_at", "audit_at", "request_text"}

        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if not expected_cols.issubset(set(reader.fieldnames or [])):
                missing = expected_cols - set(reader.fieldnames or [])
                raise DatasetLoadingError(f"Missing required columns in {filename}: {missing}")

            for line_no, row in enumerate(reader, start=2):
                cid = row["case_id"].strip()
                if not cid:
                    self.diagnostics["load_errors"].append(f"{filename}:{line_no}: Empty case_id")
                    continue

                if cid in seen_case_ids:
                    self.diagnostics["duplicates"].setdefault(filename, []).append(
                        f"Duplicate case_id {cid} at line {line_no} (previously line {seen_case_ids[cid]})"
                    )
                seen_case_ids[cid] = line_no

                try:
                    record = DeletionRequestRecord(
                        case_id=cid,
                        email=normalize_email(row["email"]),
                        requested_at=parse_iso_datetime(row["requested_at"]),
                        reported_status=row["reported_status"].strip(),
                        reported_at=parse_iso_datetime(row["reported_at"]),
                        audit_at=parse_iso_datetime(row["audit_at"]),
                        request_text=row["request_text"].strip(),
                    )
                    records.append(record)
                except Exception as ex:
                    self.diagnostics["load_errors"].append(f"{filename}:{line_no}: Parse error: {ex}")

        # Deterministic sort by case_id
        records.sort(key=lambda r: int(r.case_id.split("_")[1]) if "_" in r.case_id else r.case_id)
        self.diagnostics["counts"][filename] = len(records)
        return records

    def load_user_identities(self, filename: str = "user_identities.csv") -> Dict[str, UserIdentityRecord]:
        """Loads canonical current user identities keyed by user_id."""
        path = os.path.join(self.dataset_dir, filename)
        identities: Dict[str, UserIdentityRecord] = {}
        seen_emails: Dict[str, str] = {}
        expected_cols = {"user_id", "name", "email", "phone", "email_hash", "updated_at"}

        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if not expected_cols.issubset(set(reader.fieldnames or [])):
                missing = expected_cols - set(reader.fieldnames or [])
                raise DatasetLoadingError(f"Missing required columns in {filename}: {missing}")

            for line_no, row in enumerate(reader, start=2):
                uid = row["user_id"].strip()
                norm_email = normalize_email(row["email"])

                if uid in identities:
                    self.diagnostics["duplicates"].setdefault(filename, []).append(
                        f"Duplicate user_id {uid} at line {line_no}"
                    )
                if norm_email in seen_emails:
                    self.diagnostics["duplicates"].setdefault(filename, []).append(
                        f"Email collision {norm_email} for user {uid} (already claimed by {seen_emails[norm_email]})"
                    )
                seen_emails[norm_email] = uid

                try:
                    record = UserIdentityRecord(
                        user_id=uid,
                        name=row["name"].strip(),
                        email=norm_email,
                        phone=normalize_phone(row["phone"]),
                        email_hash=row["email_hash"].strip(),
                        updated_at=parse_iso_datetime(row["updated_at"]),
                    )
                    identities[uid] = record
                except Exception as ex:
                    self.diagnostics["load_errors"].append(f"{filename}:{line_no}: Parse error: {ex}")

        self.diagnostics["counts"][filename] = len(identities)
        return identities

    def load_user_audit_log(self, filename: str = "user_audit_log.csv") -> List[AuditLogRecord]:
        """Loads historical user audit entries."""
        path = os.path.join(self.dataset_dir, filename)
        records: List[AuditLogRecord] = []
        expected_cols = {"audit_id", "user_id", "event_time", "field_name", "old_value", "new_value"}

        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if not expected_cols.issubset(set(reader.fieldnames or [])):
                missing = expected_cols - set(reader.fieldnames or [])
                raise DatasetLoadingError(f"Missing required columns in {filename}: {missing}")

            for line_no, row in enumerate(reader, start=2):
                aid = row["audit_id"].strip()
                try:
                    record = AuditLogRecord(
                        audit_id=aid,
                        user_id=row["user_id"].strip(),
                        event_time=parse_iso_datetime(row["event_time"]),
                        field_name=row["field_name"].strip(),
                        old_value=row["old_value"].strip(),
                        new_value=row["new_value"].strip(),
                    )
                    records.append(record)
                except Exception as ex:
                    self.diagnostics["load_errors"].append(f"{filename}:{line_no}: Parse error: {ex}")

        # Deterministic sort by event_time, then audit_id
        records.sort(key=lambda r: (r.event_time, r.audit_id))
        self.diagnostics["counts"][filename] = len(records)
        return records

    def load_system_activity(self, filename: str = "system_activity.csv") -> List[SystemActivityRecord]:
        """Loads global operations activity stream."""
        path = os.path.join(self.dataset_dir, filename)
        records: List[SystemActivityRecord] = []
        expected_cols = {
            "activity_id", "event_time", "event_type", "source_system",
            "target_system", "resource_id", "reported_result", "details"
        }

        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if not expected_cols.issubset(set(reader.fieldnames or [])):
                missing = expected_cols - set(reader.fieldnames or [])
                raise DatasetLoadingError(f"Missing required columns in {filename}: {missing}")

            for line_no, row in enumerate(reader, start=2):
                try:
                    record = SystemActivityRecord(
                        activity_id=row["activity_id"].strip(),
                        event_time=parse_iso_datetime(row["event_time"]),
                        event_type=row["event_type"].strip(),
                        source_system=row["source_system"].strip(),
                        target_system=row["target_system"].strip(),
                        resource_id=row["resource_id"].strip(),
                        reported_result=row["reported_result"].strip(),
                        details=row["details"].strip(),
                    )
                    records.append(record)
                except Exception as ex:
                    self.diagnostics["load_errors"].append(f"{filename}:{line_no}: Parse error: {ex}")

        records.sort(key=lambda r: (r.event_time, r.activity_id))
        self.diagnostics["counts"][filename] = len(records)
        return records

    def load_deletion_rules(self, filename: str = "deletion_rules.csv") -> Dict[str, DeletionRuleRecord]:
        """Loads deletion policy specifications."""
        path = os.path.join(self.dataset_dir, filename)
        rules: Dict[str, DeletionRuleRecord] = {}
        expected_cols = {"rule_id", "data_category", "condition", "required_action"}

        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if not expected_cols.issubset(set(reader.fieldnames or [])):
                missing = expected_cols - set(reader.fieldnames or [])
                raise DatasetLoadingError(f"Missing required columns in {filename}: {missing}")

            for line_no, row in enumerate(reader, start=2):
                rid = row["rule_id"].strip()
                try:
                    record = DeletionRuleRecord(
                        rule_id=rid,
                        data_category=row["data_category"].strip(),
                        condition=row["condition"].strip(),
                        required_action=row["required_action"].strip(),
                    )
                    rules[rid] = record
                except Exception as ex:
                    self.diagnostics["load_errors"].append(f"{filename}:{line_no}: Parse error: {ex}")

        self.diagnostics["counts"][filename] = len(rules)
        return rules

    def load_evidence_files(self, filename: str = "evidence_files.csv") -> Dict[str, EvidenceFileRecord]:
        """Loads evidence files manifest."""
        path = os.path.join(self.dataset_dir, filename)
        manifest: Dict[str, EvidenceFileRecord] = {}
        expected_cols = {"file_id", "file_path", "origin", "captured_at"}

        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if not expected_cols.issubset(set(reader.fieldnames or [])):
                missing = expected_cols - set(reader.fieldnames or [])
                raise DatasetLoadingError(f"Missing required columns in {filename}: {missing}")

            for line_no, row in enumerate(reader, start=2):
                fid = row["file_id"].strip()
                try:
                    record = EvidenceFileRecord(
                        file_id=fid,
                        file_path=row["file_path"].strip(),
                        origin=row["origin"].strip(),
                        captured_at=parse_iso_datetime(row["captured_at"]),
                    )
                    manifest[fid] = record
                except Exception as ex:
                    self.diagnostics["load_errors"].append(f"{filename}:{line_no}: Parse error: {ex}")

        self.diagnostics["counts"][filename] = len(manifest)
        return manifest
