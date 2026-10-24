"""
test_identity_engine.py - Unit Test Suite for Identity Engine and Ingestion.
Tests:
1. Current email match
2. Historical email match
3. Multiple identifiers in chain
4. Identifier collision
5. Unrelated user with similar identifier
6. Identity changed before audit_at
7. Identity changed after audit_at
8. Missing identity
9. Duplicate identity records
10. Malformed records
11. Synthetic test cases without organizer truth
"""

import unittest
from datetime import datetime, timezone

from code.models import (
    UserIdentityRecord,
    AuditLogRecord,
    MatchRelationship,
    RequestType,
    DeletionRequestRecord,
)
from code.identity_engine import IdentityEngine
from code.intent_classifier import IntentClassifier
from code.case_context import CaseContextBuilder
from code.loaders import DataLoader, parse_iso_datetime


class TestIdentityEngine(unittest.TestCase):

    def setUp(self):
        # Create synthetic test dataset
        self.t0 = parse_iso_datetime("2025-01-01T00:00:00Z")
        self.t1 = parse_iso_datetime("2025-06-01T00:00:00Z")
        self.t2 = parse_iso_datetime("2026-01-01T00:00:00Z")
        self.t3 = parse_iso_datetime("2026-06-01T00:00:00Z")

        # Synthetic User 1: Has historical email and phone changes
        self.u1 = UserIdentityRecord(
            user_id="user_synth_01",
            name="Alice Smith",
            email="alice.smith@example.com",
            phone="+1 555 0101",
            email_hash="hash_alice_current",
            updated_at=self.t2,
        )

        # Synthetic User 2: Static profile
        self.u2 = UserIdentityRecord(
            user_id="user_synth_02",
            name="Bob Jones",
            email="bob.jones@example.com",
            phone="+1 555 0202",
            email_hash="hash_bob_current",
            updated_at=self.t0,
        )

        # Synthetic User 3: Collision victim (shares an old phone with user 4 in malformed scenario)
        self.u3 = UserIdentityRecord(
            user_id="user_synth_03",
            name="Charlie Brown",
            email="charlie@example.com",
            phone="+1 555 0303",
            email_hash="hash_charlie_current",
            updated_at=self.t0,
        )
        self.u4 = UserIdentityRecord(
            user_id="user_synth_04",
            name="Charlie Alternate",
            email="charlie_alt@example.com",
            phone="+1 555 0303",  # duplicate phone collision!
            email_hash="hash_charlie_alt",
            updated_at=self.t0,
        )

        self.identities = {
            self.u1.user_id: self.u1,
            self.u2.user_id: self.u2,
            self.u3.user_id: self.u3,
            self.u4.user_id: self.u4,
        }

        # Audit logs for User 1:
        # t1: email changed from alice.old@example.com -> alice.mid@example.com
        # t2: email changed from alice.mid@example.com -> alice.smith@example.com
        # t1: phone changed from +1 555 0000 -> +1 555 0101
        self.audit_logs = [
            AuditLogRecord(
                audit_id="audit_s01",
                user_id="user_synth_01",
                event_time=self.t1,
                field_name="email",
                old_value="alice.old@example.com",
                new_value="alice.mid@example.com",
            ),
            AuditLogRecord(
                audit_id="audit_s02",
                user_id="user_synth_01",
                event_time=self.t2,
                field_name="email",
                old_value="alice.mid@example.com",
                new_value="alice.smith@example.com",
            ),
            AuditLogRecord(
                audit_id="audit_s03",
                user_id="user_synth_01",
                event_time=self.t1,
                field_name="phone",
                old_value="+1 555 0000",
                new_value="+1 555 0101",
            ),
        ]

        self.engine = IdentityEngine(self.identities, self.audit_logs)

    # 1. Current email match
    def test_current_email_match(self):
        res = self.engine.resolve_identity("alice.smith@example.com")
        self.assertTrue(res.is_resolved)
        self.assertEqual(res.canonical_user_id, "user_synth_01")
        self.assertEqual(res.primary_relationship, MatchRelationship.CURRENT_EMAIL)
        self.assertEqual(res.confidence, 1.0)
        self.assertEqual(len(res.ambiguities), 0)

    # 2. Historical email match
    def test_historical_email_match(self):
        res = self.engine.resolve_identity("alice.old@example.com")
        self.assertTrue(res.is_resolved)
        self.assertEqual(res.canonical_user_id, "user_synth_01")
        self.assertEqual(res.primary_relationship, MatchRelationship.HISTORICAL_EMAIL)

        # Also test intermediate historical email
        res_mid = self.engine.resolve_identity("alice.mid@example.com")
        self.assertTrue(res_mid.is_resolved)
        self.assertEqual(res_mid.canonical_user_id, "user_synth_01")
        self.assertEqual(res_mid.primary_relationship, MatchRelationship.HISTORICAL_EMAIL)

    # 3. Multiple identifiers in chain
    def test_multiple_identifiers_in_chain(self):
        all_ids = self.engine.get_all_identifiers_for_user("user_synth_01")
        self.assertIn("alice.old@example.com", all_ids["emails"])
        self.assertIn("alice.mid@example.com", all_ids["emails"])
        self.assertIn("alice.smith@example.com", all_ids["emails"])
        self.assertIn("+1 555 0000", all_ids["phones"])
        self.assertIn("+1 555 0101", all_ids["phones"])

    # 4. Identifier collision
    def test_identifier_collision(self):
        # Phone +1 555 0303 is shared by u3 and u4
        res = self.engine.resolve_identity("+1 555 0303")
        self.assertFalse(res.is_resolved)
        self.assertIsNone(res.canonical_user_id)
        self.assertTrue(any("collision" in amb.lower() for amb in res.ambiguities))

    # 5. Unrelated user with similar identifier
    def test_unrelated_user_similar_identifier(self):
        # Look up similar but distinct email
        res = self.engine.resolve_identity("alice.smith2@example.com")
        self.assertFalse(res.is_resolved)
        self.assertIsNone(res.canonical_user_id)

    # 6. Identity changed before audit_at
    def test_identity_changed_before_audit_at(self):
        # audit_at is after t2 (e.g. t3). Active email should be alice.smith@example.com
        state = self.engine.get_identity_at("user_synth_01", self.t3)
        self.assertIsNotNone(state)
        self.assertEqual(state["email"], "alice.smith@example.com")

    # 7. Identity changed after audit_at
    def test_identity_changed_after_audit_at(self):
        # Suppose audit_at was before t2 (e.g. between t1 and t2)
        mid_time = parse_iso_datetime("2025-09-01T00:00:00Z")
        state = self.engine.get_identity_at("user_synth_01", mid_time)
        self.assertIsNotNone(state)
        # At mid_time, email was alice.mid@example.com, NOT alice.smith@example.com
        self.assertEqual(state["email"], "alice.mid@example.com")

        # Before t1
        early_time = parse_iso_datetime("2025-03-01T00:00:00Z")
        state_early = self.engine.get_identity_at("user_synth_01", early_time)
        self.assertEqual(state_early["email"], "alice.old@example.com")

    # 8. Missing identity
    def test_missing_identity(self):
        res = self.engine.resolve_identity("non_existent@example.com")
        self.assertFalse(res.is_resolved)
        self.assertIsNone(res.canonical_user_id)
        self.assertIn("not found", res.ambiguities[0].lower())

    # 9. Duplicate identity records handling in loader
    def test_duplicate_records_loader(self):
        loader = DataLoader("dataset")
        # Ensure loader diagnostics track duplicate detection without crashing
        self.assertIsInstance(loader.diagnostics["duplicates"], dict)

    # 10. Malformed records
    def test_malformed_records(self):
        # Empty string
        res = self.engine.resolve_identity("")
        self.assertFalse(res.is_resolved)
        # Whitespace
        res_ws = self.engine.resolve_identity("   ")
        self.assertFalse(res_ws.is_resolved)

    # 11. Intent classifier tests
    def test_intent_classification(self):
        # Deletion authorized
        is_del, r_type, _ = IntentClassifier.classify("Please delete my account and personal data.")
        self.assertTrue(is_del)
        self.assertEqual(r_type, RequestType.DELETION)

        # Portability request
        is_del, r_type, _ = IntentClassifier.classify("I'd like to download my account information in a portable format. Please keep the account as it is.")
        self.assertFalse(is_del)
        self.assertEqual(r_type, RequestType.PORTABILITY_REQUEST)

        # Access request
        is_del, r_type, _ = IntentClassifier.classify("I need a copy of last year's invoices for my records. Please leave my profile and purchase history in place.")
        self.assertFalse(is_del)
        self.assertEqual(r_type, RequestType.ACCESS_REQUEST)

        # Marketing opt-out
        is_del, r_type, _ = IntentClassifier.classify("Please stop the promotional emails. I still need the account and my order history, so I am not asking for deletion.")
        self.assertFalse(is_del)
        self.assertEqual(r_type, RequestType.MARKETING_OPT_OUT)


if __name__ == "__main__":
    unittest.main()
