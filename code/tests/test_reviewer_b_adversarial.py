"""
test_reviewer_b_adversarial.py — Senior Architect Adversarial Stress Test Suite (Reviewer B)
Attacks critical points in identity, temporal machine, cycle detection, and policy logic.
"""

import unittest
from datetime import datetime, timezone, timedelta
from code.models import DeletionStatus, Phase, Operation, ResourceState
from code.evidence_models import EvidenceObservation, ObservedState
from code.temporal_state_machine import TemporalStateMachine
from code.policy_engine import PolicyEngine
from code.recreation_models import DataFlowGraph, GraphEdge, FlowType, ActivityStatus
from code.intent_classifier import IntentClassifier
from code.extractors.json_extractor import JsonExtractor


class TestReviewerBAdversarialAttacks(unittest.TestCase):
    """Reviewer B adversarial stress test attacks."""

    def setUp(self):
        self.tsm = TemporalStateMachine()
        self.policy = PolicyEngine()
        self.intent = IntentClassifier()

    def test_attack_1_microsecond_clock_skew(self):
        """Attack: Primary deleted at T, replica observed present at T + 1 microsecond."""
        t_base = datetime(2026, 8, 1, 12, 0, 0, 0, tzinfo=timezone.utc)
        t_skew = t_base + timedelta(microseconds=1)
        audit_at = t_base + timedelta(hours=1)

        obs_del = EvidenceObservation(
            observation_id="obs_1",
            evidence_id="evidence_01",
            source_file="primary.sql",
            source_location="sql",
            extraction_method="sql_dump",
            captured_at=t_base,
            event_time=t_base,
            system_id="account_db",
            resource_id="acc_999",
            resource_type="ACCOUNT_DATA",
            data_category="ACCOUNT_DATA",
            observed_state=ObservedState.ABSENT,
        )
        obs_rep = EvidenceObservation(
            observation_id="obs_2",
            evidence_id="evidence_02",
            source_file="replica.sql",
            source_location="sql",
            extraction_method="sql_dump",
            captured_at=t_skew,
            event_time=t_skew,
            system_id="account_db",
            resource_id="acc_999",
            resource_type="ACCOUNT_DATA",
            data_category="ACCOUNT_DATA",
            observed_state=ObservedState.PRESENT,
        )

        snaps = self.tsm.evaluate_resource_states_at_audit([obs_del, obs_rep], audit_at)
        self.assertIn("acc_999", snaps)
        # The replica snapshot captured 1 microsecond later proves data was recreated / lagged
        self.assertEqual(snaps["acc_999"].proven_state, ObservedState.PRESENT)

    def test_attack_2_tombstone_email_hash_leak(self):
        """Attack: Account tombstone has name/email removed but leaks email_hash."""
        from code.evidence_models import ResourceStateSnapshot
        now = datetime(2026, 9, 1, tzinfo=timezone.utc)
        snap = ResourceStateSnapshot(
            system_id="identity_service",
            resource_id="tombstone_user_99",
            data_category="ACCOUNT_TOMBSTONE",
            proven_state=ObservedState.PRESENT,
            audit_at=now,
            cited_evidence_id="evidence_50",
            metadata={"has_prohibited_pii": True},
        )
        proof = self.policy.evaluate_resource_policy(snap)
        # Redact rule requires email_hash to be removed from tombstone
        self.assertFalse(proof.is_compliant)
        self.assertEqual(proof.finding_step.operation, Operation.REPORT_EXPOSED_PII)
        self.assertEqual(proof.remediation_step.operation, Operation.REDACT_RECORD)

    def test_attack_3_cyclic_recreation_dataflow(self):
        """Attack: Complex multi-hop circular dataflow: S1 -> S2 -> S3 -> S1."""
        now = datetime(2026, 9, 1, tzinfo=timezone.utc)
        graph = DataFlowGraph()
        graph.add_edge(GraphEdge(edge_id="e1", source_node="svc_1", target_node="svc_2", flow_type=FlowType.SYNC, channel_id="ch_1", status=ActivityStatus.ACTIVE, is_active=True, event_time=now, evidence_id="act_1"))
        graph.add_edge(GraphEdge(edge_id="e2", source_node="svc_2", target_node="svc_3", flow_type=FlowType.SYNC, channel_id="ch_2", status=ActivityStatus.ACTIVE, is_active=True, event_time=now, evidence_id="act_2"))
        graph.add_edge(GraphEdge(edge_id="e3", source_node="svc_3", target_node="svc_1", flow_type=FlowType.SYNC, channel_id="ch_3", status=ActivityStatus.ACTIVE, is_active=True, event_time=now, evidence_id="act_3"))

        cycles = graph.detect_cycles()
        self.assertTrue(len(cycles) >= 1)

    def test_attack_4_corrupted_json_resilience(self):
        """Attack: Corrupted/non-dict JSON and unexpected types."""
        import tempfile, os
        ext = JsonExtractor({})
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("['corrupted', 'array', 123]")
            f_path = f.name
        try:
            obs = ext.extract_from_file(f_path, "corrupted.json")
            self.assertEqual(obs, [])
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)

    def test_attack_5_unicode_zero_width_request_intent(self):
        """Attack: Request text containing zero-width spaces and mixed whitespace."""
        malicious_text = "Please\u200b erase \u200cmy \u200daccount and \ufeffdelete all personal data."
        is_del, req_type, rationale = self.intent.classify(malicious_text)
        self.assertTrue(is_del)

    def test_attack_6_exact_timestamp_conflict_resolution(self):
        """Attack: Direct evidence says PRESENT while activity log says COMPLETE at identical timestamp."""
        t_same = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
        audit_at = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)

        obs_claim = EvidenceObservation(
            observation_id="act_101",
            evidence_id="activity_101",
            source_file="system_activity.csv",
            source_location="activity",
            extraction_method="system_activity_stream",
            captured_at=t_same,
            event_time=t_same,
            system_id="billing_service",
            resource_id="inv_55",
            resource_type="INVOICE",
            data_category="TRANSACTION_RECORDS",
            observed_state=ObservedState.ABSENT,
        )
        obs_physical = EvidenceObservation(
            observation_id="ev_202",
            evidence_id="evidence_20",
            source_file="billing_snapshot.json",
            source_location="json",
            extraction_method="json_snapshot_bundle",
            captured_at=t_same,
            event_time=t_same,
            system_id="billing_service",
            resource_id="inv_55",
            resource_type="INVOICE",
            data_category="TRANSACTION_RECORDS",
            observed_state=ObservedState.PRESENT,
        )

        # Rule 1 Invariant: Direct physical evidence MUST override activity claims
        snaps = self.tsm.evaluate_resource_states_at_audit([obs_claim, obs_physical], audit_at)
        self.assertEqual(snaps["inv_55"].proven_state, ObservedState.PRESENT)
        self.assertEqual(snaps["inv_55"].cited_evidence_id, "evidence_20")

    def test_attack_7_post_audit_evidence_strict_exclusion(self):
        """Attack: Evidence file captured 1 second after audit_at must never be included."""
        t_audit = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
        t_after = t_audit + timedelta(seconds=1)

        obs_after = EvidenceObservation(
            observation_id="obs_future",
            evidence_id="evidence_99",
            source_file="future.sql",
            source_location="sql",
            extraction_method="sql_dump",
            captured_at=t_after,
            event_time=t_after,
            system_id="account_service",
            resource_id="acc_future",
            resource_type="ACCOUNT_DATA",
            data_category="ACCOUNT_DATA",
            observed_state=ObservedState.ABSENT,
        )

        snaps = self.tsm.evaluate_resource_states_at_audit([obs_after], t_audit)
        self.assertEqual(len(snaps), 0)

    def test_attack_8_mixed_case_multilingual_rectification_rejection(self):
        """Attack: Spanish rectification request with mixed case asking to correct phone, not delete."""
        rect_text = "PoR FaVoR CorRiJa Mi NúMeRo De TelÉfOnO eN Mi PeRfiL."
        is_del, req_type, rationale = self.intent.classify(rect_text)
        self.assertFalse(is_del)


if __name__ == "__main__":
    unittest.main()
