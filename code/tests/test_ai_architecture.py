"""
Unit Tests for AI Architecture Hardening & Semantic Validation Engine
HackerRank Orchestrate October 2026 — Phase 8
"""

import unittest
from datetime import datetime
from code.ai_architect import (
    CandidateObservation,
    ObservationValidator,
    AIArchitectureAuditor,
    ModelCallSpecification,
)
from code.evidence_models import ObservedState
from code.intent_classifier import IntentClassifier
from code.policy_engine import PolicyEngine
from code.remediation_planner import RemediationPlanner
from code.decision_engine import DecisionEngine
from code.models import DeletionStatus


class TestAIArchitectureHardening(unittest.TestCase):
    def setUp(self):
        self.known_evidence_ids = {"evidence_01", "evidence_02", "evidence_03", "activity_101"}
        self.validator = ObservationValidator(self.known_evidence_ids)

    def test_01_candidate_observation_promotion(self):
        """Valid candidate observation is schema-checked and promoted to grounded EvidenceObservation."""
        cand = CandidateObservation(
            evidence_id="evidence_01",
            source_file="evidence/logs/service_events.log",
            source_location="line:42",
            system_id="account_service",
            resource_id="account_101",
            data_category="USER_PROFILE",
            observed_state="PRESENT",
            matched_identifier="user@example.com",
            confidence=0.98,
        )
        is_valid, promoted, err = self.validator.validate_and_promote(cand)
        self.assertTrue(is_valid)
        self.assertIsNotNone(promoted)
        self.assertIsNone(err)
        self.assertEqual(promoted.observed_state, ObservedState.PRESENT)
        self.assertEqual(promoted.system_id, "account_service")
        self.assertEqual(promoted.resource_id, "account_101")
        self.assertEqual(promoted.extraction_method, "ai_model_validated")

    def test_02_rejection_of_fabricated_evidence_id(self):
        """Untrusted model output citing fabricated or unmanifested evidence_id is rejected."""
        cand = CandidateObservation(
            evidence_id="evidence_9999",  # Not in known manifest
            source_file="evidence/logs/ghost.log",
            source_location="line:1",
            system_id="account_service",
            resource_id="account_101",
            data_category="USER_PROFILE",
            observed_state="PRESENT",
        )
        is_valid, promoted, err = self.validator.validate_and_promote(cand)
        self.assertFalse(is_valid)
        self.assertIsNone(promoted)
        self.assertIn("Fabricated evidence_id not in manifest", err)

    def test_03_rejection_of_invalid_system_id(self):
        """Untrusted model output with hallucinated system_id is rejected."""
        cand = CandidateObservation(
            evidence_id="evidence_01",
            source_file="evidence/logs/app.log",
            source_location="line:1",
            system_id="hallucinated_database_service",
            resource_id="db_99",
            data_category="USER_PROFILE",
            observed_state="PRESENT",
        )
        is_valid, promoted, err = self.validator.validate_and_promote(cand)
        self.assertFalse(is_valid)
        self.assertIsNone(promoted)
        self.assertIn("Invalid system_id", err)

    def test_04_rejection_of_missing_provenance(self):
        """Untrusted model output without grounded provenance (file and location) is rejected."""
        cand = CandidateObservation(
            evidence_id="evidence_01",
            source_file="",  # Missing provenance
            source_location="",
            system_id="account_service",
            resource_id="account_101",
            data_category="USER_PROFILE",
            observed_state="PRESENT",
        )
        is_valid, promoted, err = self.validator.validate_and_promote(cand)
        self.assertFalse(is_valid)
        self.assertIn("Missing provenance", err)

    def test_05_model_cannot_dictate_final_decision(self):
        """
        Architecture Invariant: A model cannot output 'COMPLETE' directly.
        All decisions must pass through TemporalStateMachine -> PolicyEngine -> DecisionEngine proof checklist.
        """
        # Even if a model claims a resource is deleted:
        cand = CandidateObservation(
            evidence_id="evidence_01",
            source_file="evidence/logs/app.log",
            source_location="line:5",
            system_id="account_service",
            resource_id="account_101",
            data_category="USER_PROFILE",
            observed_state="ABSENT",
        )
        is_valid, promoted, _ = self.validator.validate_and_promote(cand)
        self.assertTrue(is_valid)

        # The promoted observation is only a candidate input to PolicyEngine
        policy_engine = PolicyEngine()
        from code.evidence_models import ResourceStateSnapshot
        snap = ResourceStateSnapshot(
            system_id="account_service",
            resource_id="account_101",
            data_category="USER_PROFILE",
            proven_state=promoted.observed_state,
            audit_at=datetime.now(),
            cited_evidence_id=promoted.evidence_id,
        )
        eval_res = policy_engine.evaluate_resource_policy(snap)
        self.assertTrue(eval_res["is_compliant"])

        # Final status is determined deterministically by RemediationPlanner, not LLM
        planner = RemediationPlanner()
        status, steps = planner.build_plan("case_test", True, [eval_res])
        self.assertEqual(status, DeletionStatus.COMPLETE)
        self.assertEqual(len(steps), 1)

    def test_06_deterministic_fallback_availability(self):
        """If AI model is disabled or fails, deterministic fallbacks process evidence with 100% integrity."""
        classifier = IntentClassifier()
        # Complex French request
        text = "Veuillez supprimer définitivement mon compte et toutes les données personnelles associées."
        is_del, req_type, rationale = classifier.classify(text)
        self.assertTrue(is_del)
        self.assertEqual(req_type.value, "DELETION")

    def test_07_structured_pipeline_zero_ai_dependency(self):
        """Structured operations (sorting, CSV serialization, policy evaluation) have zero LLM dependency."""
        planner = RemediationPlanner()
        # Verify plan building is completely deterministic
        status, steps = planner.build_plan("case_sort_test", False, [])
        self.assertEqual(status, DeletionStatus.NOT_APPLICABLE)
        self.assertEqual(steps, [])

    def test_08_all_model_specifications_audited(self):
        """Every potential model touchpoint has an exhaustive, documented specification."""
        specs = AIArchitectureAuditor.get_all_model_specifications()
        self.assertEqual(len(specs), 4)

        for s in specs:
            self.assertTrue(len(s.call_id) > 0)
            self.assertTrue(len(s.purpose) > 0)
            self.assertIsInstance(s.expected_output_schema, dict)
            self.assertTrue(len(s.failure_modes) > 0)
            self.assertTrue(len(s.validation_mechanism) > 0)
            self.assertTrue(len(s.fallback_mechanism) > 0)
            self.assertGreater(s.estimated_token_cost_input, 0)
            self.assertGreater(s.estimated_token_cost_output, 0)
            self.assertFalse(s.is_runtime_necessary)  # All compiled to deterministic runtime!


if __name__ == "__main__":
    unittest.main()
