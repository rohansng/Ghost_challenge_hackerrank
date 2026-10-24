"""
Deletion Policy Engine (Phase 3)
Parses deletion_rules.csv into structured PolicyRule models and evaluates
reconstructed resource state snapshots against deletion policy rules.
Generates explainable PolicyProof instances strictly adhering to challenge contracts.
"""

import csv
import logging
import os
from typing import List, Dict, Any, Optional, Tuple

from code.evidence_models import ResourceStateSnapshot, ObservedState
from code.models import Operation, ResourceState, Phase, Step
from code.policy_models import (
    PolicyAction,
    ConditionType,
    RuleScope,
    PolicyRule,
    PolicyProof,
)

logger = logging.getLogger("ghost_data.policy_engine")


class PolicyParser:
    """
    Parses dataset/deletion_rules.csv into structured PolicyRule instances.
    Extracts data categories, conditions, actions, scopes, and field constraints.
    """

    def __init__(self, rules_file_path: str = "dataset/deletion_rules.csv"):
        self.rules_file_path = rules_file_path
        self.diagnostics: Dict[str, Any] = {
            "loaded_rules": 0,
            "errors": [],
            "warnings": [],
        }

    def parse(self) -> Dict[str, PolicyRule]:
        rules: Dict[str, PolicyRule] = {}

        if not os.path.exists(self.rules_file_path):
            logger.warning(f"Policy file {self.rules_file_path} not found; using canonical ruleset.")
            return self._build_canonical_ruleset()

        expected_cols = {"rule_id", "data_category", "condition", "required_action"}
        with open(self.rules_file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if not expected_cols.issubset(set(reader.fieldnames or [])):
                missing = expected_cols - set(reader.fieldnames or [])
                raise ValueError(f"Missing required columns in {self.rules_file_path}: {missing}")

            for line_no, row in enumerate(reader, start=2):
                rid = row["rule_id"].strip()
                cat = row["data_category"].strip()
                cond = row["condition"].strip()
                act_str = row["required_action"].strip().upper()

                try:
                    action = PolicyAction(act_str)
                except ValueError:
                    action = PolicyAction.DELETE
                    self.diagnostics["warnings"].append(f"Line {line_no}: Unknown action '{act_str}', defaulting to DELETE")

                cond_type, scope, permitted, prohibited = self._infer_condition_and_fields(cat, cond, action)

                rule = PolicyRule(
                    rule_id=rid,
                    data_category=cat,
                    condition_text=cond,
                    condition_type=cond_type,
                    required_action=action,
                    scope=scope,
                    retained_permitted_fields=permitted,
                    prohibited_fields=prohibited,
                    allows_retention=(action == PolicyAction.RETAIN),
                    requires_redaction=(action == PolicyAction.REDACT or cat == "ACCOUNT_TOMBSTONE"),
                    requires_anonymization=(action == PolicyAction.ANONYMIZE),
                    requires_tombstone=(cat == "ACCOUNT_TOMBSTONE"),
                    requires_restore_block=(cat == "BACKUP_ARCHIVE"),
                )
                rules[rid] = rule
                self.diagnostics["loaded_rules"] += 1

        # Register operational sync flow rule
        rules["rule_sync"] = PolicyRule(
            rule_id="rule_sync",
            data_category="CONNECTOR_SUBSCRIPTION",
            condition_text="Active connector can replicate or recreate deleted data",
            condition_type=ConditionType.CONNECTOR_ACTIVE,
            required_action=PolicyAction.DELETE,
            scope=RuleScope.SYSTEM,
            retained_permitted_fields=[],
            prohibited_fields=["active_sync_channel"],
        )

        return rules

    def _infer_condition_and_fields(
        self,
        category: str,
        condition: str,
        action: PolicyAction,
    ) -> Tuple[ConditionType, RuleScope, List[str], List[str]]:
        cat_upper = category.upper()
        cond_lower = condition.lower()

        if "tombstone" in cat_upper or "tombstone" in cond_lower:
            return (
                ConditionType.ACCOUNT_TOMBSTONE,
                RuleScope.FIELD,
                ["user_id", "deleted_at", "account_status"],
                ["email", "phone", "name", "email_hash", "address"],
            )
        elif "support_message" in cat_upper or "shared" in cond_lower:
            return (
                ConditionType.SHARED_CONTEXT,
                RuleScope.CONDITIONAL,
                ["ticket_id", "message_id", "timestamp", "agent_id", "order_id", "shared_context"],
                ["customer_name", "customer_email", "customer_phone", "email_hash"],
            )
        elif "attachment" in cat_upper:
            return (
                ConditionType.SUBJECT_ATTACHMENT,
                RuleScope.RESOURCE,
                [],
                ["file_path", "attachment_content", "user_id"],
            )
        elif "analytics" in cat_upper or "telemetry" in cat_upper or "attributable" in cond_lower:
            return (
                ConditionType.ATTRIBUTABLE_TO_USER,
                RuleScope.FIELD,
                ["aggregated_metrics", "event_counts", "funnel_data", "duration_ms"],
                ["user_id", "email", "device_fingerprint", "ip_address", "attribution_token"],
            )
        elif "delivery_log" in cat_upper or "contains a user email" in cond_lower:
            return (
                ConditionType.CONTAINS_EMAIL,
                RuleScope.FIELD,
                ["delivery_id", "status", "timestamp", "template_id"],
                ["recipient_email", "email"],
            )
        elif "security_audit_log" in cat_upper or "retention period" in cond_lower:
            return (
                ConditionType.WITHIN_RETENTION,
                RuleScope.CONDITIONAL,
                ["audit_id", "event_time", "actor", "action", "ip_hash"],
                ["unneeded_pii", "cleartext_passwords"],
            )
        elif "legal_hold" in cat_upper or "legal hold" in cond_lower:
            return (
                ConditionType.LEGAL_HOLD_ACTIVE,
                RuleScope.CONDITIONAL,
                ["case_reference", "dispute_id", "hold_timestamp", "evidence_payload"],
                [],
            )
        elif "backup" in cat_upper or "restore" in cond_lower:
            return (
                ConditionType.RESTORE_BLOCKED,
                RuleScope.OPERATION,
                ["archive_id", "snapshot_time", "checksum"],
                ["active_restore_endpoint"],
            )
        elif "always" in cond_lower:
            return (
                ConditionType.ALWAYS,
                RuleScope.DATA_CATEGORY,
                [],
                ["user_id", "email", "phone", "name", "record_data"],
            )
        else:
            return (
                ConditionType.UNKNOWN,
                RuleScope.DATA_CATEGORY,
                [],
                ["user_id", "email"],
            )

    def _build_canonical_ruleset(self) -> Dict[str, PolicyRule]:
        """Canonical fallback mapping for all 15 rules when file is unavailable."""
        rules = {}
        canonical = [
            ("rule_01", "USER_PROFILE", "Always", PolicyAction.DELETE),
            ("rule_02", "SECONDARY_IDENTIFIER", "Always", PolicyAction.DELETE),
            ("rule_03", "SEARCH_INDEX_ENTRY", "Always", PolicyAction.DELETE),
            ("rule_04", "CACHE_ENTRY", "Always,DELETE", PolicyAction.DELETE),
            ("rule_05", "SUPPORT_MESSAGE", "Conversation contains shared customer, agent, or order context that must be retained", PolicyAction.REDACT),
            ("rule_06", "SUPPORT_ATTACHMENT", "Attachment belongs only to the deletion subject", PolicyAction.DELETE),
            ("rule_07", "ANALYTICS_PROFILE", "Record is still attributable to a user", PolicyAction.ANONYMIZE),
            ("rule_08", "PRODUCT_TELEMETRY", "Record is still attributable to a user", PolicyAction.ANONYMIZE),
            ("rule_09", "USER_EXPORT", "Always", PolicyAction.DELETE),
            ("rule_10", "MARKETING_PROFILE", "Always", PolicyAction.DELETE),
            ("rule_11", "EMAIL_DELIVERY_LOG", "Log contains a user email address", PolicyAction.REDACT),
            ("rule_12", "SECURITY_AUDIT_LOG", "Record is within the supplied retention period", PolicyAction.RETAIN),
            ("rule_13", "LEGAL_HOLD_RECORD", "A supplied legal hold is active", PolicyAction.RETAIN),
            ("rule_14", "BACKUP_ARCHIVE", "Restore access can be blocked", PolicyAction.RETAIN),
            ("rule_15", "ACCOUNT_TOMBSTONE", "Account is deleted and only a stable internal user_id is needed to preserve references to retained records", PolicyAction.REDACT),
        ]
        for rid, cat, cond, act in canonical:
            c_type, scope, perm, proh = self._infer_condition_and_fields(cat, cond, act)
            rules[rid] = PolicyRule(
                rule_id=rid,
                data_category=cat,
                condition_text=cond,
                condition_type=c_type,
                required_action=act,
                scope=scope,
                retained_permitted_fields=perm,
                prohibited_fields=proh,
                allows_retention=(act == PolicyAction.RETAIN),
                requires_redaction=(act == PolicyAction.REDACT or cat == "ACCOUNT_TOMBSTONE"),
                requires_anonymization=(act == PolicyAction.ANONYMIZE),
                requires_tombstone=(cat == "ACCOUNT_TOMBSTONE"),
                requires_restore_block=(cat == "BACKUP_ARCHIVE"),
            )
        rules["rule_sync"] = PolicyRule(
            rule_id="rule_sync",
            data_category="CONNECTOR_SUBSCRIPTION",
            condition_text="Active connector can replicate or recreate deleted data",
            condition_type=ConditionType.CONNECTOR_ACTIVE,
            required_action=PolicyAction.DELETE,
            scope=RuleScope.SYSTEM,
            retained_permitted_fields=[],
            prohibited_fields=["active_sync_channel"],
        )
        return rules


class PolicyEngine:
    """
    Evaluates proven resource snapshots against deletion policy rules.
    Produces deterministic, explainable PolicyProof records.
    Never declares COMPLETE based on claims; checks actual state at audit_at.
    """

    def __init__(self, rules_file_path: str = "dataset/deletion_rules.csv"):
        self.parser = PolicyParser(rules_file_path)
        self.rules: Dict[str, PolicyRule] = self.parser.parse()
        self.diagnostics: Dict[str, Any] = {
            "evaluations_count": 0,
            "compliant_count": 0,
            "violations_count": 0,
            "rule_invocations": {},
            "unknown_categories": set(),
        }

    def match_rule(self, data_category: str) -> Optional[PolicyRule]:
        """Matches a data category string to the authoritative PolicyRule."""
        cat_clean = data_category.strip().upper()

        # 1. Exact match on category
        for rule in self.rules.values():
            if rule.data_category.upper() == cat_clean:
                return rule

        # 2. Key patterns
        if "TOMBSTONE" in cat_clean:
            return self.rules.get("rule_15")
        if "SECONDARY_IDENTIFIER" in cat_clean:
            return self.rules.get("rule_02")
        if "USER_PROFILE" in cat_clean or cat_clean in ("ACCOUNT", "USER", "PROFILE", "CUSTOMER"):
            return self.rules.get("rule_01")
        if "SEARCH" in cat_clean:
            return self.rules.get("rule_03")
        if "CACHE" in cat_clean:
            return self.rules.get("rule_04")
        if "SUPPORT_ATTACHMENT" in cat_clean or "ATTACHMENT" in cat_clean:
            return self.rules.get("rule_06")
        if "SUPPORT_MESSAGE" in cat_clean or "SUPPORT" in cat_clean or "TICKET" in cat_clean:
            return self.rules.get("rule_05")
        if "ANALYTICS" in cat_clean:
            return self.rules.get("rule_07")
        if "TELEMETRY" in cat_clean:
            return self.rules.get("rule_08")
        if "EXPORT" in cat_clean:
            return self.rules.get("rule_09")
        if "MARKETING" in cat_clean:
            return self.rules.get("rule_10")
        if "EMAIL_DELIVERY_LOG" in cat_clean or "DELIVERY_LOG" in cat_clean:
            return self.rules.get("rule_11")
        if "SECURITY_AUDIT_LOG" in cat_clean or "AUDIT" in cat_clean:
            return self.rules.get("rule_12")
        if "LEGAL_HOLD" in cat_clean or "LEGAL" in cat_clean:
            return self.rules.get("rule_13")
        if "BACKUP" in cat_clean or "ARCHIVE" in cat_clean:
            return self.rules.get("rule_14")
        if "CONNECTOR" in cat_clean or "DATA_FLOW" in cat_clean or "SYNC" in cat_clean:
            return self.rules.get("rule_sync")

        return None

    def evaluate_resource_policy(
        self,
        snapshot: ResourceStateSnapshot,
    ) -> PolicyProof:
        """
        Determines compliance, prohibited PII, retention validity, and required
        operations for a single proven resource snapshot at audit_at.
        Returns a rich, explainable PolicyProof object.
        """
        self.diagnostics["evaluations_count"] += 1
        cat = snapshot.data_category.upper()
        state = snapshot.proven_state
        sys_id = snapshot.system_id
        res_id = snapshot.resource_id
        ev_id = snapshot.cited_evidence_id
        metadata = getattr(snapshot, "metadata", None) or {}

        rule = self.match_rule(cat)

        # -------------------------------------------------------------
        # UNKNOWN RESOURCE TYPE OR MISSING RULE
        # -------------------------------------------------------------
        if not rule:
            self.diagnostics["unknown_categories"].add(cat)
            is_present = state in (ObservedState.PRESENT, ObservedState.ACTIVE, ObservedState.UNKNOWN)
            if is_present:
                self.diagnostics["violations_count"] += 1
                finding = Step(
                    step_no=0,
                    phase=Phase.FINDING,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.REPORT_REMAINING_RECORD,
                    state=ResourceState.PRESENT,
                    evidence_id=ev_id,
                )
                remediation = Step(
                    step_no=0,
                    phase=Phase.REMEDIATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.DELETE_RECORD,
                    state=ResourceState.ABSENT,
                    evidence_id="",
                )
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.VERIFY_RECORD_ABSENT,
                    state=ResourceState.ABSENT,
                    evidence_id="",
                )
                return PolicyProof(
                    resource_id=res_id,
                    system_id=sys_id,
                    data_category=cat,
                    rule_id="rule_unknown",
                    condition_text="No explicit policy rule found; applying safe deletion requirement",
                    condition_met=False,
                    required_action=PolicyAction.DELETE,
                    actual_state=state,
                    is_compliant=False,
                    has_prohibited_pii=True,
                    is_retention_permitted=False,
                    failure_reason=f"Unknown resource category '{cat}' remains present at audit_at; default safe policy requires deletion.",
                    evidence_proof_id=ev_id,
                    finding_step=finding,
                    remediation_step=remediation,
                    verification_step=verification,
                )
            else:
                self.diagnostics["compliant_count"] += 1
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.VERIFY_RECORD_ABSENT,
                    state=ResourceState.ABSENT,
                    evidence_id=ev_id,
                )
                return PolicyProof(
                    resource_id=res_id,
                    system_id=sys_id,
                    data_category=cat,
                    rule_id="rule_unknown",
                    condition_text="No explicit policy rule found; record verified absent",
                    condition_met=True,
                    required_action=PolicyAction.DELETE,
                    actual_state=state,
                    is_compliant=True,
                    has_prohibited_pii=False,
                    is_retention_permitted=False,
                    failure_reason=None,
                    evidence_proof_id=ev_id,
                    finding_step=None,
                    remediation_step=None,
                    verification_step=verification,
                )

        rid = rule.rule_id
        self.diagnostics["rule_invocations"][rid] = self.diagnostics["rule_invocations"].get(rid, 0) + 1

        # -------------------------------------------------------------
        # 0. OPERATIONAL DATA FLOW / SYNC CONNECTOR
        # -------------------------------------------------------------
        if cat in ("CONNECTOR_SUBSCRIPTION", "DATA_FLOW") or rid == "rule_sync" or "CONNECTOR" in cat or "DATA_FLOW" in cat:
            is_active_flow = state in (ObservedState.ACTIVE, ObservedState.PRESENT, ObservedState.ENABLED)
            if is_active_flow:
                self.diagnostics["violations_count"] += 1
                finding = Step(
                    step_no=0,
                    phase=Phase.FINDING,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.REPORT_ACTIVE_DATA_FLOW,
                    state=ResourceState.ACTIVE,
                    evidence_id=ev_id,
                )
                remediation = Step(
                    step_no=0,
                    phase=Phase.REMEDIATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.DISABLE_DATA_FLOW,
                    state=ResourceState.DISABLED,
                    evidence_id="",
                )
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.VERIFY_DATA_FLOW_DISABLED,
                    state=ResourceState.DISABLED,
                    evidence_id="",
                )
                return PolicyProof(
                    resource_id=res_id,
                    system_id=sys_id,
                    data_category=cat,
                    rule_id=rid,
                    condition_text=rule.condition_text,
                    condition_met=False,
                    required_action=PolicyAction.DELETE,
                    actual_state=state,
                    is_compliant=False,
                    has_prohibited_pii=False,
                    is_retention_permitted=False,
                    recreation_risk="Active connector can replicate or recreate deleted data",
                    failure_reason=f"Active data flow {res_id} can copy or recreate deleted data.",
                    evidence_proof_id=ev_id,
                    finding_step=finding,
                    remediation_step=remediation,
                    verification_step=verification,
                )
            else:
                self.diagnostics["compliant_count"] += 1
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.VERIFY_DATA_FLOW_DISABLED,
                    state=ResourceState.DISABLED,
                    evidence_id=ev_id,
                )
                return PolicyProof(
                    resource_id=res_id,
                    system_id=sys_id,
                    data_category=cat,
                    rule_id=rid,
                    condition_text=rule.condition_text,
                    condition_met=True,
                    required_action=PolicyAction.DELETE,
                    actual_state=state,
                    is_compliant=True,
                    has_prohibited_pii=False,
                    is_retention_permitted=False,
                    recreation_risk=None,
                    failure_reason=None,
                    evidence_proof_id=ev_id,
                    finding_step=None,
                    remediation_step=None,
                    verification_step=verification,
                )

        # -------------------------------------------------------------
        # 1. ACTION: DELETE
        # Rules: 01, 02, 03, 04, 06, 09, 10
        # -------------------------------------------------------------
        elif rule.required_action == PolicyAction.DELETE:
            is_present = state in (ObservedState.PRESENT, ObservedState.ACTIVE, ObservedState.UNKNOWN)
            if is_present:
                self.diagnostics["violations_count"] += 1
                finding = Step(
                    step_no=0,
                    phase=Phase.FINDING,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.REPORT_REMAINING_RECORD,
                    state=ResourceState.PRESENT,
                    evidence_id=ev_id,
                )
                remediation = Step(
                    step_no=0,
                    phase=Phase.REMEDIATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.DELETE_RECORD,
                    state=ResourceState.ABSENT,
                    evidence_id="",
                )
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.VERIFY_RECORD_ABSENT,
                    state=ResourceState.ABSENT,
                    evidence_id="",
                )
                return PolicyProof(
                    resource_id=res_id,
                    system_id=sys_id,
                    data_category=cat,
                    rule_id=rid,
                    condition_text=rule.condition_text,
                    condition_met=True,
                    required_action=PolicyAction.DELETE,
                    actual_state=state,
                    is_compliant=False,
                    has_prohibited_pii=True,
                    is_retention_permitted=False,
                    failure_reason=f"Record {res_id} in category {cat} still exists at audit_at, violating {rid}.",
                    evidence_proof_id=ev_id,
                    finding_step=finding,
                    remediation_step=remediation,
                    verification_step=verification,
                )
            else:
                self.diagnostics["compliant_count"] += 1
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.VERIFY_RECORD_ABSENT,
                    state=ResourceState.ABSENT,
                    evidence_id=ev_id,
                )
                return PolicyProof(
                    resource_id=res_id,
                    system_id=sys_id,
                    data_category=cat,
                    rule_id=rid,
                    condition_text=rule.condition_text,
                    condition_met=True,
                    required_action=PolicyAction.DELETE,
                    actual_state=state,
                    is_compliant=True,
                    has_prohibited_pii=False,
                    is_retention_permitted=False,
                    failure_reason=None,
                    evidence_proof_id=ev_id,
                    finding_step=None,
                    remediation_step=None,
                    verification_step=verification,
                )

        # -------------------------------------------------------------
        # 2. ACTION: ANONYMIZE
        # Rules: 07, 08 (ANALYTICS_PROFILE, PRODUCT_TELEMETRY)
        # -------------------------------------------------------------
        elif rule.required_action == PolicyAction.ANONYMIZE:
            is_attributable = (state in (ObservedState.PRESENT, ObservedState.ACTIVE, ObservedState.UNKNOWN)) or metadata.get("attributable", False)
            if is_attributable:
                self.diagnostics["violations_count"] += 1
                finding = Step(
                    step_no=0,
                    phase=Phase.FINDING,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.REPORT_EXPOSED_PII,
                    state=ResourceState.PRESENT,
                    evidence_id=ev_id,
                )
                remediation = Step(
                    step_no=0,
                    phase=Phase.REMEDIATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.ANONYMIZE_RECORD,
                    state=ResourceState.ANONYMIZED,
                    evidence_id="",
                )
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.VERIFY_RECORD_ANONYMIZED,
                    state=ResourceState.ANONYMIZED,
                    evidence_id="",
                )
                return PolicyProof(
                    resource_id=res_id,
                    system_id=sys_id,
                    data_category=cat,
                    rule_id=rid,
                    condition_text=rule.condition_text,
                    condition_met=True,
                    required_action=PolicyAction.ANONYMIZE,
                    actual_state=state,
                    is_compliant=False,
                    has_prohibited_pii=True,
                    is_retention_permitted=True,
                    failure_reason=f"Telemetry/Analytics record {res_id} remains attributable to user at audit_at.",
                    evidence_proof_id=ev_id,
                    finding_step=finding,
                    remediation_step=remediation,
                    verification_step=verification,
                )
            else:
                self.diagnostics["compliant_count"] += 1
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.VERIFY_RECORD_ANONYMIZED,
                    state=ResourceState.ANONYMIZED,
                    evidence_id=ev_id,
                )
                return PolicyProof(
                    resource_id=res_id,
                    system_id=sys_id,
                    data_category=cat,
                    rule_id=rid,
                    condition_text=rule.condition_text,
                    condition_met=True,
                    required_action=PolicyAction.ANONYMIZE,
                    actual_state=state,
                    is_compliant=True,
                    has_prohibited_pii=False,
                    is_retention_permitted=True,
                    failure_reason=None,
                    evidence_proof_id=ev_id,
                    finding_step=None,
                    remediation_step=None,
                    verification_step=verification,
                )

        # -------------------------------------------------------------
        # 3. ACTION: REDACT (including TOMBSTONE)
        # Rules: 05, 11, 15 (SUPPORT_MESSAGE, EMAIL_DELIVERY_LOG, ACCOUNT_TOMBSTONE)
        # -------------------------------------------------------------
        elif rule.required_action in (PolicyAction.REDACT, PolicyAction.TOMBSTONE):
            has_pii = (state in (ObservedState.PRESENT, ObservedState.ACTIVE, ObservedState.UNKNOWN)) or metadata.get("has_prohibited_pii", False)
            if has_pii:
                self.diagnostics["violations_count"] += 1
                finding = Step(
                    step_no=0,
                    phase=Phase.FINDING,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.REPORT_EXPOSED_PII,
                    state=ResourceState.PRESENT,
                    evidence_id=ev_id,
                )
                remediation = Step(
                    step_no=0,
                    phase=Phase.REMEDIATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.REDACT_RECORD,
                    state=ResourceState.REDACTED,
                    evidence_id="",
                )
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.VERIFY_RECORD_REDACTED,
                    state=ResourceState.REDACTED,
                    evidence_id="",
                )
                return PolicyProof(
                    resource_id=res_id,
                    system_id=sys_id,
                    data_category=cat,
                    rule_id=rid,
                    condition_text=rule.condition_text,
                    condition_met=True,
                    required_action=rule.required_action,
                    actual_state=state,
                    is_compliant=False,
                    has_prohibited_pii=True,
                    is_retention_permitted=True,
                    failure_reason=f"Prohibited personal identifiers remain exposed in {cat} {res_id} at audit_at.",
                    evidence_proof_id=ev_id,
                    finding_step=finding,
                    remediation_step=remediation,
                    verification_step=verification,
                )
            else:
                self.diagnostics["compliant_count"] += 1
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.VERIFY_RECORD_REDACTED,
                    state=ResourceState.REDACTED,
                    evidence_id=ev_id,
                )
                return PolicyProof(
                    resource_id=res_id,
                    system_id=sys_id,
                    data_category=cat,
                    rule_id=rid,
                    condition_text=rule.condition_text,
                    condition_met=True,
                    required_action=rule.required_action,
                    actual_state=state,
                    is_compliant=True,
                    has_prohibited_pii=False,
                    is_retention_permitted=True,
                    failure_reason=None,
                    evidence_proof_id=ev_id,
                    finding_step=None,
                    remediation_step=None,
                    verification_step=verification,
                )

        # -------------------------------------------------------------
        # 4. ACTION: RETAIN (Rules 12, 13: SECURITY_AUDIT_LOG, LEGAL_HOLD_RECORD)
        # -------------------------------------------------------------
        elif rule.required_action == PolicyAction.RETAIN and cat != "BACKUP_ARCHIVE":
            # Check if retention period has expired or if prohibited data leaked into retained record
            retention_expired = metadata.get("retention_expired", False)
            has_prohibited = metadata.get("has_prohibited_pii", False)

            if retention_expired or has_prohibited:
                self.diagnostics["violations_count"] += 1
                finding = Step(
                    step_no=0,
                    phase=Phase.FINDING,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.REPORT_EXPOSED_PII,
                    state=ResourceState.PRESENT,
                    evidence_id=ev_id,
                )
                remediation = Step(
                    step_no=0,
                    phase=Phase.REMEDIATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.REDACT_RECORD,
                    state=ResourceState.REDACTED,
                    evidence_id="",
                )
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.VERIFY_RECORD_REDACTED,
                    state=ResourceState.REDACTED,
                    evidence_id="",
                )
                return PolicyProof(
                    resource_id=res_id,
                    system_id=sys_id,
                    data_category=cat,
                    rule_id=rid,
                    condition_text=rule.condition_text,
                    condition_met=False,
                    required_action=PolicyAction.RETAIN,
                    actual_state=state,
                    is_compliant=False,
                    has_prohibited_pii=True,
                    is_retention_permitted=False,
                    failure_reason=f"Retained record {res_id} exposes prohibited PII or retention period has expired.",
                    evidence_proof_id=ev_id,
                    finding_step=finding,
                    remediation_step=remediation,
                    verification_step=verification,
                )
            else:
                self.diagnostics["compliant_count"] += 1
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.VERIFY_RECORD_PRESENT,
                    state=ResourceState.PRESENT,
                    evidence_id=ev_id,
                )
                return PolicyProof(
                    resource_id=res_id,
                    system_id=sys_id,
                    data_category=cat,
                    rule_id=rid,
                    condition_text=rule.condition_text,
                    condition_met=True,
                    required_action=PolicyAction.RETAIN,
                    actual_state=state,
                    is_compliant=True,
                    has_prohibited_pii=False,
                    is_retention_permitted=True,
                    failure_reason=None,
                    evidence_proof_id=ev_id,
                    finding_step=None,
                    remediation_step=None,
                    verification_step=verification,
                )

        # -------------------------------------------------------------
        # 5. BACKUP_ARCHIVE (Rule 14: RETAIN with RESTORE_BLOCKED condition)
        # -------------------------------------------------------------
        elif cat == "BACKUP_ARCHIVE" or rule.requires_restore_block:
            restore_blocked = (state in (ObservedState.BLOCKED, ObservedState.DISABLED, ObservedState.ABSENT)) or metadata.get("restore_blocked", False)
            if not restore_blocked:
                self.diagnostics["violations_count"] += 1
                finding = Step(
                    step_no=0,
                    phase=Phase.FINDING,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.REPORT_RESTORE_RISK,
                    state=ResourceState.ACTIVE,
                    evidence_id=ev_id,
                )
                remediation = Step(
                    step_no=0,
                    phase=Phase.REMEDIATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.BLOCK_RESTORE,
                    state=ResourceState.BLOCKED,
                    evidence_id="",
                )
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.VERIFY_RESTORE_BLOCKED,
                    state=ResourceState.BLOCKED,
                    evidence_id="",
                )
                return PolicyProof(
                    resource_id=res_id,
                    system_id=sys_id,
                    data_category=cat,
                    rule_id=rid,
                    condition_text=rule.condition_text,
                    condition_met=False,
                    required_action=PolicyAction.RETAIN,
                    actual_state=state,
                    is_compliant=False,
                    has_prohibited_pii=False,
                    is_retention_permitted=True,
                    recreation_risk="Restore access can be invoked to recreate deleted subject data",
                    failure_reason=f"Backup archive {res_id} has active restore capability at audit_at.",
                    evidence_proof_id=ev_id,
                    finding_step=finding,
                    remediation_step=remediation,
                    verification_step=verification,
                )
            else:
                self.diagnostics["compliant_count"] += 1
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=sys_id,
                    resource_id=res_id,
                    operation=Operation.VERIFY_RESTORE_BLOCKED,
                    state=ResourceState.BLOCKED,
                    evidence_id=ev_id,
                )
                return PolicyProof(
                    resource_id=res_id,
                    system_id=sys_id,
                    data_category=cat,
                    rule_id=rid,
                    condition_text=rule.condition_text,
                    condition_met=True,
                    required_action=PolicyAction.RETAIN,
                    actual_state=state,
                    is_compliant=True,
                    has_prohibited_pii=False,
                    is_retention_permitted=True,
                    recreation_risk=None,
                    failure_reason=None,
                    evidence_proof_id=ev_id,
                    finding_step=None,
                    remediation_step=None,
                    verification_step=verification,
                )

        # Default fallback
        verification = Step(
            step_no=0,
            phase=Phase.VERIFICATION,
            system_id=sys_id,
            resource_id=res_id,
            operation=Operation.VERIFY_RECORD_ABSENT,
            state=ResourceState.ABSENT,
            evidence_id=ev_id,
        )
        return PolicyProof(
            resource_id=res_id,
            system_id=sys_id,
            data_category=cat,
            rule_id=rid,
            condition_text=rule.condition_text,
            condition_met=True,
            required_action=rule.required_action,
            actual_state=state,
            is_compliant=True,
            has_prohibited_pii=False,
            is_retention_permitted=False,
            failure_reason=None,
            evidence_proof_id=ev_id,
            finding_step=None,
            remediation_step=None,
            verification_step=verification,
        )
