"""
Unit Tests for Policy Engine and Remediation Planner
Tests policy rules, remediation planning, ordering hierarchy, and tie-breaking.
"""

import unittest
from datetime import datetime, timezone
from code.models import Step, Phase, Operation, ResourceState, DeletionStatus
from code.evidence_models import ResourceStateSnapshot, ObservedState
from code.policy_engine import PolicyEngine
from code.remediation_planner import RemediationPlanner


class TestPolicyOrdering(unittest.TestCase):
    def setUp(self):
        self.policy_engine = PolicyEngine()
        self.planner = RemediationPlanner()
        self.dt = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)

    def test_01_user_profile_present_violates_policy(self):
        """USER_PROFILE present must generate REPORT_REMAINING_RECORD, DELETE_RECORD, VERIFY_RECORD_ABSENT."""
        snap = ResourceStateSnapshot(
            system_id="account_service",
            resource_id="account_101",
            data_category="USER_PROFILE",
            proven_state=ObservedState.PRESENT,
            audit_at=self.dt,
            cited_evidence_id="evidence_54",
        )
        res = self.policy_engine.evaluate_resource_policy(snap)
        self.assertFalse(res["is_compliant"])
        self.assertEqual(res["finding"].operation, Operation.REPORT_REMAINING_RECORD)
        self.assertEqual(res["remediation"].operation, Operation.DELETE_RECORD)
        self.assertEqual(res["verification"].operation, Operation.VERIFY_RECORD_ABSENT)

    def test_02_analytics_profile_present_requires_anonymize(self):
        """ANALYTICS_PROFILE with PII must generate REPORT_EXPOSED_PII, ANONYMIZE_RECORD, VERIFY_RECORD_ANONYMIZED."""
        snap = ResourceStateSnapshot(
            system_id="analytics_platform",
            resource_id="analytics_202",
            data_category="ANALYTICS_PROFILE",
            proven_state=ObservedState.PRESENT,
            audit_at=self.dt,
            cited_evidence_id="evidence_56",
        )
        res = self.policy_engine.evaluate_resource_policy(snap)
        self.assertFalse(res["is_compliant"])
        self.assertEqual(res["finding"].operation, Operation.REPORT_EXPOSED_PII)
        self.assertEqual(res["remediation"].operation, Operation.ANONYMIZE_RECORD)
        self.assertEqual(res["verification"].operation, Operation.VERIFY_RECORD_ANONYMIZED)

    def test_03_active_connector_requires_disable(self):
        """CONNECTOR_SUBSCRIPTION active must generate REPORT_ACTIVE_DATA_FLOW, DISABLE_DATA_FLOW, VERIFY_DATA_FLOW_DISABLED."""
        snap = ResourceStateSnapshot(
            system_id="integration_service",
            resource_id="data_flow_303",
            data_category="CONNECTOR_SUBSCRIPTION",
            proven_state=ObservedState.ACTIVE,
            audit_at=self.dt,
            cited_evidence_id="evidence_14",
        )
        res = self.policy_engine.evaluate_resource_policy(snap)
        self.assertFalse(res["is_compliant"])
        self.assertEqual(res["finding"].operation, Operation.REPORT_ACTIVE_DATA_FLOW)
        self.assertEqual(res["remediation"].operation, Operation.DISABLE_DATA_FLOW)
        self.assertEqual(res["verification"].operation, Operation.VERIFY_DATA_FLOW_DISABLED)

    def test_04_restore_risk_requires_block(self):
        """BACKUP_ARCHIVE active must generate REPORT_RESTORE_RISK, BLOCK_RESTORE, VERIFY_RESTORE_BLOCKED."""
        snap = ResourceStateSnapshot(
            system_id="backup_service",
            resource_id="backup_404",
            data_category="BACKUP_ARCHIVE",
            proven_state=ObservedState.ACTIVE,
            audit_at=self.dt,
            cited_evidence_id="evidence_32",
        )
        res = self.policy_engine.evaluate_resource_policy(snap)
        self.assertFalse(res["is_compliant"])
        self.assertEqual(res["finding"].operation, Operation.REPORT_RESTORE_RISK)
        self.assertEqual(res["remediation"].operation, Operation.BLOCK_RESTORE)
        self.assertEqual(res["verification"].operation, Operation.VERIFY_RESTORE_BLOCKED)

    def test_05_retained_audit_log_compliant(self):
        """SECURITY_AUDIT_LOG present evaluates as compliant under rule_12."""
        snap = ResourceStateSnapshot(
            system_id="security_service",
            resource_id="audit_record_505",
            data_category="SECURITY_AUDIT_LOG",
            proven_state=ObservedState.PRESENT,
            audit_at=self.dt,
            cited_evidence_id="evidence_37",
        )
        res = self.policy_engine.evaluate_resource_policy(snap)
        self.assertTrue(res["is_compliant"])
        self.assertIsNone(res["finding"])
        self.assertEqual(res["verification"].operation, Operation.VERIFY_RECORD_PRESENT)

    def test_06_non_deletion_request_outputs_not_applicable(self):
        """Non-deletion request must return NOT_APPLICABLE with empty steps list."""
        status, steps = self.planner.build_plan(
            case_id="case_non_del",
            is_deletion_authorized=False,
            evaluated_resources=[],
        )
        self.assertEqual(status, DeletionStatus.NOT_APPLICABLE)
        self.assertEqual(steps, [])

    def test_07_complete_case_has_only_verifications_with_evidence(self):
        """COMPLETE case contains only verifications citing evidence."""
        snap_acc = ResourceStateSnapshot(
            system_id="account_service",
            resource_id="account_606",
            data_category="USER_PROFILE",
            proven_state=ObservedState.ABSENT,
            audit_at=self.dt,
            cited_evidence_id="evidence_54",
        )
        eval_acc = self.policy_engine.evaluate_resource_policy(snap_acc)
        status, steps = self.planner.build_plan(
            case_id="case_comp",
            is_deletion_authorized=True,
            evaluated_resources=[eval_acc],
        )
        self.assertEqual(status, DeletionStatus.COMPLETE)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].phase, Phase.VERIFICATION)
        self.assertEqual(steps[0].evidence_id, "evidence_54")

    def test_08_incomplete_case_sets_empty_evidence_for_remediation_and_verification(self):
        """INCOMPLETE case must set evidence_id = '' for remediation and future verification."""
        snap_flow = ResourceStateSnapshot(
            system_id="integration_service",
            resource_id="data_flow_707",
            data_category="CONNECTOR_SUBSCRIPTION",
            proven_state=ObservedState.ACTIVE,
            audit_at=self.dt,
            cited_evidence_id="evidence_14",
        )
        eval_flow = self.policy_engine.evaluate_resource_policy(snap_flow)
        status, steps = self.planner.build_plan(
            case_id="case_incomp",
            is_deletion_authorized=True,
            evaluated_resources=[eval_flow],
        )
        self.assertEqual(status, DeletionStatus.INCOMPLETE)
        self.assertEqual(len(steps), 3)
        # Finding retains evidence
        self.assertEqual(steps[0].phase, Phase.FINDING)
        self.assertEqual(steps[0].evidence_id, "evidence_14")
        # Remediation empty
        self.assertEqual(steps[1].phase, Phase.REMEDIATION)
        self.assertEqual(steps[1].evidence_id, "")
        # Verification empty
        self.assertEqual(steps[2].phase, Phase.VERIFICATION)
        self.assertEqual(steps[2].evidence_id, "")

    def test_09_step_numbering_consecutive_from_1(self):
        """Step numbers must start from 1 and increase monotonically without gaps."""
        snap1 = ResourceStateSnapshot(
            system_id="search_service",
            resource_id="search_808",
            data_category="SEARCH_INDEX_ENTRY",
            proven_state=ObservedState.PRESENT,
            audit_at=self.dt,
            cited_evidence_id="evidence_09",
        )
        snap2 = ResourceStateSnapshot(
            system_id="account_service",
            resource_id="account_808",
            data_category="USER_PROFILE",
            proven_state=ObservedState.PRESENT,
            audit_at=self.dt,
            cited_evidence_id="evidence_04",
        )
        eval1 = self.policy_engine.evaluate_resource_policy(snap1)
        eval2 = self.policy_engine.evaluate_resource_policy(snap2)

        status, steps = self.planner.build_plan(
            case_id="case_num",
            is_deletion_authorized=True,
            evaluated_resources=[eval1, eval2],
        )
        self.assertEqual(len(steps), 6)
        for idx, s in enumerate(steps, start=1):
            self.assertEqual(s.step_no, idx)


if __name__ == "__main__":
    unittest.main()
