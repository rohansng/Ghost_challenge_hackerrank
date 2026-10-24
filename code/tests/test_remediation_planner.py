"""
test_remediation_planner.py - Step Planner & Deterministic Ordering Test Suite.
Validates the 12 required test conditions:
1. No steps
2. One finding
3. Multiple findings
4. Remediation ordering
5. Verification ordering
6. Mixed phases
7. Identical system/resource names
8. Ordering ties
9. Duplicate evidence/steps
10. Invalid evidence IDs
11. COMPLETE evidence preservation
12. INCOMPLETE empty evidence IDs
"""

import unittest
from code.models import Step, Phase, Operation, DeletionStatus
from code.evidence_models import ObservedState
from code.remediation_planner import RemediationPlanner, StepValidator


class TestRemediationPlanner(unittest.TestCase):
    def setUp(self):
        self.planner = RemediationPlanner()

    def test_01_no_steps(self):
        """1. No steps: Non-deletion request produces empty steps list."""
        status, steps = self.planner.build_plan(
            case_id="case_01",
            is_deletion_authorized=False,
            evaluated_resources=[],
        )
        self.assertEqual(status, DeletionStatus.NOT_APPLICABLE)
        self.assertEqual(steps, [])

    def test_02_one_finding(self):
        """2. One finding: Generates finding, remediation, and verification with consecutive numbering."""
        res_eval = {
            "finding": Step(0, Phase.FINDING, "account_service", "account_1", Operation.REPORT_REMAINING_RECORD, ObservedState.PRESENT, "evidence_01"),
            "remediation": Step(0, Phase.REMEDIATION, "account_service", "account_1", Operation.DELETE_RECORD, ObservedState.ABSENT, ""),
            "verification": Step(0, Phase.VERIFICATION, "account_service", "account_1", Operation.VERIFY_RECORD_ABSENT, ObservedState.ABSENT, ""),
        }
        status, steps = self.planner.build_plan(
            case_id="case_02",
            is_deletion_authorized=True,
            evaluated_resources=[res_eval],
        )
        self.assertEqual(status, DeletionStatus.INCOMPLETE)
        self.assertEqual(len(steps), 3)
        self.assertEqual([s.step_no for s in steps], [1, 2, 3])
        self.assertEqual([s.phase for s in steps], [Phase.FINDING, Phase.REMEDIATION, Phase.VERIFICATION])
        self.assertEqual(steps[0].evidence_id, "evidence_01")
        self.assertEqual(steps[1].evidence_id, "")
        self.assertEqual(steps[2].evidence_id, "")

    def test_03_multiple_findings(self):
        """3. Multiple findings: Findings strictly ordered by operation priority."""
        evals = [
            {"finding": Step(0, Phase.FINDING, "backup_service", "backup_1", Operation.REPORT_RESTORE_RISK, ObservedState.ACTIVE, "evidence_01")},
            {"finding": Step(0, Phase.FINDING, "integration_service", "data_flow_1", Operation.REPORT_ACTIVE_DATA_FLOW, ObservedState.ACTIVE, "evidence_01")},
            {"finding": Step(0, Phase.FINDING, "support_platform", "support_1", Operation.REPORT_EXPOSED_PII, ObservedState.PRESENT, "evidence_01")},
            {"finding": Step(0, Phase.FINDING, "account_service", "account_1", Operation.REPORT_REMAINING_RECORD, ObservedState.PRESENT, "evidence_01")},
        ]
        status, steps = self.planner.build_plan("case_03", True, evals)
        self.assertEqual(status, DeletionStatus.INCOMPLETE)
        op_order = [s.operation for s in steps]
        expected_op_order = [
            Operation.REPORT_REMAINING_RECORD,
            Operation.REPORT_EXPOSED_PII,
            Operation.REPORT_ACTIVE_DATA_FLOW,
            Operation.REPORT_RESTORE_RISK,
        ]
        self.assertEqual(op_order, expected_op_order)

    def test_04_remediation_order(self):
        """4. Remediation ordering: DISABLE_DATA_FLOW -> BLOCK_RESTORE -> DELETE -> REDACT -> ANONYMIZE."""
        evals = [
            {"finding": Step(0, Phase.FINDING, "account_service", "acc", Operation.REPORT_REMAINING_RECORD, ObservedState.PRESENT, "evidence_01"),
             "remediation": Step(0, Phase.REMEDIATION, "analytics_platform", "analytics_1", Operation.ANONYMIZE_RECORD, ObservedState.ANONYMIZED, "")},
            {"finding": Step(0, Phase.FINDING, "account_service", "acc2", Operation.REPORT_REMAINING_RECORD, ObservedState.PRESENT, "evidence_01"),
             "remediation": Step(0, Phase.REMEDIATION, "support_platform", "support_1", Operation.REDACT_RECORD, ObservedState.REDACTED, "")},
            {"finding": Step(0, Phase.FINDING, "account_service", "acc3", Operation.REPORT_REMAINING_RECORD, ObservedState.PRESENT, "evidence_01"),
             "remediation": Step(0, Phase.REMEDIATION, "account_service", "account_1", Operation.DELETE_RECORD, ObservedState.ABSENT, "")},
            {"finding": Step(0, Phase.FINDING, "backup_service", "backup_1", Operation.REPORT_RESTORE_RISK, ObservedState.ACTIVE, "evidence_01"),
             "remediation": Step(0, Phase.REMEDIATION, "backup_service", "backup_1", Operation.BLOCK_RESTORE, ObservedState.BLOCKED, "")},
            {"finding": Step(0, Phase.FINDING, "integration_service", "flow_1", Operation.REPORT_ACTIVE_DATA_FLOW, ObservedState.ACTIVE, "evidence_01"),
             "remediation": Step(0, Phase.REMEDIATION, "integration_service", "flow_1", Operation.DISABLE_DATA_FLOW, ObservedState.DISABLED, "")},
        ]
        status, steps = self.planner.build_plan("case_04", True, evals)
        remediations = [s for s in steps if s.phase == Phase.REMEDIATION]
        rem_ops = [s.operation for s in remediations]
        expected_ops = [
            Operation.DISABLE_DATA_FLOW,
            Operation.BLOCK_RESTORE,
            Operation.DELETE_RECORD,
            Operation.REDACT_RECORD,
            Operation.ANONYMIZE_RECORD,
        ]
        self.assertEqual(rem_ops, expected_ops)

    def test_05_verification_order(self):
        """5. Verification ordering: ABSENT -> PRESENT -> REDACTED -> ANONYMIZED -> DISABLED -> BLOCKED."""
        evals = [
            {"verification": Step(0, Phase.VERIFICATION, "backup_service", "backup_1", Operation.VERIFY_RESTORE_BLOCKED, ObservedState.BLOCKED, "evidence_01")},
            {"verification": Step(0, Phase.VERIFICATION, "integration_service", "flow_1", Operation.VERIFY_DATA_FLOW_DISABLED, ObservedState.DISABLED, "evidence_01")},
            {"verification": Step(0, Phase.VERIFICATION, "analytics_platform", "analytics_1", Operation.VERIFY_RECORD_ANONYMIZED, ObservedState.ANONYMIZED, "evidence_01")},
            {"verification": Step(0, Phase.VERIFICATION, "support_platform", "support_1", Operation.VERIFY_RECORD_REDACTED, ObservedState.REDACTED, "evidence_01")},
            {"verification": Step(0, Phase.VERIFICATION, "security_service", "audit_1", Operation.VERIFY_RECORD_PRESENT, ObservedState.PRESENT, "evidence_01")},
            {"verification": Step(0, Phase.VERIFICATION, "account_service", "account_1", Operation.VERIFY_RECORD_ABSENT, ObservedState.ABSENT, "evidence_01")},
        ]
        status, steps = self.planner.build_plan("case_05", True, evals)
        self.assertEqual(status, DeletionStatus.COMPLETE)
        verif_ops = [s.operation for s in steps]
        expected_ops = [
            Operation.VERIFY_RECORD_ABSENT,
            Operation.VERIFY_RECORD_PRESENT,
            Operation.VERIFY_RECORD_REDACTED,
            Operation.VERIFY_RECORD_ANONYMIZED,
            Operation.VERIFY_DATA_FLOW_DISABLED,
            Operation.VERIFY_RESTORE_BLOCKED,
        ]
        self.assertEqual(verif_ops, expected_ops)

    def test_06_mixed_phases(self):
        """6. Mixed phases: Strictly preserves FINDING -> REMEDIATION -> VERIFICATION phase sequence."""
        evals = [
            {"verification": Step(0, Phase.VERIFICATION, "account_service", "acc", Operation.VERIFY_RECORD_ABSENT, ObservedState.ABSENT, "")},
            {"remediation": Step(0, Phase.REMEDIATION, "account_service", "acc", Operation.DELETE_RECORD, ObservedState.ABSENT, "")},
            {"finding": Step(0, Phase.FINDING, "account_service", "acc", Operation.REPORT_REMAINING_RECORD, ObservedState.PRESENT, "evidence_01")},
        ]
        status, steps = self.planner.build_plan("case_06", True, evals)
        phases = [s.phase for s in steps]
        self.assertEqual(phases, [Phase.FINDING, Phase.REMEDIATION, Phase.VERIFICATION])

    def test_07_identical_system_resource_names(self):
        """7. Identical system/resource names: Tie-breaking handles identical systems with different operations."""
        evals = [
            {"finding": Step(0, Phase.FINDING, "support_platform", "ticket_100", Operation.REPORT_EXPOSED_PII, ObservedState.PRESENT, "evidence_01"),
             "remediation": Step(0, Phase.REMEDIATION, "support_platform", "ticket_100", Operation.REDACT_RECORD, ObservedState.REDACTED, ""),
             "verification": Step(0, Phase.VERIFICATION, "support_platform", "ticket_100", Operation.VERIFY_RECORD_REDACTED, ObservedState.REDACTED, "")},
            {"finding": Step(0, Phase.FINDING, "support_platform", "ticket_200", Operation.REPORT_REMAINING_RECORD, ObservedState.PRESENT, "evidence_01"),
             "remediation": Step(0, Phase.REMEDIATION, "support_platform", "ticket_200", Operation.DELETE_RECORD, ObservedState.ABSENT, ""),
             "verification": Step(0, Phase.VERIFICATION, "support_platform", "ticket_200", Operation.VERIFY_RECORD_ABSENT, ObservedState.ABSENT, "")},
        ]
        status, steps = self.planner.build_plan("case_07", True, evals)
        findings = [s for s in steps if s.phase == Phase.FINDING]
        self.assertEqual(findings[0].resource_id, "ticket_200")  # REPORT_REMAINING_RECORD (priority 1)
        self.assertEqual(findings[1].resource_id, "ticket_100")  # REPORT_EXPOSED_PII (priority 2)

    def test_08_ordering_ties(self):
        """8. Ordering ties: Secondary sorting strictly by system_id then resource_id."""
        evals = [
            {"verification": Step(0, Phase.VERIFICATION, "search_service", "search_2", Operation.VERIFY_RECORD_ABSENT, ObservedState.ABSENT, "evidence_01")},
            {"verification": Step(0, Phase.VERIFICATION, "account_service", "account_2", Operation.VERIFY_RECORD_ABSENT, ObservedState.ABSENT, "evidence_01")},
            {"verification": Step(0, Phase.VERIFICATION, "search_service", "search_1", Operation.VERIFY_RECORD_ABSENT, ObservedState.ABSENT, "evidence_01")},
            {"verification": Step(0, Phase.VERIFICATION, "account_service", "account_1", Operation.VERIFY_RECORD_ABSENT, ObservedState.ABSENT, "evidence_01")},
        ]
        status, steps = self.planner.build_plan("case_08", True, evals)
        tuples = [(s.system_id, s.resource_id) for s in steps]
        expected_tuples = [
            ("account_service", "account_1"),
            ("account_service", "account_2"),
            ("search_service", "search_1"),
            ("search_service", "search_2"),
        ]
        self.assertEqual(tuples, expected_tuples)

    def test_09_duplicate_evidence(self):
        """9. Duplicate evidence: Duplicate step evaluations are merged deterministically."""
        step = Step(0, Phase.VERIFICATION, "account_service", "account_1", Operation.VERIFY_RECORD_ABSENT, ObservedState.ABSENT, "evidence_01")
        evals = [
            {"verification": step},
            {"verification": step},
        ]
        status, steps = self.planner.build_plan("case_09", True, evals)
        self.assertEqual(len(steps), 1)

    def test_10_invalid_evidence_ids(self):
        """10. Invalid evidence IDs: Validation raises ValueError on malformed evidence_id."""
        malformed_finding = Step(0, Phase.FINDING, "account_service", "account_1", Operation.REPORT_REMAINING_RECORD, ObservedState.PRESENT, "invalid_id_format")
        with self.assertRaises(ValueError):
            self.planner.build_plan("case_10", True, [{"finding": malformed_finding}])

    def test_11_complete_evidence(self):
        """11. COMPLETE evidence: All steps in a COMPLETE plan retain their cited evidence IDs."""
        evals = [
            {"verification": Step(0, Phase.VERIFICATION, "account_service", "acc_1", Operation.VERIFY_RECORD_ABSENT, ObservedState.ABSENT, "evidence_54")},
            {"verification": Step(0, Phase.VERIFICATION, "security_service", "audit_1", Operation.VERIFY_RECORD_PRESENT, ObservedState.PRESENT, "evidence_54")},
        ]
        status, steps = self.planner.build_plan("case_11", True, evals)
        self.assertEqual(status, DeletionStatus.COMPLETE)
        self.assertTrue(all(s.evidence_id == "evidence_54" for s in steps))

    def test_12_incomplete_empty_evidence_ids(self):
        """12. INCOMPLETE empty evidence IDs: Remediations and future verifications must have empty evidence_id."""
        evals = [
            {"finding": Step(0, Phase.FINDING, "account_service", "acc_1", Operation.REPORT_REMAINING_RECORD, ObservedState.PRESENT, "evidence_01"),
             "remediation": Step(0, Phase.REMEDIATION, "account_service", "acc_1", Operation.DELETE_RECORD, ObservedState.ABSENT, "evidence_01"),  # Has evidence_id which must be stripped
             "verification": Step(0, Phase.VERIFICATION, "account_service", "acc_1", Operation.VERIFY_RECORD_ABSENT, ObservedState.ABSENT, "evidence_01")},  # Has evidence_id which must be stripped
        ]
        status, steps = self.planner.build_plan("case_12", True, evals)
        self.assertEqual(status, DeletionStatus.INCOMPLETE)
        f = [s for s in steps if s.phase == Phase.FINDING][0]
        r = [s for s in steps if s.phase == Phase.REMEDIATION][0]
        v = [s for s in steps if s.phase == Phase.VERIFICATION][0]

        self.assertEqual(f.evidence_id, "evidence_01")
        self.assertEqual(r.evidence_id, "")
        self.assertEqual(v.evidence_id, "")


if __name__ == "__main__":
    unittest.main()
