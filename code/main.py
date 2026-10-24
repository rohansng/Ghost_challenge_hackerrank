"""
Ghost Data Still Exists — Primary Autonomous Deletion Audit Agent
HackerRank Orchestrate October 2026 Challenge Entry Point.
"""

import os
import sys
import csv
import json
import time
from datetime import datetime
from typing import List, Dict, Any, Tuple

from code.loaders import DataLoader
from code.intent_classifier import IntentClassifier
from code.identity_engine import IdentityEngine
from code.evidence_normalizer import EvidenceNormalizer
from code.temporal_state_machine import TemporalStateMachine
from code.policy_engine import PolicyEngine
from code.remediation_planner import RemediationPlanner
from code.models import DeletionStatus, Step


class DeletionAuditEngine:
    def __init__(self, dataset_dir: str = "dataset"):
        self.dataset_dir = dataset_dir
        self.loader = DataLoader(dataset_dir)
        self.intent_classifier = IntentClassifier()
        self.normalizer = EvidenceNormalizer(dataset_dir)
        self.tsm = TemporalStateMachine()
        self.policy_engine = PolicyEngine()
        self.planner = RemediationPlanner()
        self.identity_engine = None

    def initialize(self):
        print("[1/4] Loading identities, audit logs, and policy rules...")
        identities = self.loader.load_user_identities("user_identities.csv")
        audit_logs = self.loader.load_user_audit_log("user_audit_log.csv")
        
        print("[2/4] Initializing Multi-Hop Temporal Identity Graph...")
        self.identity_engine = IdentityEngine(identities, audit_logs)

        print("[3/4] Extracting multi-modal evidence across 94 files and activity streams...")
        total_obs = self.normalizer.load_and_extract_all()
        print(f"      Extracted {total_obs:,} observations.")

    def process_request(self, req) -> Tuple[DeletionStatus, List[Step]]:
        # 1. Determine request authorization
        is_deletion, req_type, rationale = self.intent_classifier.classify(req.request_text)
        if not is_deletion:
            return DeletionStatus.NOT_APPLICABLE, []

        # 2. Resolve identity
        res = self.identity_engine.resolve_identity(req.email)
        user_id = res.canonical_user_id if res else None

        identifiers = {req.email.lower()}
        if res and res.identity_node:
            identifiers.update(e.lower() for e in res.identity_node.all_emails)

        # 3. Retrieve matching candidate observations
        candidate_obs = self.normalizer.get_observations_for_subject(
            user_id=user_id,
            emails=identifiers,
        )

        # 4. Temporal state reconstruction at audit_at
        snapshots = self.tsm.evaluate_resource_states_at_audit(candidate_obs, req.audit_at)

        # 5. Evaluate policy on all reconstructed resources
        evaluated_resources = []
        for res_id, snap in snapshots.items():
            eval_res = self.policy_engine.evaluate_resource_policy(snap)
            evaluated_resources.append(eval_res)

        # 6. Build ordered plan
        status, steps = self.planner.build_plan(
            case_id=req.case_id,
            is_deletion_authorized=is_deletion,
            evaluated_resources=evaluated_resources,
        )

        return status, steps

    def run_evaluation(self, output_csv_path: str = "output.csv") -> Dict[str, Any]:
        self.initialize()
        print(f"[4/4] Processing all evaluation deletion requests...")
        eval_requests = self.loader.load_deletion_requests("deletion_requests.csv")

        results = []
        status_counts = defaultdict_int()

        start_time = time.time()
        for req in eval_requests:
            status, steps = self.process_request(req)
            status_counts[status.value] += 1
            steps_json = json.dumps([s.to_dict() for s in steps], separators=(",", ":"))
            results.append({
                "case_id": req.case_id,
                "deletion_status": status.value,
                "steps_json": steps_json,
            })

        duration = time.time() - start_time

        # Sort results by case_id
        # Natural sorting: sort by integer value of case_id if format is case_XXX
        def case_sort_key(r):
            cid = r["case_id"]
            if cid.startswith("case_"):
                try:
                    return int(cid.split("_")[1])
                except ValueError:
                    return cid
            return cid

        results.sort(key=case_sort_key)

        # Write output.csv at repo root
        print(f"Writing final output to {output_csv_path}...")
        with open(output_csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["case_id", "deletion_status", "steps_json"])
            writer.writeheader()
            for r in results:
                writer.writerow(r)

        stats = {
            "total_cases": len(results),
            "status_counts": dict(status_counts),
            "duration_seconds": duration,
            "output_path": output_csv_path,
        }
        return stats


def defaultdict_int():
    from collections import defaultdict
    return defaultdict(int)


def main():
    engine = DeletionAuditEngine("dataset")
    stats = engine.run_evaluation("output.csv")
    print(f"\nAudit completed successfully in {stats['duration_seconds']:.2f} seconds!")
    print(f"Total Cases: {stats['total_cases']}")
    print(f"Status Counts: {stats['status_counts']}")
    print(f"Output File: {stats['output_path']}")


if __name__ == "__main__":
    main()
