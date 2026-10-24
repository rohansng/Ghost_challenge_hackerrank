"""
identity_engine.py - Deterministic Identity Resolution & Temporal Graph.
Constructs identity graphs, reconstructs temporal states, tracks historical identifiers,
and prevents contamination across users.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple, Any

from code.models import (
    UserIdentityRecord,
    AuditLogRecord,
    IdentityNode,
    IdentifierInterval,
    MatchRelationship,
    IdentifierMatch,
)
from code.loaders import normalize_email, normalize_phone


@dataclass
class IdentityResolutionResult:
    is_resolved: bool
    canonical_user_id: Optional[str]
    identity_node: Optional[IdentityNode]
    primary_relationship: Optional[MatchRelationship]
    confidence: float
    matched_identifiers: List[IdentifierMatch]
    ambiguities: List[str]


class IdentityEngine:
    """Deterministic Multi-Hop Temporal Identity Resolution Engine."""

    def __init__(self, identities: Dict[str, UserIdentityRecord], audit_logs: List[AuditLogRecord]):
        self.identities = identities
        self.audit_logs = audit_logs
        
        # Primary storage
        self.nodes: Dict[str, IdentityNode] = {}
        
        # Inverted indexes for fast, deterministic reverse lookups
        self.email_to_user_ids: Dict[str, Set[str]] = defaultdict(set)
        self.phone_to_user_ids: Dict[str, Set[str]] = defaultdict(set)
        self.hash_to_user_ids: Dict[str, Set[str]] = defaultdict(set)
        self.name_to_user_ids: Dict[str, Set[str]] = defaultdict(set)
        
        self._build_graph()

    def _build_graph(self) -> None:
        """Constructs IdentityNode objects and stitches temporal audit trails."""
        # Step 1: Initialize nodes from current snapshot
        for uid, rec in self.identities.items():
            node = IdentityNode(
                canonical_user_id=uid,
                current_name=rec.name,
                current_email=rec.email,
                current_phone=rec.phone,
                current_email_hash=rec.email_hash,
                updated_at=rec.updated_at,
            )
            node.all_names.add(rec.name)
            node.all_emails.add(rec.email)
            node.all_phones.add(rec.phone)
            node.all_hashes.add(rec.email_hash)
            self.nodes[uid] = node

            # Populate current inverted indexes
            self.email_to_user_ids[rec.email].add(uid)
            self.phone_to_user_ids[rec.phone].add(uid)
            self.hash_to_user_ids[rec.email_hash].add(uid)
            self.name_to_user_ids[rec.name].add(uid)

        # Step 2: Ingest audit history per user chronologically
        user_audits: Dict[str, List[AuditLogRecord]] = defaultdict(list)
        for al in self.audit_logs:
            user_audits[al.user_id].append(al)

        for uid, events in user_audits.items():
            if uid not in self.nodes:
                continue
            node = self.nodes[uid]
            # Ensure chronological order
            events.sort(key=lambda e: (e.event_time, e.audit_id))

            # Group by field_name
            by_field: Dict[str, List[AuditLogRecord]] = defaultdict(list)
            for ev in events:
                by_field[ev.field_name].append(ev)

            # Build temporal intervals for emails
            if "email" in by_field:
                email_events = by_field["email"]
                prev_time = None
                for i, ev in enumerate(email_events):
                    old_em = normalize_email(ev.old_value)
                    new_em = normalize_email(ev.new_value)
                    node.all_emails.add(old_em)
                    node.all_emails.add(new_em)
                    self.email_to_user_ids[old_em].add(uid)
                    self.email_to_user_ids[new_em].add(uid)

                    # Interval for old_em: valid from prev_time (or inception) to ev.event_time
                    node.email_intervals.append(
                        IdentifierInterval(
                            field_name="email",
                            value=old_em,
                            valid_from=prev_time,
                            valid_to=ev.event_time,
                            source_audit_id=ev.audit_id,
                        )
                    )
                    prev_time = ev.event_time

                # Last interval: valid from last event_time to indefinite
                last_em = normalize_email(email_events[-1].new_value)
                node.email_intervals.append(
                    IdentifierInterval(
                        field_name="email",
                        value=last_em,
                        valid_from=email_events[-1].event_time,
                        valid_to=None,
                        source_audit_id=email_events[-1].audit_id,
                    )
                )

            # Build temporal intervals for phones
            if "phone" in by_field:
                phone_events = by_field["phone"]
                prev_time = None
                for i, ev in enumerate(phone_events):
                    old_ph = normalize_phone(ev.old_value)
                    new_ph = normalize_phone(ev.new_value)
                    node.all_phones.add(old_ph)
                    node.all_phones.add(new_ph)
                    self.phone_to_user_ids[old_ph].add(uid)
                    self.phone_to_user_ids[new_ph].add(uid)

                    node.phone_intervals.append(
                        IdentifierInterval(
                            field_name="phone",
                            value=old_ph,
                            valid_from=prev_time,
                            valid_to=ev.event_time,
                            source_audit_id=ev.audit_id,
                        )
                    )
                    prev_time = ev.event_time

                last_ph = normalize_phone(phone_events[-1].new_value)
                node.phone_intervals.append(
                    IdentifierInterval(
                        field_name="phone",
                        value=last_ph,
                        valid_from=phone_events[-1].event_time,
                        valid_to=None,
                        source_audit_id=phone_events[-1].audit_id,
                    )
                )

            # Build temporal intervals for email hashes
            if "email_hash" in by_field:
                hash_events = by_field["email_hash"]
                prev_time = None
                for i, ev in enumerate(hash_events):
                    old_h = ev.old_value.strip()
                    new_h = ev.new_value.strip()
                    node.all_hashes.add(old_h)
                    node.all_hashes.add(new_h)
                    self.hash_to_user_ids[old_h].add(uid)
                    self.hash_to_user_ids[new_h].add(uid)

                    node.hash_intervals.append(
                        IdentifierInterval(
                            field_name="email_hash",
                            value=old_h,
                            valid_from=prev_time,
                            valid_to=ev.event_time,
                            source_audit_id=ev.audit_id,
                        )
                    )
                    prev_time = ev.event_time

                last_h = hash_events[-1].new_value.strip()
                node.hash_intervals.append(
                    IdentifierInterval(
                        field_name="email_hash",
                        value=last_h,
                        valid_from=hash_events[-1].event_time,
                        valid_to=None,
                        source_audit_id=hash_events[-1].audit_id,
                    )
                )

    def resolve_identity(self, raw_identifier: str) -> IdentityResolutionResult:
        """
        Deterministically resolves any candidate identifier to a canonical user entity.
        Supports current emails, historical emails, phones, hashes, and user_ids.
        Detects collisions and retains ambiguity rather than falsely conflating identities.
        """
        if not raw_identifier or not raw_identifier.strip():
            return IdentityResolutionResult(
                is_resolved=False,
                canonical_user_id=None,
                identity_node=None,
                primary_relationship=None,
                confidence=0.0,
                matched_identifiers=[],
                ambiguities=["Empty identifier provided"],
            )

        identifier = raw_identifier.strip()
        matches: List[IdentifierMatch] = []
        ambiguities: List[str] = []

        # 1. Direct user_id check
        if identifier in self.nodes:
            matches.append(
                IdentifierMatch(
                    matched_value=identifier,
                    relationship=MatchRelationship.USER_ID,
                    confidence=1.0,
                    source="user_identities",
                )
            )
            node = self.nodes[identifier]
            return IdentityResolutionResult(
                is_resolved=True,
                canonical_user_id=identifier,
                identity_node=node,
                primary_relationship=MatchRelationship.USER_ID,
                confidence=1.0,
                matched_identifiers=matches,
                ambiguities=[],
            )

        # 2. Email lookup (case-insensitive)
        norm_email = normalize_email(identifier)
        if norm_email in self.email_to_user_ids:
            candidate_uids = self.email_to_user_ids[norm_email]
            if len(candidate_uids) > 1:
                ambiguities.append(
                    f"Identifier collision: email {norm_email} is associated with multiple users: {sorted(candidate_uids)}"
                )
                return IdentityResolutionResult(
                    is_resolved=False,
                    canonical_user_id=None,
                    identity_node=None,
                    primary_relationship=None,
                    confidence=0.0,
                    matched_identifiers=[],
                    ambiguities=ambiguities,
                )

            uid = next(iter(candidate_uids))
            node = self.nodes[uid]
            rel = (
                MatchRelationship.CURRENT_EMAIL
                if norm_email == node.current_email
                else MatchRelationship.HISTORICAL_EMAIL
            )
            matches.append(
                IdentifierMatch(
                    matched_value=norm_email,
                    relationship=rel,
                    confidence=1.0 if rel == MatchRelationship.CURRENT_EMAIL else 0.95,
                    source="user_identities" if rel == MatchRelationship.CURRENT_EMAIL else "user_audit_log",
                )
            )
            return IdentityResolutionResult(
                is_resolved=True,
                canonical_user_id=uid,
                identity_node=node,
                primary_relationship=rel,
                confidence=1.0,
                matched_identifiers=matches,
                ambiguities=[],
            )

        # 3. Phone lookup
        norm_phone = normalize_phone(identifier)
        if norm_phone in self.phone_to_user_ids:
            candidate_uids = self.phone_to_user_ids[norm_phone]
            if len(candidate_uids) > 1:
                ambiguities.append(
                    f"Identifier collision: phone {norm_phone} associated with multiple users: {sorted(candidate_uids)}"
                )
                return IdentityResolutionResult(
                    is_resolved=False,
                    canonical_user_id=None,
                    identity_node=None,
                    primary_relationship=None,
                    confidence=0.0,
                    matched_identifiers=[],
                    ambiguities=ambiguities,
                )

            uid = next(iter(candidate_uids))
            node = self.nodes[uid]
            rel = (
                MatchRelationship.CURRENT_PHONE
                if norm_phone == node.current_phone
                else MatchRelationship.HISTORICAL_PHONE
            )
            matches.append(
                IdentifierMatch(
                    matched_value=norm_phone,
                    relationship=rel,
                    confidence=0.95 if rel == MatchRelationship.CURRENT_PHONE else 0.90,
                    source="user_identities" if rel == MatchRelationship.CURRENT_PHONE else "user_audit_log",
                )
            )
            return IdentityResolutionResult(
                is_resolved=True,
                canonical_user_id=uid,
                identity_node=node,
                primary_relationship=rel,
                confidence=0.95,
                matched_identifiers=matches,
                ambiguities=[],
            )

        # 4. Email Hash lookup
        if identifier in self.hash_to_user_ids:
            candidate_uids = self.hash_to_user_ids[identifier]
            if len(candidate_uids) > 1:
                ambiguities.append(
                    f"Hash collision: {identifier} associated with multiple users: {sorted(candidate_uids)}"
                )
                return IdentityResolutionResult(
                    is_resolved=False,
                    canonical_user_id=None,
                    identity_node=None,
                    primary_relationship=None,
                    confidence=0.0,
                    matched_identifiers=[],
                    ambiguities=ambiguities,
                )

            uid = next(iter(candidate_uids))
            node = self.nodes[uid]
            rel = (
                MatchRelationship.EMAIL_HASH
                if identifier == node.current_email_hash
                else MatchRelationship.HISTORICAL_HASH
            )
            matches.append(
                IdentifierMatch(
                    matched_value=identifier,
                    relationship=rel,
                    confidence=0.99,
                    source="user_identities" if rel == MatchRelationship.EMAIL_HASH else "user_audit_log",
                )
            )
            return IdentityResolutionResult(
                is_resolved=True,
                canonical_user_id=uid,
                identity_node=node,
                primary_relationship=rel,
                confidence=0.99,
                matched_identifiers=matches,
                ambiguities=[],
            )

        return IdentityResolutionResult(
            is_resolved=False,
            canonical_user_id=None,
            identity_node=None,
            primary_relationship=None,
            confidence=0.0,
            matched_identifiers=[],
            ambiguities=[f"Identifier not found in identity graph: {identifier}"],
        )

    def get_identity_at(self, user_id: str, at_time: datetime) -> Optional[Dict[str, str]]:
        """Reconstruct identity state as of timestamp at_time."""
        if user_id not in self.nodes:
            return None
        return self.nodes[user_id].get_identity_at(at_time)

    def get_all_identifiers_for_user(self, user_id: str) -> Dict[str, Set[str]]:
        """Returns all historical and current identifiers for the given user."""
        if user_id not in self.nodes:
            return {}
        node = self.nodes[user_id]
        return {
            "user_id": {user_id},
            "emails": set(node.all_emails),
            "phones": set(node.all_phones),
            "hashes": set(node.all_hashes),
            "names": set(node.all_names),
        }
