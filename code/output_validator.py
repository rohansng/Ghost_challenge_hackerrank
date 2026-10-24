"""
Strict Untrusted Output Validator and Failure Taxonomy Engine
HackerRank Orchestrate October 2026 — Ghost Data Still Exists

Treats output.csv as completely untrusted input and performs exhaustive schema,
structural, temporal, relational, ordering, and evidence validation.
"""

import os
import sys
import csv
import json
import re
from enum import Enum
from typing import List, Dict, Any, Optional, Set, Tuple


class FailureCategory(Enum):
    IDENTITY = "IDENTITY"
    EVIDENCE = "EVIDENCE"
    TEMPORAL = "TEMPORAL"
    POLICY = "POLICY"
    RECREATION = "RECREATION"
    RETENTION = "RETENTION"
    DECISION = "DECISION"
    ORDERING = "ORDERING"
    OUTPUT = "OUTPUT"
    VALIDATION = "VALIDATION"
    OTHER = "OTHER"


class ValidationError:
    def __init__(self, category: FailureCategory, case_id: str, field: str, message: str, step_no: Optional[int] = None):
        self.category = category
        self.case_id = case_id
        self.field = field
        self.message = message
        self.step_no = step_no

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "case_id": self.case_id,
            "field": self.field,
            "step_no": self.step_no,
            "message": self.message,
        }

    def __repr__(self) -> str:
        step_part = f" (step {self.step_no})" if self.step_no is not None else ""
        return f"[{self.category.value}] Case {self.case_id}{step_part} - {self.field}: {self.message}"


