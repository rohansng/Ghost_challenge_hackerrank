"""
audit_reviewer_a.py — Deep Adversarial Output Evaluator (Reviewer A)
Audits output.csv against all hidden traps, false COMPLETEs, and false INCOMPLETEs.
"""

import os
import sys
import json
import csv
from datetime import datetime

# Ensure root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from code.config import EngineConfig
from code.loaders import DataLoader, parse_iso_datetime
from code.intent_classifier import IntentClassifier
from code.output_validator import OutputValidator


def run_reviewer_a_audit(output_csv="output.csv", dataset_dir="dataset"):
    print("=" * 70)
    print("REVIEWER A — ADVERSARIAL OUTPUT AUDIT")
    print("=" * 70)

    # 1. Run strict schema & safety validator
    validator = OutputValidator(dataset_dir)
    is_valid, errors, stats = validator.validate_file(output_csv, expected_count=518)
    print(f"Schema & Safety Validator: {'PASSED [OK]' if is_valid else 'FAILED [X]'}")
    print(f"Total Evaluated Rows:      {stats['total_rows']}")
    print(f"Status Distribution:       {stats['status_counts']}")
    print(f"Phase Distribution:        {stats['phase_counts']}")
    print(f"Total Structural Errors:   {len(errors)}")

    if not is_valid:
        print("\nErrors Found:")
        for err in errors[:10]:
            print(f"  {err}")
        return False

    # 2. Load dataset and output for adversarial probing
    loader = DataLoader(dataset_dir)
    requests = {r.case_id: r for r in loader.load_deletion_requests("deletion_requests.csv")}
    manifest = loader.load_evidence_files("evidence_files.csv")
    activities = {a.activity_id: a for a in loader.load_system_activity("system_activity.csv")}
    audits = {a.audit_id: a for a in loader.load_user_audit_log("user_audit_log.csv")}

    output_rows = []
    with open(output_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            output_rows.append(r)

    # 3. Adversarial Search for False COMPLETE
    print("\n[Adversarial Probe 1] Auditing all 164 COMPLETE cases for False Complete traps...")
    false_complete_findings = []
    intent_classifier = IntentClassifier()

    for r in output_rows:
        cid = r["case_id"]
        status = r["deletion_status"]
        steps = json.loads(r["steps_json"])
        req = requests.get(cid)

        if not req:
            false_complete_findings.append(f"{cid}: Missing in deletion_requests.csv")
            continue

        if status == "COMPLETE":
            # Trap A: Non-deletion request marked COMPLETE
            is_del, _, _ = intent_classifier.classify(req.request_text)
            if not is_del:
                false_complete_findings.append(f"{cid}: Marked COMPLETE but request does not authorize deletion: '{req.request_text}'")

            # Trap B: COMPLETE with 0 steps
            if len(steps) == 0:
                false_complete_findings.append(f"{cid}: Marked COMPLETE but has 0 verification steps")

            # Trap C: COMPLETE containing FINDING or REMEDIATION phases
            for s in steps:
                if s["phase"] != "VERIFICATION":
                    false_complete_findings.append(f"{cid}: Marked COMPLETE but contains non-verification step {s['step_no']} (phase={s['phase']})")

                # Trap D: COMPLETE with empty evidence_id
                if not s["evidence_id"]:
                    false_complete_findings.append(f"{cid}: Marked COMPLETE but verification step {s['step_no']} has empty evidence_id")

                # Trap E: Verification step cites evidence captured strictly AFTER audit_at
                ev_id = s["evidence_id"]
                ev_time = None
                if ev_id in manifest:
                    ev_time = manifest[ev_id].captured_at
                elif ev_id in activities:
                    ev_time = activities[ev_id].event_time
                elif ev_id in audits:
                    ev_time = audits[ev_id].event_time

                if ev_time and ev_time > req.audit_at:
                    false_complete_findings.append(
                        f"{cid}: Verification step {s['step_no']} cites evidence {ev_id} captured at {ev_time} strictly after audit_at {req.audit_at}"
                    )

    print(f"  False COMPLETE Violations Found: {len(false_complete_findings)}")
    for f in false_complete_findings[:10]:
        print(f"    * {f}")

    # 4. Adversarial Search for False INCOMPLETE
    print("\n[Adversarial Probe 2] Auditing all 344 INCOMPLETE cases for False Incomplete traps...")
    false_incomplete_findings = []

    for r in output_rows:
        cid = r["case_id"]
        status = r["deletion_status"]
        steps = json.loads(r["steps_json"])
        req = requests.get(cid)

        if status == "INCOMPLETE":
            # Trap A: Incomplete with 0 steps
            if len(steps) == 0:
                false_incomplete_findings.append(f"{cid}: Marked INCOMPLETE but steps_json is empty []")

            # Trap B: Incomplete with no FINDINGS
            phases = [s["phase"] for s in steps]
            if "FINDING" not in phases:
                false_incomplete_findings.append(f"{cid}: Marked INCOMPLETE but contains no FINDING steps to justify incomplete verdict")

            # Trap C: Incomplete with no REMEDIATION
            if "REMEDIATION" not in phases:
                false_incomplete_findings.append(f"{cid}: Marked INCOMPLETE but lacks REMEDIATION steps")

            # Trap D: Future remediation steps citing non-empty evidence IDs
            for s in steps:
                if s["phase"] == "REMEDIATION" and s["evidence_id"] != "":
                    false_incomplete_findings.append(f"{cid}: Remediation step {s['step_no']} has non-empty evidence_id '{s['evidence_id']}'")
                if s["phase"] == "VERIFICATION" and s["evidence_id"] != "":
                    false_incomplete_findings.append(f"{cid}: Post-remediation verification step {s['step_no']} has non-empty evidence_id '{s['evidence_id']}'")

    print(f"  False INCOMPLETE Violations Found: {len(false_incomplete_findings)}")
    for f in false_incomplete_findings[:10]:
        print(f"    * {f}")

    # 5. Adversarial Probe on NOT_APPLICABLE Cases
    print("\n[Adversarial Probe 3] Auditing all 10 NOT_APPLICABLE cases...")
    na_findings = []
    for r in output_rows:
        cid = r["case_id"]
        status = r["deletion_status"]
        steps = json.loads(r["steps_json"])
        req = requests.get(cid)

        if status == "NOT_APPLICABLE":
            if steps != []:
                na_findings.append(f"{cid}: NOT_APPLICABLE must have steps_json = [] but has {len(steps)} steps")
            is_del, req_type, rationale = intent_classifier.classify(req.request_text)
            if is_del:
                na_findings.append(f"{cid}: Classified NOT_APPLICABLE but text actually authorizes deletion: '{req.request_text}'")

    print(f"  NOT_APPLICABLE Violations Found: {len(na_findings)}")
    for f in na_findings[:10]:
        print(f"    * {f}")

    # 6. Overall Verdict
    total_violations = len(false_complete_findings) + len(false_incomplete_findings) + len(na_findings)
    print("\n" + "=" * 70)
    print(f"REVIEWER A AUDIT RESULT: {'PASSED — 0 ANOMALIES DETECTED' if total_violations == 0 else f'FAILED — {total_violations} VIOLATIONS'}")
    print("=" * 70)
    return total_violations == 0


if __name__ == "__main__":
    success = run_reviewer_a_audit()
    sys.exit(0 if success else 1)
