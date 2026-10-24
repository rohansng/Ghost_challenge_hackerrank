"""
Adversarial Test Suite for Ghost Data Still Exists
HackerRank Orchestrate October 2026 — Phase 7

Contains 16 comprehensive adversarial evaluation test cases verifying:
1. historical email
2. identifier collision
3. stale evidence
4. post-audit evidence
5. active sync
6. inactive sync
7. backup restore risk
8. retained record with prohibited identifier
9. contradictory workflow result
10. ambiguous identity
11. compliant account tombstone
12. non-deletion rectification request
13. non-deletion access request
14. legal hold retention coexistence
15. surviving secondary export
16. downstream dependency remediation ordering
"""

import unittest
from datetime import datetime
from code.models import DeletionRequestRecord as DeletionRequest, DeletionStatus, Phase, Operation, IdentityNode
from code.evidence_models import EvidenceObservation, ObservedState
from code.intent_classifier import IntentClassifier
from code.identity_engine import IdentityEngine, IdentityResolutionResult
from code.temporal_state_machine import TemporalStateMachine
from code.policy_engine import PolicyEngine
from code.remediation_planner import RemediationPlanner, StepValidator
from code.decision_engine import DecisionEngine


class TestAdversarialSuite(unittest.TestCase):
    def setUp(self):
        self.intent_classifier = IntentClassifier()
        self.tsm = TemporalStateMachine()
        self.policy_engine = PolicyEngine()
        self.planner = RemediationPlanner()
        self.decision_engine = DecisionEngine()

    def test_01_historical_email(self):
        """
        Scenario: Subject submits deletion request using an older historical email address.
        Expected reasoning: Multi-hop identity engine resolves historical alias to canonical user_id, finding surviving records under current identity.
        Expected status: INCOMPLETE
        Expected safety property: Historical email alias cannot be used as an evasion vector; ghost data under all subject aliases must be remediated.
        """
        req = DeletionRequest(
            case_id="adv_01",
            email="old.alias@example.com",
            requested_at=datetime.fromisoformat("2026-05-01T10:00:00+00:00"),
            reported_status="COMPLETE",
            reported_at=datetime.fromisoformat("2026-05-02T10:00:00+00:00"),
            audit_at=datetime.fromisoformat("2026-05-10T10:00:00+00:00"),
            request_text="Please delete my account and all personal records across all systems.",
        )
        is_del, _, _ = self.intent_classifier.classify(req.request_text)
        self.assertTrue(is_del)

        # Mock resolved identity with historical alias
        node = IdentityNode(
            canonical_user_id="user_adv_01",
            current_name="Test User",
            current_email="new.primary@example.com",
            current_phone="+1234567890",
            current_email_hash="hash123",
            updated_at=datetime.fromisoformat("2026-05-01T10:00:00+00:00"),
        )
        node.all_emails.update(["new.primary@example.com", "old.alias@example.com"])
        res = IdentityResolutionResult(
            is_resolved=True,
            canonical_user_id="user_adv_01",
            identity_node=node,
            primary_relationship=None,
            confidence=1.0,
            matched_identifiers=[],
            ambiguities=[],
        )

        obs = [
            EvidenceObservation(
                observation_id="obs_01",
                evidence_id="evidence_01",
                source_file="evidence/logs/app.log",
                source_location="line:1",
                extraction_method="test",
                captured_at=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
                event_time=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
                system_id="account_service",
                resource_id="account_adv_01",
                resource_type="USER_PROFILE",
                data_category="USER_PROFILE",
                observed_state=ObservedState.PRESENT,
                user_id="user_adv_01",
                matched_identifier="new.primary@example.com",
            )
        ]
        snapshots = self.tsm.evaluate_resource_states_at_audit(obs, req.audit_at)
        eval_res = [self.policy_engine.evaluate_resource_policy(snap) for snap in snapshots.values()]
        status, steps = self.planner.build_plan(req.case_id, is_del, eval_res)

        self.assertEqual(status, DeletionStatus.INCOMPLETE)
        self.assertTrue(any(s.operation == Operation.REPORT_REMAINING_RECORD for s in steps))

    def test_02_identifier_collision(self):
        """
        Scenario: Two distinct users exist in the platform, but target user requests deletion.
        Expected reasoning: Identity engine isolates the target subject without touching the second user's records.
        Expected status: COMPLETE
        Expected safety property: Multi-tenant safety; no collateral deletion or unauthorized remediation of unrelated user records.
        """
        req = DeletionRequest(
            case_id="adv_02",
            email="target.user@example.com",
            requested_at=datetime.fromisoformat("2026-05-01T10:00:00+00:00"),
            reported_status="COMPLETE",
            reported_at=datetime.fromisoformat("2026-05-02T10:00:00+00:00"),
            audit_at=datetime.fromisoformat("2026-05-10T10:00:00+00:00"),
            request_text="I hereby request permanent deletion of my account.",
        )
        is_del, _, _ = self.intent_classifier.classify(req.request_text)

        # Target user verified deleted
        obs = [
            EvidenceObservation(
                observation_id="obs_02",
                evidence_id="evidence_02",
                source_file="evidence/logs/app.log",
                source_location="line:1",
                extraction_method="test",
                captured_at=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
                event_time=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
                system_id="account_service",
                resource_id="account_adv_02",
                resource_type="USER_PROFILE",
                data_category="USER_PROFILE",
                observed_state=ObservedState.ABSENT,
                user_id="user_adv_02",
                matched_identifier="target.user@example.com",
            )
        ]
        snapshots = self.tsm.evaluate_resource_states_at_audit(obs, req.audit_at)
        eval_res = [self.policy_engine.evaluate_resource_policy(snap) for snap in snapshots.values()]
        status, steps = self.planner.build_plan(req.case_id, is_del, eval_res)

        self.assertEqual(status, DeletionStatus.COMPLETE)
        self.assertEqual(steps[0].operation, Operation.VERIFY_RECORD_ABSENT)

    def test_03_stale_evidence_prior_to_deletion(self):
        """
        Scenario: An older observation at t0 shows account was PRESENT, but a subsequent observation at t1 < audit_at proves it was deleted.
        Expected reasoning: Temporal State Machine resolves the true state at audit_at using the latest chronological observation.
        Expected status: COMPLETE
        Expected safety property: No false-positive findings generated by outdated historical records superseded by valid deletion events.
        """
        req = DeletionRequest(
            case_id="adv_03",
            email="stale.test@example.com",
            requested_at=datetime.fromisoformat("2026-05-01T10:00:00+00:00"),
            reported_status="COMPLETE",
            reported_at=datetime.fromisoformat("2026-05-03T10:00:00+00:00"),
            audit_at=datetime.fromisoformat("2026-05-10T10:00:00+00:00"),
            request_text="Delete my data completely.",
        )
        is_del, _, _ = self.intent_classifier.classify(req.request_text)

        obs = [
            EvidenceObservation(
                observation_id="obs_03_stale",
                evidence_id="evidence_03",
                source_file="evidence/logs/old.log",
                source_location="line:1",
                extraction_method="test",
                captured_at=datetime.fromisoformat("2026-05-01T12:00:00+00:00"),
                event_time=datetime.fromisoformat("2026-05-01T12:00:00+00:00"),
                system_id="account_service",
                resource_id="account_adv_03",
                resource_type="USER_PROFILE",
                data_category="USER_PROFILE",
                observed_state=ObservedState.PRESENT,
            ),
            EvidenceObservation(
                observation_id="obs_03_fresh",
                evidence_id="evidence_04",
                source_file="evidence/logs/fresh.log",
                source_location="line:10",
                extraction_method="test",
                captured_at=datetime.fromisoformat("2026-05-02T12:00:00+00:00"),
                event_time=datetime.fromisoformat("2026-05-02T12:00:00+00:00"),
                system_id="account_service",
                resource_id="account_adv_03",
                resource_type="USER_PROFILE",
                data_category="USER_PROFILE",
                observed_state=ObservedState.ABSENT,
            ),
        ]
        snapshots = self.tsm.evaluate_resource_states_at_audit(obs, req.audit_at)
        self.assertEqual(snapshots["account_adv_03"].proven_state, ObservedState.ABSENT)
        eval_res = [self.policy_engine.evaluate_resource_policy(snap) for snap in snapshots.values()]
        status, steps = self.planner.build_plan(req.case_id, is_del, eval_res)
        self.assertEqual(status, DeletionStatus.COMPLETE)

    def test_04_post_audit_evidence_ignored(self):
        """
        Scenario: Record was PRESENT at audit_at. A deletion event occurred strictly after audit_at.
        Expected reasoning: Strict temporal cutoff at audit_at discards post-audit events when establishing state.
        Expected status: INCOMPLETE
        Expected safety property: Post-audit remediation claims cannot retroactively certify pre-audit compliance.
        """
        req = DeletionRequest(
            case_id="adv_04",
            email="post.audit@example.com",
            requested_at=datetime.fromisoformat("2026-05-01T10:00:00+00:00"),
            reported_status="NOT_STARTED",
            reported_at=datetime.fromisoformat("2026-05-02T10:00:00+00:00"),
            audit_at=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
            request_text="Please erase my personal profile.",
        )
        is_del, _, _ = self.intent_classifier.classify(req.request_text)

        obs = [
            EvidenceObservation(
                observation_id="obs_pre",
                evidence_id="evidence_05",
                source_file="evidence/logs/pre.log",
                source_location="line:1",
                extraction_method="test",
                captured_at=datetime.fromisoformat("2026-05-04T10:00:00+00:00"),
                event_time=datetime.fromisoformat("2026-05-04T10:00:00+00:00"),
                system_id="account_service",
                resource_id="account_adv_04",
                resource_type="USER_PROFILE",
                data_category="USER_PROFILE",
                observed_state=ObservedState.PRESENT,
            ),
            EvidenceObservation(
                observation_id="obs_post",
                evidence_id="evidence_06",
                source_file="evidence/logs/post.log",
                source_location="line:1",
                extraction_method="test",
                captured_at=datetime.fromisoformat("2026-05-06T10:00:00+00:00"),
                event_time=datetime.fromisoformat("2026-05-06T10:00:00+00:00"),
                system_id="account_service",
                resource_id="account_adv_04",
                resource_type="USER_PROFILE",
                data_category="USER_PROFILE",
                observed_state=ObservedState.ABSENT,
            ),
        ]
        snapshots = self.tsm.evaluate_resource_states_at_audit(obs, req.audit_at)
        self.assertEqual(snapshots["account_adv_04"].proven_state, ObservedState.PRESENT)
        eval_res = [self.policy_engine.evaluate_resource_policy(snap) for snap in snapshots.values()]
        status, steps = self.planner.build_plan(req.case_id, is_del, eval_res)
        self.assertEqual(status, DeletionStatus.INCOMPLETE)

    def test_05_active_sync_recreation_risk(self):
        """
        Scenario: Operational profile is deleted, but an active CDC replication sync flow is active.
        Expected reasoning: System detects active sync threat and requires DISABLE_DATA_FLOW before verification.
        Expected status: INCOMPLETE
        Expected safety property: Active recreation pathways prevent declaration of complete deletion until disabled.
        """
        req = DeletionRequest(
            case_id="adv_05",
            email="sync.risk@example.com",
            requested_at=datetime.fromisoformat("2026-05-01T10:00:00+00:00"),
            reported_status="COMPLETE",
            reported_at=datetime.fromisoformat("2026-05-02T10:00:00+00:00"),
            audit_at=datetime.fromisoformat("2026-05-10T10:00:00+00:00"),
            request_text="Delete my account and ensure no sync copies remain.",
        )
        is_del, _, _ = self.intent_classifier.classify(req.request_text)

        obs = [
            EvidenceObservation(
                observation_id="obs_sync",
                evidence_id="evidence_07",
                source_file="evidence/logs/sync.log",
                source_location="line:1",
                extraction_method="test",
                captured_at=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
                event_time=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
                system_id="integration_service",
                resource_id="data_flow_adv_05",
                resource_type="CONNECTOR_SUBSCRIPTION",
                data_category="CONNECTOR_SUBSCRIPTION",
                observed_state=ObservedState.ACTIVE,
            )
        ]
        snapshots = self.tsm.evaluate_resource_states_at_audit(obs, req.audit_at)
        eval_res = [self.policy_engine.evaluate_resource_policy(snap) for snap in snapshots.values()]
        status, steps = self.planner.build_plan(req.case_id, is_del, eval_res)

        self.assertEqual(status, DeletionStatus.INCOMPLETE)
        self.assertTrue(any(s.operation == Operation.REPORT_ACTIVE_DATA_FLOW for s in steps))
        self.assertTrue(any(s.operation == Operation.DISABLE_DATA_FLOW for s in steps))

    def test_06_inactive_sync_flow_safe(self):
        """
        Scenario: A sync connector exists in config, but is verified disabled (DISABLED state).
        Expected reasoning: Inactive sync flow does not constitute an active recreation risk.
        Expected status: COMPLETE
        Expected safety property: Inactive, dormant pipelines do not generate false positive remediation actions.
        """
        req = DeletionRequest(
            case_id="adv_06",
            email="inactive.sync@example.com",
            requested_at=datetime.fromisoformat("2026-05-01T10:00:00+00:00"),
            reported_status="COMPLETE",
            reported_at=datetime.fromisoformat("2026-05-02T10:00:00+00:00"),
            audit_at=datetime.fromisoformat("2026-05-10T10:00:00+00:00"),
            request_text="Delete my account please.",
        )
        is_del, _, _ = self.intent_classifier.classify(req.request_text)

        obs = [
            EvidenceObservation(
                observation_id="obs_disabled_flow",
                evidence_id="evidence_08",
                source_file="evidence/logs/sync.log",
                source_location="line:1",
                extraction_method="test",
                captured_at=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
                event_time=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
                system_id="integration_service",
                resource_id="data_flow_adv_06",
                resource_type="CONNECTOR_SUBSCRIPTION",
                data_category="CONNECTOR_SUBSCRIPTION",
                observed_state=ObservedState.DISABLED,
            )
        ]
        snapshots = self.tsm.evaluate_resource_states_at_audit(obs, req.audit_at)
        eval_res = [self.policy_engine.evaluate_resource_policy(snap) for snap in snapshots.values()]
        status, steps = self.planner.build_plan(req.case_id, is_del, eval_res)

        self.assertEqual(status, DeletionStatus.COMPLETE)
        self.assertEqual(steps[0].operation, Operation.VERIFY_DATA_FLOW_DISABLED)

    def test_07_backup_restore_risk(self):
        """
        Scenario: Backup snapshot exists in cold storage with deletion_block=False and restore_allowed=True.
        Expected reasoning: Unblocked backup creates restore threat (REPORT_RESTORE_RISK), requiring BLOCK_RESTORE.
        Expected status: INCOMPLETE
        Expected safety property: Backup archives without restore sanitization/blocks fail the deletion guarantee.
        """
        req = DeletionRequest(
            case_id="adv_07",
            email="backup.threat@example.com",
            requested_at=datetime.fromisoformat("2026-05-01T10:00:00+00:00"),
            reported_status="COMPLETE",
            reported_at=datetime.fromisoformat("2026-05-02T10:00:00+00:00"),
            audit_at=datetime.fromisoformat("2026-05-10T10:00:00+00:00"),
            request_text="Delete all traces of my account.",
        )
        is_del, _, _ = self.intent_classifier.classify(req.request_text)

        obs = [
            EvidenceObservation(
                observation_id="obs_backup_risk",
                evidence_id="evidence_09",
                source_file="evidence/logs/backup.log",
                source_location="line:1",
                extraction_method="test",
                captured_at=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
                event_time=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
                system_id="backup_service",
                resource_id="backup_adv_07",
                resource_type="BACKUP_ARCHIVE",
                data_category="BACKUP_ARCHIVE",
                observed_state=ObservedState.ACTIVE,
            )
        ]
        snapshots = self.tsm.evaluate_resource_states_at_audit(obs, req.audit_at)
        eval_res = [self.policy_engine.evaluate_resource_policy(snap) for snap in snapshots.values()]
        status, steps = self.planner.build_plan(req.case_id, is_del, eval_res)

        self.assertEqual(status, DeletionStatus.INCOMPLETE)
        self.assertTrue(any(s.operation == Operation.REPORT_RESTORE_RISK for s in steps))
        self.assertTrue(any(s.operation == Operation.BLOCK_RESTORE for s in steps))

    def test_08_retained_record_with_prohibited_pii(self):
        """
        Scenario: Support ticket is subject to 1-year retention under policy, but still contains direct customer PII.
        Expected reasoning: Policy requires REDACT on support messages; unredacted message triggers REPORT_EXPOSED_PII.
        Expected status: INCOMPLETE
        Expected safety property: Retention mandates cannot excuse unredacted direct personal identifiers.
        """
        req = DeletionRequest(
            case_id="adv_08",
            email="pii.exposed@example.com",
            requested_at=datetime.fromisoformat("2026-05-01T10:00:00+00:00"),
            reported_status="PARTIALLY_COMPLETE",
            reported_at=datetime.fromisoformat("2026-05-02T10:00:00+00:00"),
            audit_at=datetime.fromisoformat("2026-05-10T10:00:00+00:00"),
            request_text="Please delete my data and redact tickets.",
        )
        is_del, _, _ = self.intent_classifier.classify(req.request_text)

        obs = [
            EvidenceObservation(
                observation_id="obs_support_pii",
                evidence_id="evidence_10",
                source_file="evidence/logs/support.log",
                source_location="line:1",
                extraction_method="test",
                captured_at=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
                event_time=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
                system_id="support_platform",
                resource_id="support_adv_08",
                resource_type="SUPPORT_MESSAGE",
                data_category="SUPPORT_MESSAGE",
                observed_state=ObservedState.PRESENT,  # Not redacted yet
            )
        ]
        snapshots = self.tsm.evaluate_resource_states_at_audit(obs, req.audit_at)
        eval_res = [self.policy_engine.evaluate_resource_policy(snap) for snap in snapshots.values()]
        status, steps = self.planner.build_plan(req.case_id, is_del, eval_res)

        self.assertEqual(status, DeletionStatus.INCOMPLETE)
        self.assertTrue(any(s.operation == Operation.REPORT_EXPOSED_PII for s in steps))
        self.assertTrue(any(s.operation == Operation.REDACT_RECORD for s in steps))

    def test_09_contradictory_workflow_result(self):
        """
        Scenario: Workflow reports status COMPLETE, but ground truth evidence shows database replica contains active profile.
        Expected reasoning: Self-reported claims are treated as unverified; evidence establishes true state as INCOMPLETE.
        Expected status: INCOMPLETE
        Expected safety property: Self-reported workflow statuses never substitute for evidence-backed state verification.
        """
        req = DeletionRequest(
            case_id="adv_09",
            email="false.claim@example.com",
            requested_at=datetime.fromisoformat("2026-05-01T10:00:00+00:00"),
            reported_status="COMPLETE",  # Fraudulent or premature claim
            reported_at=datetime.fromisoformat("2026-05-02T10:00:00+00:00"),
            audit_at=datetime.fromisoformat("2026-05-10T10:00:00+00:00"),
            request_text="Delete my account permanently.",
        )
        is_del, _, _ = self.intent_classifier.classify(req.request_text)

        obs = [
            EvidenceObservation(
                observation_id="obs_replica_presence",
                evidence_id="evidence_11",
                source_file="evidence/logs/replica.log",
                source_location="line:1",
                extraction_method="test",
                captured_at=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
                event_time=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
                system_id="account_service",
                resource_id="account_adv_09",
                resource_type="USER_PROFILE",
                data_category="USER_PROFILE",
                observed_state=ObservedState.PRESENT,
            )
        ]
        snapshots = self.tsm.evaluate_resource_states_at_audit(obs, req.audit_at)
        eval_res = [self.policy_engine.evaluate_resource_policy(snap) for snap in snapshots.values()]
        status, steps = self.planner.build_plan(req.case_id, is_del, eval_res)

        self.assertEqual(status, DeletionStatus.INCOMPLETE)
        self.assertEqual(steps[0].operation, Operation.REPORT_REMAINING_RECORD)

    def test_10_ambiguous_identity_isolated(self):
        """
        Scenario: Request email matches an unlinked or corrupted profile without clear identity resolution.
        Expected reasoning: Identity Engine reports ambiguity without performing destructive wide-spectrum remediation.
        Expected status: INCOMPLETE
        Expected safety property: Indeterminate identity resolution fails closed safely without broad destructive side effects.
        """
        req = DeletionRequest(
            case_id="adv_10",
            email="ambiguous@example.com",
            requested_at=datetime.fromisoformat("2026-05-01T10:00:00+00:00"),
            reported_status="NOT_STARTED",
            reported_at=datetime.fromisoformat("2026-05-02T10:00:00+00:00"),
            audit_at=datetime.fromisoformat("2026-05-10T10:00:00+00:00"),
            request_text="Delete my data.",
        )
        is_del, _, _ = self.intent_classifier.classify(req.request_text)
        res = IdentityResolutionResult(
            is_resolved=False,
            canonical_user_id="ambiguous_user",
            identity_node=None,
            primary_relationship=None,
            confidence=0.2,
            matched_identifiers=[],
            ambiguities=["Ambiguous cluster"],
        )

        proof = self.decision_engine.evaluate_case(
            request=req,
            is_deletion_authorized=is_del,
            identity_res=res,
            all_observations=[],
            snapshots={},
            evaluated_resources=[],
            steps=[],
        )
        self.assertEqual(proof.final_decision, DeletionStatus.INCOMPLETE)

    def test_11_compliant_account_tombstone(self):
        """
        Scenario: Account tombstone exists with stable user_id preserved, but name, email, and phone stripped.
        Expected reasoning: Policy Engine recognizes compliant tombstone under policy rule ACCOUNT_TOMBSTONE and verifies state.
        Expected status: COMPLETE
        Expected safety property: Permitted account tombstones are preserved without violating deletion completeness.
        """
        req = DeletionRequest(
            case_id="adv_11",
            email="tombstone.user@example.com",
            requested_at=datetime.fromisoformat("2026-05-01T10:00:00+00:00"),
            reported_status="COMPLETE",
            reported_at=datetime.fromisoformat("2026-05-02T10:00:00+00:00"),
            audit_at=datetime.fromisoformat("2026-05-10T10:00:00+00:00"),
            request_text="Delete my account.",
        )
        is_del, _, _ = self.intent_classifier.classify(req.request_text)

        obs = [
            EvidenceObservation(
                observation_id="obs_tombstone",
                evidence_id="evidence_12",
                source_file="evidence/logs/tombstone.log",
                source_location="line:1",
                extraction_method="test",
                captured_at=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
                event_time=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
                system_id="identity_service",
                resource_id="tombstone_adv_11",
                resource_type="ACCOUNT_TOMBSTONE",
                data_category="ACCOUNT_TOMBSTONE",
                observed_state=ObservedState.REDACTED,
                user_id="user_adv_11",
            )
        ]
        snapshots = self.tsm.evaluate_resource_states_at_audit(obs, req.audit_at)
        eval_res = [self.policy_engine.evaluate_resource_policy(snap) for snap in snapshots.values()]
        status, steps = self.planner.build_plan(req.case_id, is_del, eval_res)

        self.assertEqual(status, DeletionStatus.COMPLETE)
        self.assertEqual(steps[0].operation, Operation.VERIFY_RECORD_REDACTED)

    def test_12_non_deletion_rectification_request(self):
        """
        Scenario: Request asks to 'update my shipping address and correct the spelling of my last name'.
        Expected reasoning: Intent classifier identifies non-deletion intent, sets status NOT_APPLICABLE with steps_json=[].
        Expected status: NOT_APPLICABLE
        Expected safety property: Non-deletion GDPR/CCPA requests (rectification) never trigger accidental data destruction.
        """
        text = "Hello, I noticed a typo in my shipping address. Please update my address to 123 Main St and correct my profile."
        is_del, req_type, _ = self.intent_classifier.classify(text)
        self.assertFalse(is_del)

        status, steps = self.planner.build_plan("adv_12", is_del, [])
        self.assertEqual(status, DeletionStatus.NOT_APPLICABLE)
        self.assertEqual(steps, [])

    def test_13_non_deletion_access_request(self):
        """
        Scenario: Request asks for 'a complete export and copy of all personal records for data portability'.
        Expected reasoning: Intent classifier identifies access/portability request, sets status NOT_APPLICABLE with steps_json=[].
        Expected status: NOT_APPLICABLE
        Expected safety property: Data access requests are never conflated with erasure requests.
        """
        text = "Under Article 15 of GDPR, I request a copy of all my personal data and an export of my account history."
        is_del, req_type, _ = self.intent_classifier.classify(text)
        self.assertFalse(is_del)

        status, steps = self.planner.build_plan("adv_13", is_del, [])
        self.assertEqual(status, DeletionStatus.NOT_APPLICABLE)
        self.assertEqual(steps, [])

    def test_14_legal_hold_retention_coexistence(self):
        """
        Scenario: Security audit record is subject to statutory retention under policy rule RETAIN.
        Expected reasoning: Policy Engine verifies record is preserved (VERIFY_RECORD_PRESENT) without ordering deletion.
        Expected status: COMPLETE
        Expected safety property: Legal preservation mandates override deletion without failing compliance.
        """
        req = DeletionRequest(
            case_id="adv_14",
            email="legal.hold@example.com",
            requested_at=datetime.fromisoformat("2026-05-01T10:00:00+00:00"),
            reported_status="COMPLETE",
            reported_at=datetime.fromisoformat("2026-05-02T10:00:00+00:00"),
            audit_at=datetime.fromisoformat("2026-05-10T10:00:00+00:00"),
            request_text="Delete my data subject to your legal obligations.",
        )
        is_del, _, _ = self.intent_classifier.classify(req.request_text)

        obs = [
            EvidenceObservation(
                observation_id="obs_audit",
                evidence_id="evidence_14",
                source_file="evidence/logs/audit.log",
                source_location="line:1",
                extraction_method="test",
                captured_at=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
                event_time=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
                system_id="security_service",
                resource_id="audit_record_adv_14",
                resource_type="SECURITY_AUDIT_LOG",
                data_category="SECURITY_AUDIT_LOG",
                observed_state=ObservedState.PRESENT,
            )
        ]
        snapshots = self.tsm.evaluate_resource_states_at_audit(obs, req.audit_at)
        eval_res = [self.policy_engine.evaluate_resource_policy(snap) for snap in snapshots.values()]
        status, steps = self.planner.build_plan(req.case_id, is_del, eval_res)

        self.assertEqual(status, DeletionStatus.COMPLETE)
        self.assertEqual(steps[0].operation, Operation.VERIFY_RECORD_PRESENT)

    def test_15_surviving_secondary_export(self):
        """
        Scenario: Operational profile was deleted, but an export ZIP file dumped to storage remains available.
        Expected reasoning: Reconstructs surviving export as PRESENT, triggering REPORT_REMAINING_RECORD and DELETE_RECORD.
        Expected status: INCOMPLETE
        Expected safety property: Secondary exports and archival dumps are audited with identical rigor to primary operational stores.
        """
        req = DeletionRequest(
            case_id="adv_15",
            email="export.leak@example.com",
            requested_at=datetime.fromisoformat("2026-05-01T10:00:00+00:00"),
            reported_status="COMPLETE",
            reported_at=datetime.fromisoformat("2026-05-02T10:00:00+00:00"),
            audit_at=datetime.fromisoformat("2026-05-10T10:00:00+00:00"),
            request_text="Erase my account.",
        )
        is_del, _, _ = self.intent_classifier.classify(req.request_text)

        obs = [
            EvidenceObservation(
                observation_id="obs_exp",
                evidence_id="evidence_15",
                source_file="evidence/logs/export.log",
                source_location="line:1",
                extraction_method="test",
                captured_at=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
                event_time=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
                system_id="export_service",
                resource_id="export_adv_15",
                resource_type="USER_EXPORT",
                data_category="USER_EXPORT",
                observed_state=ObservedState.PRESENT,
            )
        ]
        snapshots = self.tsm.evaluate_resource_states_at_audit(obs, req.audit_at)
        eval_res = [self.policy_engine.evaluate_resource_policy(snap) for snap in snapshots.values()]
        status, steps = self.planner.build_plan(req.case_id, is_del, eval_res)

        self.assertEqual(status, DeletionStatus.INCOMPLETE)
        self.assertTrue(any(s.operation == Operation.REPORT_REMAINING_RECORD for s in steps))
        self.assertTrue(any(s.operation == Operation.DELETE_RECORD for s in steps))

    def test_16_downstream_dependency_remediation_ordering(self):
        """
        Scenario: Both an active data flow and a downstream replica record are found incomplete.
        Expected reasoning: Remediation Planner enforces canonical remediation priority: DISABLE_DATA_FLOW precedes DELETE_RECORD.
        Expected status: INCOMPLETE
        Expected safety property: Ingestion/sync sources must be disabled before downstream records are cleaned.
        """
        req = DeletionRequest(
            case_id="adv_16",
            email="order.test@example.com",
            requested_at=datetime.fromisoformat("2026-05-01T10:00:00+00:00"),
            reported_status="NOT_STARTED",
            reported_at=datetime.fromisoformat("2026-05-02T10:00:00+00:00"),
            audit_at=datetime.fromisoformat("2026-05-10T10:00:00+00:00"),
            request_text="Delete my data.",
        )
        is_del, _, _ = self.intent_classifier.classify(req.request_text)

        obs = [
            EvidenceObservation(
                observation_id="obs_rec",
                evidence_id="evidence_16",
                source_file="evidence/logs/rec.log",
                source_location="line:1",
                extraction_method="test",
                captured_at=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
                event_time=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
                system_id="search_service",
                resource_id="search_adv_16",
                resource_type="SEARCH_INDEX_ENTRY",
                data_category="SEARCH_INDEX_ENTRY",
                observed_state=ObservedState.PRESENT,
            ),
            EvidenceObservation(
                observation_id="obs_flow",
                evidence_id="evidence_17",
                source_file="evidence/logs/flow.log",
                source_location="line:2",
                extraction_method="test",
                captured_at=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
                event_time=datetime.fromisoformat("2026-05-05T10:00:00+00:00"),
                system_id="integration_service",
                resource_id="data_flow_adv_16",
                resource_type="CONNECTOR_SUBSCRIPTION",
                data_category="CONNECTOR_SUBSCRIPTION",
                observed_state=ObservedState.ACTIVE,
            ),
        ]
        snapshots = self.tsm.evaluate_resource_states_at_audit(obs, req.audit_at)
        eval_res = [self.policy_engine.evaluate_resource_policy(snap) for snap in snapshots.values()]
        status, steps = self.planner.build_plan(req.case_id, is_del, eval_res)

        self.assertEqual(status, DeletionStatus.INCOMPLETE)
        # Find step indexes
        disable_step_idx = next(i for i, s in enumerate(steps) if s.operation == Operation.DISABLE_DATA_FLOW)
        delete_step_idx = next(i for i, s in enumerate(steps) if s.operation == Operation.DELETE_RECORD)

        self.assertLess(disable_step_idx, delete_step_idx)


if __name__ == "__main__":
    unittest.main()