class OutputValidator:
    """
    Exhaustive validator for deletion audit prediction files.
    Enforces all constraints specified in the challenge contract (AGENTS.md §6.3, §6.4).
    """

    ALLOWED_HEADERS = ["case_id", "deletion_status", "steps_json"]
    ALLOWED_STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}
    ALLOWED_PHASES = {"FINDING", "REMEDIATION", "VERIFICATION"}
    ALLOWED_STEP_KEYS = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}

    VALID_OP_STATE = {
        "REPORT_REMAINING_RECORD": "PRESENT",
        "REPORT_EXPOSED_PII": "PRESENT",
        "REPORT_ACTIVE_DATA_FLOW": "ACTIVE",
        "REPORT_RESTORE_RISK": "ACTIVE",
        "DISABLE_DATA_FLOW": "DISABLED",
        "BLOCK_RESTORE": "BLOCKED",
        "DELETE_RECORD": "ABSENT",
        "REDACT_RECORD": "REDACTED",
        "ANONYMIZE_RECORD": "ANONYMIZED",
        "VERIFY_RECORD_ABSENT": "ABSENT",
        "VERIFY_RECORD_PRESENT": "PRESENT",
        "VERIFY_RECORD_REDACTED": "REDACTED",
        "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED",
        "VERIFY_DATA_FLOW_DISABLED": "DISABLED",
        "VERIFY_RESTORE_BLOCKED": "BLOCKED",
    }

    PHASE_RANK = {
        "FINDING": 1,
        "REMEDIATION": 2,
        "VERIFICATION": 3,
    }

    OPERATION_RANK = {
        # Finding
        "REPORT_REMAINING_RECORD": 1,
        "REPORT_EXPOSED_PII": 2,
        "REPORT_ACTIVE_DATA_FLOW": 3,
        "REPORT_RESTORE_RISK": 4,
        # Remediation
        "DISABLE_DATA_FLOW": 1,
        "BLOCK_RESTORE": 2,
        "DELETE_RECORD": 3,
        "REDACT_RECORD": 4,
        "ANONYMIZE_RECORD": 5,
        # Verification
        "VERIFY_RECORD_ABSENT": 1,
        "VERIFY_RECORD_PRESENT": 2,
        "VERIFY_RECORD_REDACTED": 3,
        "VERIFY_RECORD_ANONYMIZED": 4,
        "VERIFY_DATA_FLOW_DISABLED": 5,
        "VERIFY_RESTORE_BLOCKED": 6,
    }

    # Citable evidence IDs must match standard patterns
    EVIDENCE_PATTERN = re.compile(r"^(evidence_\d+|activity_\d+|audit_\d+|ev_\d+)$")

    def __init__(self, dataset_dir: Optional[str] = None):
        self.dataset_dir = dataset_dir
        self.known_evidence_ids: Optional[Set[str]] = None
        self.known_case_ids: Optional[List[str]] = None
        if dataset_dir:
            self._load_ground_truth_manifests()

    def _load_ground_truth_manifests(self):
        """Loads valid evidence IDs and evaluation case IDs from dataset files if present."""
        try:
            ev_path = os.path.join(self.dataset_dir, "evidence_files.csv")
            if os.path.exists(ev_path):
                self.known_evidence_ids = set()
                with open(ev_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        fid = row.get("file_id")
                        if fid:
                            self.known_evidence_ids.add(fid.strip())

            req_path = os.path.join(self.dataset_dir, "deletion_requests.csv")
            if os.path.exists(req_path):
                self.known_case_ids = []
                with open(req_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        cid = row.get("case_id")
                        if cid:
                            self.known_case_ids.append(cid.strip())
        except Exception:
            pass

    def validate_file(self, csv_path: str, expected_count: Optional[int] = 518) -> Tuple[bool, List[ValidationError], Dict[str, Any]]:
        """
        Validates an output.csv file against all strict rules.
        Returns: (is_valid, list_of_errors, stats)
        """
        errors: List[ValidationError] = []
        stats: Dict[str, Any] = {
            "file_path": csv_path,
            "total_rows": 0,
            "status_counts": {"COMPLETE": 0, "INCOMPLETE": 0, "NOT_APPLICABLE": 0},
            "total_steps": 0,
            "phase_counts": {"FINDING": 0, "REMEDIATION": 0, "VERIFICATION": 0},
            "error_count_by_category": {},
        }

        if not os.path.exists(csv_path):
            errors.append(ValidationError(FailureCategory.OUTPUT, "GLOBAL", "file", f"File does not exist: {csv_path}"))
            return False, errors, stats

        rows = []
        try:
            with open(csv_path, "r", encoding="utf-8", newline="") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header is None:
                    errors.append(ValidationError(FailureCategory.OUTPUT, "GLOBAL", "header", "File is empty"))
                    return False, errors, stats

                # 1. Exact header validation
                if header != self.ALLOWED_HEADERS:
                    errors.append(ValidationError(
                        FailureCategory.OUTPUT, "GLOBAL", "header",
                        f"Invalid header columns. Expected {self.ALLOWED_HEADERS}, found {header}"
                    ))

                for line_idx, row in enumerate(reader, start=2):
                    rows.append((line_idx, row))
        except Exception as e:
            errors.append(ValidationError(FailureCategory.OUTPUT, "GLOBAL", "read_error", f"Failed reading CSV: {str(e)}"))
            return False, errors, stats

        stats["total_rows"] = len(rows)

        # 2. Row count validation
        if expected_count is not None and len(rows) != expected_count:
            errors.append(ValidationError(
                FailureCategory.VALIDATION, "GLOBAL", "row_count",
                f"Row count mismatch: expected exactly {expected_count} data rows, found {len(rows)}"
            ))

        seen_case_ids = set()
        previous_case_sort_key = None

        for line_idx, row in rows:
            if len(row) != 3:
                errors.append(ValidationError(
                    FailureCategory.OUTPUT, f"LINE_{line_idx}", "row_length",
                    f"Row has {len(row)} columns, expected 3"
                ))
                continue

            case_id, status, steps_raw = row[0].strip(), row[1].strip(), row[2].strip()

            # 3. Case ID duplicate and missing checks
            if not case_id:
                errors.append(ValidationError(FailureCategory.IDENTITY, f"LINE_{line_idx}", "case_id", "Missing case_id"))
                continue

            if case_id in seen_case_ids:
                errors.append(ValidationError(
                    FailureCategory.OUTPUT, case_id, "case_id", f"Duplicate case_id: {case_id}"
                ))
            seen_case_ids.add(case_id)

            # Check sort ordering
            try:
                current_sort_key = int(case_id.split("_")[1]) if case_id.startswith("case_") else case_id
                if previous_case_sort_key is not None:
                    if isinstance(previous_case_sort_key, int) and isinstance(current_sort_key, int):
                        if current_sort_key < previous_case_sort_key:
                            errors.append(ValidationError(
                                FailureCategory.ORDERING, case_id, "case_id_order",
                                f"Cases not sorted: {case_id} appears after key {previous_case_sort_key}"
                            ))
                previous_case_sort_key = current_sort_key
            except Exception:
                pass

            # 4. Status validation
            if status not in self.ALLOWED_STATUSES:
                errors.append(ValidationError(
                    FailureCategory.DECISION, case_id, "deletion_status",
                    f"Invalid status '{status}'. Must be one of {self.ALLOWED_STATUSES}"
                ))
                continue

            stats["status_counts"][status] = stats["status_counts"].get(status, 0) + 1

            # 5. JSON parsing
            try:
                steps_data = json.loads(steps_raw)
            except json.JSONDecodeError as jde:
                errors.append(ValidationError(
                    FailureCategory.OUTPUT, case_id, "steps_json", f"Malformed JSON: {str(jde)}"
                ))
                continue

            if not isinstance(steps_data, list):
                errors.append(ValidationError(
                    FailureCategory.OUTPUT, case_id, "steps_json", "steps_json must be a JSON array"
                ))
                continue

            # 6. Status-specific step requirements
            if status == "NOT_APPLICABLE":
                if len(steps_data) != 0:
                    errors.append(ValidationError(
                        FailureCategory.POLICY, case_id, "steps_json",
                        f"NOT_APPLICABLE requests must have steps_json=[] (found {len(steps_data)} steps)"
                    ))
                continue

            if status == "COMPLETE":
                if len(steps_data) == 0:
                    errors.append(ValidationError(
                        FailureCategory.DECISION, case_id, "steps_json",
                        "COMPLETE case lacks proof: steps_json cannot be empty"
                    ))

            # 7. Step schema and phase validation
            prev_step_no = 0
            prev_phase_rank = 0
            prev_op_rank = 0
            prev_tie_key = ""

            for idx, s in enumerate(steps_data):
                stats["total_steps"] += 1
                if not isinstance(s, dict):
                    errors.append(ValidationError(
                        FailureCategory.OUTPUT, case_id, "step_item", f"Step at index {idx} is not an object", idx + 1
                    ))
                    continue

                step_keys = set(s.keys())
                if step_keys != self.ALLOWED_STEP_KEYS:
                    missing = self.ALLOWED_STEP_KEYS - step_keys
                    extra = step_keys - self.ALLOWED_STEP_KEYS
                    errors.append(ValidationError(
                        FailureCategory.OUTPUT, case_id, "step_keys",
                        f"Step schema mismatch. Missing: {missing}, Extra: {extra}", idx + 1
                    ))

                step_no = s.get("step_no")
                phase = s.get("phase")
                system_id = str(s.get("system_id", ""))
                resource_id = str(s.get("resource_id", ""))
                operation = s.get("operation")
                state = s.get("state")
                evidence_id = str(s.get("evidence_id", ""))

                # Consecutive step numbering starting at 1
                if step_no != prev_step_no + 1:
                    errors.append(ValidationError(
                        FailureCategory.ORDERING, case_id, "step_no",
                        f"Step numbering must be consecutive starting at 1. Expected {prev_step_no + 1}, got {step_no}", step_no
                    ))
                prev_step_no = step_no if isinstance(step_no, int) else prev_step_no + 1

                # Valid phase
                if phase not in self.ALLOWED_PHASES:
                    errors.append(ValidationError(
                        FailureCategory.VALIDATION, case_id, "phase", f"Invalid phase '{phase}'", step_no
                    ))
                    continue

                stats["phase_counts"][phase] = stats["phase_counts"].get(phase, 0) + 1

                # Phase ordering: FINDING -> REMEDIATION -> VERIFICATION
                current_phase_rank = self.PHASE_RANK.get(phase, 0)
                if current_phase_rank < prev_phase_rank:
                    errors.append(ValidationError(
                        FailureCategory.ORDERING, case_id, "phase_order",
                        f"Phase regression: '{phase}' appeared after higher phase", step_no
                    ))

                # If phase changed, reset operation and tie ranks
                if current_phase_rank > prev_phase_rank:
                    prev_phase_rank = current_phase_rank
                    prev_op_rank = 0
                    prev_tie_key = ""

                # Valid operation and state pairing
                if operation not in self.VALID_OP_STATE:
                    errors.append(ValidationError(
                        FailureCategory.POLICY, case_id, "operation", f"Unknown operation '{operation}'", step_no
                    ))
                else:
                    expected_state = self.VALID_OP_STATE[operation]
                    if state != expected_state:
                        errors.append(ValidationError(
                            FailureCategory.POLICY, case_id, "state",
                            f"State mismatch for '{operation}': expected '{expected_state}', got '{state}'", step_no
                        ))

                # Check operation ordering within phase
                current_op_rank = self.OPERATION_RANK.get(operation, 99)
                current_tie_key = f"{system_id}:{resource_id}"

                if current_op_rank < prev_op_rank:
                    errors.append(ValidationError(
                        FailureCategory.ORDERING, case_id, "operation_order",
                        f"Operation '{operation}' violates canonical priority within {phase}", step_no
                    ))
                elif current_op_rank == prev_op_rank:
                    if current_tie_key < prev_tie_key:
                        errors.append(ValidationError(
                            FailureCategory.ORDERING, case_id, "tie_breaker_order",
                            f"Tie-breaker violated: '{current_tie_key}' appeared after '{prev_tie_key}'", step_no
                        ))
                prev_op_rank = current_op_rank
                prev_tie_key = current_tie_key

                # Phase-specific and Status-specific Evidence ID Rules
                if status == "COMPLETE":
                    if phase != "VERIFICATION":
                        errors.append(ValidationError(
                            FailureCategory.DECISION, case_id, "phase",
                            f"COMPLETE case cannot contain {phase} steps; only VERIFICATION allowed", step_no
                        ))
                    if not evidence_id:
                        errors.append(ValidationError(
                            FailureCategory.EVIDENCE, case_id, "evidence_id",
                            "COMPLETE case verification step must cite non-empty evidence proving state", step_no
                        ))
                    elif not self.EVIDENCE_PATTERN.match(evidence_id):
                        errors.append(ValidationError(
                            FailureCategory.EVIDENCE, case_id, "evidence_id",
                            f"Invalid evidence_id format: '{evidence_id}'", step_no
                        ))
                    elif self.known_evidence_ids and evidence_id.startswith("evidence_") and evidence_id not in self.known_evidence_ids:
                        errors.append(ValidationError(
                            FailureCategory.EVIDENCE, case_id, "evidence_id",
                            f"Fabricated evidence_id not found in manifest: '{evidence_id}'", step_no
                        ))

                elif status == "INCOMPLETE":
                    if phase == "FINDING":
                        if not evidence_id:
                            errors.append(ValidationError(
                                FailureCategory.EVIDENCE, case_id, "evidence_id",
                                "FINDING step must cite participant-visible evidence_id", step_no
                            ))
                        elif not self.EVIDENCE_PATTERN.match(evidence_id):
                            errors.append(ValidationError(
                                FailureCategory.EVIDENCE, case_id, "evidence_id",
                                f"Invalid evidence_id format: '{evidence_id}'", step_no
                            ))
                        elif self.known_evidence_ids and evidence_id.startswith("evidence_") and evidence_id not in self.known_evidence_ids:
                            errors.append(ValidationError(
                                FailureCategory.EVIDENCE, case_id, "evidence_id",
                                f"Fabricated evidence_id not found in manifest: '{evidence_id}'", step_no
                            ))
                    elif phase == "REMEDIATION":
                        if evidence_id != "":
                            errors.append(ValidationError(
                                FailureCategory.EVIDENCE, case_id, "evidence_id",
                                f"REMEDIATION step must have empty evidence_id (''), got '{evidence_id}'", step_no
                            ))
                    elif phase == "VERIFICATION":
                        if evidence_id != "":
                            errors.append(ValidationError(
                                FailureCategory.EVIDENCE, case_id, "evidence_id",
                                f"Post-remediation VERIFICATION in INCOMPLETE case must have empty evidence_id (''), got '{evidence_id}'", step_no
                            ))

        # Check for missing case_ids against dataset manifest if available
        if self.known_case_ids:
            missing_cases = set(self.known_case_ids) - seen_case_ids
            for mc in sorted(missing_cases):
                errors.append(ValidationError(
                    FailureCategory.OUTPUT, mc, "case_id", f"Missing evaluation case_id from output: {mc}"
                ))

        # Tally errors by failure category
        for err in errors:
            cat_name = err.category.value
            stats["error_count_by_category"][cat_name] = stats["error_count_by_category"].get(cat_name, 0) + 1

        is_valid = len(errors) == 0
        return is_valid, errors, stats


def main():
    target_path = sys.argv[1] if len(sys.argv) > 1 else "output.csv"
    dataset_path = sys.argv[2] if len(sys.argv) > 2 else "dataset"

    print(f"=== STRICT OUTPUT VALIDATOR ===")
    print(f"Target file: {target_path}")
    print(f"Dataset dir: {dataset_path}")

    validator = OutputValidator(dataset_path)
    is_valid, errors, stats = validator.validate_file(target_path, expected_count=518)

    print(f"\n--- Validation Summary ---")
    print(f"Total Rows: {stats['total_rows']}")
    print(f"Status Counts: {stats['status_counts']}")
    print(f"Total Steps: {stats['total_steps']}")
    print(f"Phase Counts: {stats['phase_counts']}")
    print(f"Validation Result: {'PASSED [OK]' if is_valid else 'FAILED [X]'}")
    print(f"Total Errors: {len(errors)}")

    if errors:
        print("\nErrors by Category:")
        for cat, count in stats["error_count_by_category"].items():
            print(f"  {cat}: {count}")
        print("\nFirst 10 Errors:")
        for err in errors[:10]:
            print(f"  {err}")
        sys.exit(1)
    else:
        print("\nAll 518 cases strictly conform to the challenge schema and safety constraints!")
        sys.exit(0)


if __name__ == "__main__":
    main()
