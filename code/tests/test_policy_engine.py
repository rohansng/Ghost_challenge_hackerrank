"""
Unit Tests for Phase 3 Policy Engine
Covers all 10 required synthetic scenarios, policy parsing, explainable PolicyProof generation,
retention distinction, and fallback behaviors.
"""

import unittest
from datetime import datetime, timezone

from code.models import Step, Phase, Operation, ResourceState, DeletionStatus
from code.evidence_models import ResourceStateSnapshot, ObservedState
from code.policy_models import PolicyAction, ConditionType, PolicyProof, PolicyRule
from code.policy_engine import PolicyEngine, PolicyParser
from code.remediation_planner import RemediationPlanner


class TestPhase3PolicyEngine(unittest.TestCase):
    def setUp(self):
        self.engine = PolicyEngine(rules_file_path="dataset/deletion_rules.csv")
        self.planner = RemediationPlanner()
        self.dt = datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc)

    # -------------------------------------------------------------
    # 0. Parser Verification
    # -------------------------------------------------------------
    def test_00_policy_parser_loads_authoritative_rules(self):
        """Verifies PolicyParser loads all 15 rules from deletion_rules.csv plus sync rule."""
        parser = PolicyParser("dataset/deletion_rules.csv")
        rules = parser.parse()
        self.assertGreaterEqual(len(rules), 15)
        for i in range(1, 16):
            rid = f"rule_{i:02d}"
            self.assertIn(rid, rules, f"Missing rule {rid}")
        self.assertIn("rule_sync", rules)
        self.assertEqual(rules["rule_01"].required_action, PolicyAction.DELETE)
        self.assertEqual(rules["rule_05"].required_action, PolicyAction.REDACT)
        self.assertEqual(rules["rule_07"].required_action, PolicyAction.ANONYMIZE)
        self.assertEqual(rules["rule_12"].required_action, PolicyAction.RETAIN)
        self.assertEqual(rules["rule_14"].required_action, PolicyAction.RETAIN)
        self.assertEqual(rules["rule_15"].data_category, "ACCOUNT_TOMBSTONE")

    # -------------------------------------------------------------
    # 1. Correct Deletion
    # -------------------------------------------------------------
    def test_01_correct_deletion(self):
        """USER_PROFILE verified absent at audit_at produces compliant status and VERIFY_RECORD_ABSENT."""
        snap = ResourceStateSnapshot(
            system_id="account_service",
            resource_id="account_101",
            data_category="USER_PROFILE",
            proven_state=ObservedState.ABSENT,
            audit_at=self.dt,
            cited_evidence_id="evidence_54",
        )
        proof = self.engine.evaluate_resource_policy(snap)
        self.assertTrue(proof.is_compliant)
        self.assertFalse(proof.has_prohibited_pii)
        self.assertFalse(proof.is_retention_permitted)
        self.assertIsNone(proof.finding_step)
        self.assertIsNone(proof.remediation_step)
        self.assertIsNotNone(proof.verification_step)
        self.assertEqual(proof.verification_step.operation, Operation.VERIFY_RECORD_ABSENT)
        self.assertEqual(proof.verification_step.state, ResourceState.ABSENT)
        self.assertEqual(proof.verification_step.evidence_id, "evidence_54")

    # -------------------------------------------------------------
    # 2. Incomplete Deletion
    # -------------------------------------------------------------
    def test_02_incomplete_deletion(self):
        """USER_PROFILE present at audit_at produces REPORT_REMAINING_RECORD, DELETE_RECORD, VERIFY_RECORD_ABSENT."""
        snap = ResourceStateSnapshot(
            system_id="account_service",
            resource_id="account_102",
            data_category="USER_PROFILE",
            proven_state=ObservedState.PRESENT,
            audit_at=self.dt,
            cited_evidence_id="evidence_54",
        )
        proof = self.engine.evaluate_resource_policy(snap)
        self.assertFalse(proof.is_compliant)
        self.assertTrue(proof.has_prohibited_pii)
        self.assertIsNotNone(proof.failure_reason)
        self.assertEqual(proof.finding_step.operation, Operation.REPORT_REMAINING_RECORD)
        self.assertEqual(proof.finding_step.state, ResourceState.PRESENT)
        self.assertEqual(proof.finding_step.evidence_id, "evidence_54")
        self.assertEqual(proof.remediation_step.operation, Operation.DELETE_RECORD)
        self.assertEqual(proof.remediation_step.state, ResourceState.ABSENT)
        self.assertEqual(proof.verification_step.operation, Operation.VERIFY_RECORD_ABSENT)

    # -------------------------------------------------------------
    # 3. Required Retention
    # -------------------------------------------------------------
    def test_03_required_retention(self):
        """SECURITY_AUDIT_LOG within retention window is compliant and verified present."""
        snap = ResourceStateSnapshot(
            system_id="security_service",
            resource_id="audit_log_301",
            data_category="SECURITY_AUDIT_LOG",
            proven_state=ObservedState.PRESENT,
            audit_at=self.dt,
            cited_evidence_id="evidence_37",
            metadata={"retention_expired": False, "has_prohibited_pii": False},
        )
        proof = self.engine.evaluate_resource_policy(snap)
        self.assertTrue(proof.is_compliant)
        self.assertTrue(proof.is_retention_permitted)
        self.assertFalse(proof.has_prohibited_pii)
        self.assertIsNone(proof.finding_step)
        self.assertEqual(proof.verification_step.operation, Operation.VERIFY_RECORD_PRESENT)
        self.assertEqual(proof.verification_step.state, ResourceState.PRESENT)
        self.assertEqual(proof.verification_step.evidence_id, "evidence_37")

    # -------------------------------------------------------------
    # 4. Allowed Anonymization
    # -------------------------------------------------------------
    def test_04_allowed_anonymization(self):
        """ANALYTICS_PROFILE in ANONYMIZED state satisfies policy and produces VERIFY_RECORD_ANONYMIZED."""
        snap = ResourceStateSnapshot(
            system_id="analytics_platform",
            resource_id="analytics_401",
            data_category="ANALYTICS_PROFILE",
            proven_state=ObservedState.ANONYMIZED,
            audit_at=self.dt,
            cited_evidence_id="evidence_56",
            metadata={"attributable": False},
        )
        proof = self.engine.evaluate_resource_policy(snap)
        self.assertTrue(proof.is_compliant)
        self.assertTrue(proof.is_retention_permitted)
        self.assertFalse(proof.has_prohibited_pii)
        self.assertIsNone(proof.finding_step)
        self.assertEqual(proof.verification_step.operation, Operation.VERIFY_RECORD_ANONYMIZED)
        self.assertEqual(proof.verification_step.state, ResourceState.ANONYMIZED)

    # -------------------------------------------------------------
    # 5. Required Redaction
    # -------------------------------------------------------------
    def test_05_required_redaction(self):
        """SUPPORT_MESSAGE in REDACTED state satisfies policy while preserving conversation context."""
        snap = ResourceStateSnapshot(
            system_id="support_platform",
            resource_id="ticket_501",
            data_category="SUPPORT_MESSAGE",
            proven_state=ObservedState.REDACTED,
            audit_at=self.dt,
            cited_evidence_id="evidence_22",
            metadata={"has_prohibited_pii": False},
        )
        proof = self.engine.evaluate_resource_policy(snap)
        self.assertTrue(proof.is_compliant)
        self.assertTrue(proof.is_retention_permitted)
        self.assertFalse(proof.has_prohibited_pii)
        self.assertIsNone(proof.finding_step)
        self.assertEqual(proof.verification_step.operation, Operation.VERIFY_RECORD_REDACTED)
        self.assertEqual(proof.verification_step.state, ResourceState.REDACTED)

    # -------------------------------------------------------------
    # 6. Prohibited Identifier Remaining
    # -------------------------------------------------------------
    def test_06_prohibited_identifier_remaining(self):
        """SUPPORT_MESSAGE with unredacted PII triggers REPORT_EXPOSED_PII and REDACT_RECORD."""
        snap = ResourceStateSnapshot(
            system_id="support_platform",
            resource_id="ticket_601",
            data_category="SUPPORT_MESSAGE",
            proven_state=ObservedState.PRESENT,
            audit_at=self.dt,
            cited_evidence_id="evidence_22",
            metadata={"has_prohibited_pii": True},
        )
        proof = self.engine.evaluate_resource_policy(snap)
        self.assertFalse(proof.is_compliant)
        self.assertTrue(proof.has_prohibited_pii)
        self.assertEqual(proof.finding_step.operation, Operation.REPORT_EXPOSED_PII)
        self.assertEqual(proof.finding_step.state, ResourceState.PRESENT)
        self.assertEqual(proof.remediation_step.operation, Operation.REDACT_RECORD)
        self.assertEqual(proof.remediation_step.state, ResourceState.REDACTED)
        self.assertEqual(proof.verification_step.operation, Operation.VERIFY_RECORD_REDACTED)

    # -------------------------------------------------------------
    # 7. Multiple Policies & Composite Plan
    # -------------------------------------------------------------
    def test_07_multiple_policies(self):
        """Evaluates composite case with 5 disparate resources across full lifecycle."""
        snapshots = [
            ResourceStateSnapshot(
                system_id="account_service",
                resource_id="acc_701",
                data_category="USER_PROFILE",
                proven_state=ObservedState.PRESENT,
                audit_at=self.dt,
                cited_evidence_id="ev_01",
            ),
            ResourceStateSnapshot(
                system_id="support_platform",
                resource_id="msg_702",
                data_category="SUPPORT_MESSAGE",
                proven_state=ObservedState.PRESENT,
                audit_at=self.dt,
                cited_evidence_id="ev_02",
            ),
            ResourceStateSnapshot(
                system_id="security_service",
                resource_id="sec_703",
                data_category="SECURITY_AUDIT_LOG",
                proven_state=ObservedState.PRESENT,
                audit_at=self.dt,
                cited_evidence_id="ev_03",
            ),
            ResourceStateSnapshot(
                system_id="backup_service",
                resource_id="bak_704",
                data_category="BACKUP_ARCHIVE",
                proven_state=ObservedState.ACTIVE,
                audit_at=self.dt,
                cited_evidence_id="ev_04",
            ),
            ResourceStateSnapshot(
                system_id="integration_service",
                resource_id="flow_705",
                data_category="CONNECTOR_SUBSCRIPTION",
                proven_state=ObservedState.ACTIVE,
                audit_at=self.dt,
                cited_evidence_id="ev_05",
            ),
        ]

        evaluated = [self.engine.evaluate_resource_policy(s) for s in snapshots]
        status, steps = self.planner.build_plan(
            case_id="case_synth_07",
            is_deletion_authorized=True,
            evaluated_resources=evaluated,
        )

        self.assertEqual(status, DeletionStatus.INCOMPLETE)
        # Verify strict phase ordering: FINDING -> REMEDIATION -> VERIFICATION
        phases = [s.phase for s in steps]
        finding_indices = [i for i, p in enumerate(phases) if p == Phase.FINDING]
        remed_indices = [i for i, p in enumerate(phases) if p == Phase.REMEDIATION]
        verif_indices = [i for i, p in enumerate(phases) if p == Phase.VERIFICATION]

        self.assertLess(max(finding_indices), min(remed_indices))
        self.assertLess(max(remed_indices), min(verif_indices))

        # Check remediation ordering: DISABLE_DATA_FLOW (1) -> BLOCK_RESTORE (2) -> DELETE_RECORD (3) -> REDACT_RECORD (4)
        remed_ops = [s.operation for s in steps if s.phase == Phase.REMEDIATION]
        expected_order = [
            Operation.DISABLE_DATA_FLOW,
            Operation.BLOCK_RESTORE,
            Operation.DELETE_RECORD,
            Operation.REDACT_RECORD,
        ]
        self.assertEqual(remed_ops, expected_order)

    # -------------------------------------------------------------
    # 8. Conflicting Policy Conditions (Tombstone vs Wipe)
    # -------------------------------------------------------------
    def test_08_conflicting_policy_conditions(self):
        """Account tombstone permits stable internal user_id while requiring direct PII redaction."""
        # Scenario A: Account tombstone still exposing direct email/phone
        snap_unredacted = ResourceStateSnapshot(
            system_id="account_service",
            resource_id="tombstone_801",
            data_category="ACCOUNT_TOMBSTONE",
            proven_state=ObservedState.PRESENT,
            audit_at=self.dt,
            cited_evidence_id="ev_15",
            metadata={"has_prohibited_pii": True},
        )
        proof_unredacted = self.engine.evaluate_resource_policy(snap_unredacted)
        self.assertFalse(proof_unredacted.is_compliant)
        self.assertEqual(proof_unredacted.finding_step.operation, Operation.REPORT_EXPOSED_PII)
        self.assertEqual(proof_unredacted.remediation_step.operation, Operation.REDACT_RECORD)
        self.assertEqual(proof_unredacted.verification_step.operation, Operation.VERIFY_RECORD_REDACTED)

        # Scenario B: Properly tombstoned account
        snap_tombstoned = ResourceStateSnapshot(
            system_id="account_service",
            resource_id="tombstone_802",
            data_category="ACCOUNT_TOMBSTONE",
            proven_state=ObservedState.REDACTED,
            audit_at=self.dt,
            cited_evidence_id="ev_15",
            metadata={"has_prohibited_pii": False},
        )
        proof_tombstoned = self.engine.evaluate_resource_policy(snap_tombstoned)
        self.assertTrue(proof_tombstoned.is_compliant)
        self.assertEqual(proof_tombstoned.verification_step.operation, Operation.VERIFY_RECORD_REDACTED)

    # -------------------------------------------------------------
    # 9. Unknown Resource Type
    # -------------------------------------------------------------
    def test_09_unknown_resource_type(self):
        """Unknown resource category defaults to safe deletion requirement without crashing."""
        snap = ResourceStateSnapshot(
            system_id="feature_store",
            resource_id="feature_901",
            data_category="EXPERIMENTAL_VECTOR_EMBEDDING",
            proven_state=ObservedState.PRESENT,
            audit_at=self.dt,
            cited_evidence_id="ev_unknown",
        )
        proof = self.engine.evaluate_resource_policy(snap)
        self.assertFalse(proof.is_compliant)
        self.assertEqual(proof.rule_id, "rule_unknown")
        self.assertEqual(proof.finding_step.operation, Operation.REPORT_REMAINING_RECORD)
        self.assertEqual(proof.remediation_step.operation, Operation.DELETE_RECORD)
        self.assertEqual(proof.verification_step.operation, Operation.VERIFY_RECORD_ABSENT)

    # -------------------------------------------------------------
    # 10. Missing Rule Fallback
    # -------------------------------------------------------------
    def test_10_missing_rule(self):
        """Evaluator handles empty ruleset with explainable fallback and diagnostic recording."""
        empty_engine = PolicyEngine(rules_file_path="nonexistent_rules_file.csv")
        # Empty out its rules map explicitly to test missing rule fallback
        empty_engine.rules.clear()

        snap = ResourceStateSnapshot(
            system_id="custom_service",
            resource_id="custom_1001",
            data_category="CUSTOM_METRIC",
            proven_state=ObservedState.ABSENT,
            audit_at=self.dt,
            cited_evidence_id="ev_custom",
        )
        proof = empty_engine.evaluate_resource_policy(snap)
        self.assertTrue(proof.is_compliant)
        self.assertEqual(proof.rule_id, "rule_unknown")
        self.assertEqual(proof.verification_step.operation, Operation.VERIFY_RECORD_ABSENT)

    # -------------------------------------------------------------
    # 11. PolicyProof Explainability & Access
    # -------------------------------------------------------------
    def test_11_policy_proof_explainability_and_dict_access(self):
        """Confirms PolicyProof provides all required fields, properties, and dict-like access."""
        snap = ResourceStateSnapshot(
            system_id="account_service",
            resource_id="acc_1101",
            data_category="USER_PROFILE",
            proven_state=ObservedState.PRESENT,
            audit_at=self.dt,
            cited_evidence_id="ev_11",
        )
        proof = self.engine.evaluate_resource_policy(snap)
        d = proof.to_dict()

        self.assertIn("required_action", d)
        self.assertIn("actual_state", d)
        self.assertIn("policy_condition", d)
        self.assertIn("proof", d)
        self.assertIn("failure_reason", d)
        self.assertIn("is_compliant", d)
        self.assertIn("has_prohibited_pii", d)
        self.assertIn("is_retention_permitted", d)

        # Dict indexing compatibility
        self.assertEqual(proof["finding"].operation, Operation.REPORT_REMAINING_RECORD)
        self.assertEqual(proof.get("remediation").operation, Operation.DELETE_RECORD)
        self.assertEqual(proof.get("verification").operation, Operation.VERIFY_RECORD_ABSENT)
        self.assertFalse(proof.get("is_compliant"))


if __name__ == "__main__":
    unittest.main()
