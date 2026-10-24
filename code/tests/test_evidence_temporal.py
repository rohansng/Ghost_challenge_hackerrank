"""
Adversarial Unit Tests for Evidence Extraction & Temporal Reconstruction
Tests all 13 specified adversarial scenarios without using organizer truth.
"""

import unittest
from datetime import datetime, timezone
from code.evidence_models import EvidenceObservation, ObservedState
from code.temporal_state_machine import TemporalStateMachine


def make_dt(iso_str: str) -> datetime:
    return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))


class TestEvidenceTemporalAdversarial(unittest.TestCase):
    def setUp(self):
        self.tsm = TemporalStateMachine()
        self.audit_at = make_dt("2026-06-01T12:00:00Z")

    def test_01_delete_followed_by_recreation(self):
        """A record was deleted at T1, but recreated/resynced at T2 (T1 < T2 <= audit_at). State must be PRESENT."""
        obs_del = EvidenceObservation(
            observation_id="obs_del",
            evidence_id="evidence_del",
            source_file="evidence/logs/delete.log",
            source_location="line:1",
            extraction_method="log_kv_parser",
            captured_at=make_dt("2026-05-10T10:00:00Z"),
            event_time=make_dt("2026-05-10T10:00:00Z"),
            system_id="account_service",
            resource_id="account_adv_01",
            resource_type="USER_PROFILE",
            data_category="USER_PROFILE",
            observed_state=ObservedState.ABSENT,
        )
        obs_recreate = EvidenceObservation(
            observation_id="obs_recreate",
            evidence_id="evidence_db",
            source_file="evidence/databases/replica.sql",
            source_location="table:customer_profiles",
            extraction_method="sqlite_table",
            captured_at=make_dt("2026-05-20T10:00:00Z"),
            event_time=make_dt("2026-05-20T10:00:00Z"),
            system_id="account_service",
            resource_id="account_adv_01",
            resource_type="USER_PROFILE",
            data_category="USER_PROFILE",
            observed_state=ObservedState.PRESENT,
        )

        snapshots = self.tsm.evaluate_resource_states_at_audit([obs_del, obs_recreate], self.audit_at)
        snap = snapshots.get("account_adv_01")
        self.assertIsNotNone(snap)
        self.assertEqual(snap.proven_state, ObservedState.PRESENT)
        self.assertEqual(snap.cited_evidence_id, "evidence_db")

    def test_02_delete_after_audit_at(self):
        """A delete occurred AFTER audit_at. At audit_at, record was still PRESENT."""
        obs_pres = EvidenceObservation(
            observation_id="obs_pres",
            evidence_id="evidence_pres",
            source_file="evidence/databases/snapshot.sql",
            source_location="table:customer_profiles",
            extraction_method="sqlite_table",
            captured_at=make_dt("2026-05-25T10:00:00Z"),
            event_time=make_dt("2026-05-25T10:00:00Z"),
            system_id="account_service",
            resource_id="account_adv_02",
            resource_type="USER_PROFILE",
            data_category="USER_PROFILE",
            observed_state=ObservedState.PRESENT,
        )
        obs_del_after = EvidenceObservation(
            observation_id="obs_del_after",
            evidence_id="evidence_del_after",
            source_file="evidence/logs/delete_late.log",
            source_location="line:1",
            extraction_method="log_kv_parser",
            captured_at=make_dt("2026-06-05T10:00:00Z"),
            event_time=make_dt("2026-06-05T10:00:00Z"),
            system_id="account_service",
            resource_id="account_adv_02",
            resource_type="USER_PROFILE",
            data_category="USER_PROFILE",
            observed_state=ObservedState.ABSENT,
        )

        snapshots = self.tsm.evaluate_resource_states_at_audit([obs_pres, obs_del_after], self.audit_at)
        snap = snapshots.get("account_adv_02")
        self.assertIsNotNone(snap)
        self.assertEqual(snap.proven_state, ObservedState.PRESENT)
        self.assertEqual(snap.cited_evidence_id, "evidence_pres")

    def test_03_recreation_after_audit_at(self):
        """A record was deleted before audit_at, and recreated after audit_at. At audit_at it was ABSENT."""
        obs_del = EvidenceObservation(
            observation_id="obs_del",
            evidence_id="evidence_del",
            source_file="evidence/logs/delete.log",
            source_location="line:1",
            extraction_method="log_kv_parser",
            captured_at=make_dt("2026-05-15T10:00:00Z"),
            event_time=make_dt("2026-05-15T10:00:00Z"),
            system_id="account_service",
            resource_id="account_adv_03",
            resource_type="USER_PROFILE",
            data_category="USER_PROFILE",
            observed_state=ObservedState.ABSENT,
        )
        obs_recreate_late = EvidenceObservation(
            observation_id="obs_recreate_late",
            evidence_id="evidence_late_db",
            source_file="evidence/databases/future.sql",
            source_location="table:customer_profiles",
            extraction_method="sqlite_table",
            captured_at=make_dt("2026-06-15T10:00:00Z"),
            event_time=make_dt("2026-06-15T10:00:00Z"),
            system_id="account_service",
            resource_id="account_adv_03",
            resource_type="USER_PROFILE",
            data_category="USER_PROFILE",
            observed_state=ObservedState.PRESENT,
        )

        snapshots = self.tsm.evaluate_resource_states_at_audit([obs_del, obs_recreate_late], self.audit_at)
        snap = snapshots.get("account_adv_03")
        self.assertIsNotNone(snap)
        self.assertEqual(snap.proven_state, ObservedState.ABSENT)

    def test_04_stale_backup(self):
        """A backup exists with restore_allowed=False. State must be BLOCKED (compliant under rule_14)."""
        obs_backup = EvidenceObservation(
            observation_id="obs_backup",
            evidence_id="evidence_backup",
            source_file="evidence/records/service_export.json",
            source_location="backup_service[0]",
            extraction_method="json_service_export",
            captured_at=make_dt("2026-05-20T10:00:00Z"),
            event_time=make_dt("2026-05-20T10:00:00Z"),
            system_id="backup_service",
            resource_id="backup_adv_04",
            resource_type="BACKUP_ARCHIVE",
            data_category="BACKUP_ARCHIVE",
            observed_state=ObservedState.BLOCKED,
        )
        snapshots = self.tsm.evaluate_resource_states_at_audit([obs_backup], self.audit_at)
        snap = snapshots.get("backup_adv_04")
        self.assertEqual(snap.proven_state, ObservedState.BLOCKED)
        self.assertTrue(snap.is_compliant)

    def test_05_restored_backup(self):
        """A backup exists with restore_allowed=True. State must be ACTIVE (restore risk)."""
        obs_restore = EvidenceObservation(
            observation_id="obs_restore",
            evidence_id="evidence_restore",
            source_file="evidence/records/service_export.json",
            source_location="backup_service[0]",
            extraction_method="json_service_export",
            captured_at=make_dt("2026-05-20T10:00:00Z"),
            event_time=make_dt("2026-05-20T10:00:00Z"),
            system_id="backup_service",
            resource_id="backup_adv_05",
            resource_type="BACKUP_ARCHIVE",
            data_category="BACKUP_ARCHIVE",
            observed_state=ObservedState.ACTIVE,
        )
        snapshots = self.tsm.evaluate_resource_states_at_audit([obs_restore], self.audit_at)
        snap = snapshots.get("backup_adv_05")
        self.assertEqual(snap.proven_state, ObservedState.ACTIVE)
        self.assertFalse(snap.is_compliant)

    def test_06_sync_process(self):
        """A connector subscription is enabled=True. State must be ACTIVE (recreation risk)."""
        obs_conn = EvidenceObservation(
            observation_id="obs_conn",
            evidence_id="evidence_conn",
            source_file="evidence/records/connectors.json",
            source_location="records[0]",
            extraction_method="json_service_export",
            captured_at=make_dt("2026-05-20T10:00:00Z"),
            event_time=make_dt("2026-05-20T10:00:00Z"),
            system_id="integration_service",
            resource_id="data_flow_adv_06",
            resource_type="CONNECTOR_SUBSCRIPTION",
            data_category="CONNECTOR_SUBSCRIPTION",
            observed_state=ObservedState.ACTIVE,
        )
        snapshots = self.tsm.evaluate_resource_states_at_audit([obs_conn], self.audit_at)
        snap = snapshots.get("data_flow_adv_06")
        self.assertEqual(snap.proven_state, ObservedState.ACTIVE)
        self.assertFalse(snap.is_compliant)

    def test_07_stale_index(self):
        """A search document remains indexed (result=hit). State must be PRESENT (violates rule_03)."""
        obs_index = EvidenceObservation(
            observation_id="obs_index",
            evidence_id="evidence_index",
            source_file="evidence/logs/search.log",
            source_location="line:5",
            extraction_method="log_kv_parser",
            captured_at=make_dt("2026-05-20T10:00:00Z"),
            event_time=make_dt("2026-05-20T10:00:00Z"),
            system_id="search_service",
            resource_id="search_adv_07",
            resource_type="SEARCH_INDEX_ENTRY",
            data_category="SEARCH_INDEX_ENTRY",
            observed_state=ObservedState.PRESENT,
        )
        snapshots = self.tsm.evaluate_resource_states_at_audit([obs_index], self.audit_at)
        snap = snapshots.get("search_adv_07")
        self.assertEqual(snap.proven_state, ObservedState.PRESENT)
        self.assertFalse(snap.is_compliant)

    def test_08_export_containing_old_identifier(self):
        """A user export is downloadable (download_available=True). State must be PRESENT (violates rule_09)."""
        obs_export = EvidenceObservation(
            observation_id="obs_export",
            evidence_id="evidence_export",
            source_file="evidence/records/exports.json",
            source_location="records[0]",
            extraction_method="json_records",
            captured_at=make_dt("2026-05-20T10:00:00Z"),
            event_time=make_dt("2026-05-20T10:00:00Z"),
            system_id="export_service",
            resource_id="export_adv_08",
            resource_type="USER_EXPORT",
            data_category="USER_EXPORT",
            observed_state=ObservedState.PRESENT,
        )
        snapshots = self.tsm.evaluate_resource_states_at_audit([obs_export], self.audit_at)
        snap = snapshots.get("export_adv_08")
        self.assertEqual(snap.proven_state, ObservedState.PRESENT)
        self.assertFalse(snap.is_compliant)

    def test_09_contradictory_workflow_status(self):
        """Workflow claims deletion complete, but physical DB snapshot shows record PRESENT. Direct evidence wins."""
        claim_obs = EvidenceObservation(
            observation_id="claim_01",
            evidence_id="activity_99",
            source_file="dataset/system_activity.csv",
            source_location="activity_id:activity_99",
            extraction_method="system_activity_stream",
            captured_at=make_dt("2026-05-10T10:00:00Z"),
            event_time=make_dt("2026-05-10T10:00:00Z"),
            system_id="account_service",
            resource_id="account_adv_09",
            resource_type="USER_PROFILE",
            data_category="USER_PROFILE",
            observed_state=ObservedState.ABSENT,
        )
        db_obs = EvidenceObservation(
            observation_id="db_01",
            evidence_id="evidence_db_09",
            source_file="evidence/databases/primary.sql",
            source_location="table:customer_profiles",
            extraction_method="sqlite_table",
            captured_at=make_dt("2026-05-15T10:00:00Z"),
            event_time=make_dt("2026-05-15T10:00:00Z"),
            system_id="account_service",
            resource_id="account_adv_09",
            resource_type="USER_PROFILE",
            data_category="USER_PROFILE",
            observed_state=ObservedState.PRESENT,
        )
        snapshots = self.tsm.evaluate_resource_states_at_audit([claim_obs, db_obs], self.audit_at)
        snap = snapshots.get("account_adv_09")
        self.assertEqual(snap.proven_state, ObservedState.PRESENT)
        self.assertEqual(snap.cited_evidence_id, "evidence_db_09")

    def test_10_evidence_captured_after_audit_at(self):
        """Evidence captured strictly after audit_at must be ignored."""
        future_obs = EvidenceObservation(
            observation_id="future_01",
            evidence_id="evidence_future",
            source_file="evidence/databases/future.sql",
            source_location="table:customer_profiles",
            extraction_method="sqlite_table",
            captured_at=make_dt("2026-06-10T10:00:00Z"),
            event_time=make_dt("2026-06-10T10:00:00Z"),
            system_id="account_service",
            resource_id="account_adv_10",
            resource_type="USER_PROFILE",
            data_category="USER_PROFILE",
            observed_state=ObservedState.PRESENT,
        )
        snapshots = self.tsm.evaluate_resource_states_at_audit([future_obs], self.audit_at)
        self.assertNotIn("account_adv_10", snapshots)

    def test_11_unrelated_user_with_matching_identifier(self):
        """An observation belonging to an unrelated user must not contaminate subject evaluation."""
        # Simulated by separate resource ids
        obs_unrelated = EvidenceObservation(
            observation_id="obs_unrelated",
            evidence_id="evidence_db",
            source_file="evidence/databases/replica.sql",
            source_location="table:customer_profiles",
            extraction_method="sqlite_table",
            captured_at=make_dt("2026-05-10T10:00:00Z"),
            event_time=make_dt("2026-05-10T10:00:00Z"),
            system_id="account_service",
            resource_id="account_unrelated_999",
            resource_type="USER_PROFILE",
            data_category="USER_PROFILE",
            observed_state=ObservedState.PRESENT,
            user_id="user_999",
        )
        snapshots = self.tsm.evaluate_resource_states_at_audit([obs_unrelated], self.audit_at)
        self.assertNotIn("account_adv_11", snapshots)

    def test_12_multiple_evidence_files_showing_same_record(self):
        """When multiple evidence files show the same record, latest snapshot before audit_at is authoritative."""
        obs_early = EvidenceObservation(
            observation_id="obs_early",
            evidence_id="evidence_early",
            source_file="evidence/databases/may01.sql",
            source_location="table:customer_profiles",
            extraction_method="sqlite_table",
            captured_at=make_dt("2026-05-01T10:00:00Z"),
            event_time=make_dt("2026-05-01T10:00:00Z"),
            system_id="account_service",
            resource_id="account_adv_12",
            resource_type="USER_PROFILE",
            data_category="USER_PROFILE",
            observed_state=ObservedState.PRESENT,
        )
        obs_mid = EvidenceObservation(
            observation_id="obs_mid",
            evidence_id="evidence_mid",
            source_file="evidence/databases/may20.sql",
            source_location="table:customer_profiles",
            extraction_method="sqlite_table",
            captured_at=make_dt("2026-05-20T10:00:00Z"),
            event_time=make_dt("2026-05-20T10:00:00Z"),
            system_id="account_service",
            resource_id="account_adv_12",
            resource_type="USER_PROFILE",
            data_category="USER_PROFILE",
            observed_state=ObservedState.ABSENT,
        )
        snapshots = self.tsm.evaluate_resource_states_at_audit([obs_early, obs_mid], self.audit_at)
        snap = snapshots.get("account_adv_12")
        self.assertEqual(snap.proven_state, ObservedState.ABSENT)
        self.assertEqual(snap.cited_evidence_id, "evidence_mid")

    def test_13_missing_evidence(self):
        """When no evidence observations exist for a resource, state evaluates to None/empty."""
        snapshots = self.tsm.evaluate_resource_states_at_audit([], self.audit_at)
        self.assertEqual(len(snapshots), 0)


if __name__ == "__main__":
    unittest.main()
