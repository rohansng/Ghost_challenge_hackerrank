"""
main.py — Ghost Data Still Exists: Primary Autonomous Deletion Audit Agent
HackerRank Orchestrate October 2026 Challenge Entry Point.

This engine deterministically reconstructs identities, normalizes multi-modal
evidence across structured databases and unstructured records, tracks active
synchronization/restore recreation risks, applies statutory deletion rules,
evaluates an 11-point explainable proof checklist, and emits ordered
canonical remediation and verification steps strictly compliant with the schema.
"""

import argparse
import csv
import json
import logging
import os
import sys
import time
from collections import defaultdict
from typing import List, Dict, Any, Tuple, Optional, Union

# Ensure repository root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from code.config import EngineConfig
from code.exceptions import GhostDataError, OutputValidationError
from code.models import DeletionStatus, Step, DeletionRequestRecord
from code.loaders import DataLoader
from code.intent_classifier import IntentClassifier
from code.identity_engine import IdentityEngine, IdentityResolutionResult
from code.evidence_normalizer import EvidenceNormalizer
from code.temporal_state_machine import TemporalStateMachine
from code.policy_engine import PolicyEngine
from code.decision_engine import DecisionEngine, CaseProof
from code.remediation_planner import RemediationPlanner
from code.output_validator import OutputValidator

logger = logging.getLogger("ghost_data.engine")


class DeletionAuditEngine:
    """Primary autonomous deletion audit engine orchestrating all sub-systems."""

    def __init__(self, config: Optional[EngineConfig] = None, dataset_dir: str = "dataset"):
        if config is not None:
            self.config = config
        else:
            self.config = EngineConfig(dataset_dir=dataset_dir)

        self.loader = DataLoader(self.config.dataset_dir)
        self.intent_classifier = IntentClassifier()
        self.normalizer = EvidenceNormalizer(self.config.dataset_dir)
        self.tsm = TemporalStateMachine()
        self.policy_engine = PolicyEngine(rules_file_path=self.config.get_dataset_path(self.config.deletion_rules_file))
        self.planner = RemediationPlanner()
        self.decision_engine = DecisionEngine()
        self.identity_engine: Optional[IdentityEngine] = None
        self._is_initialized = False

    def initialize(self, verbose: bool = True) -> None:
        """Load identities, audit logs, policy rules, and multi-modal evidence indexes."""
        if self._is_initialized:
            return

        if verbose:
            logger.info("[1/4] Ingesting canonical identities and historical audit logs...")
        identities = self.loader.load_user_identities(self.config.user_identities_file)
        audit_logs = self.loader.load_user_audit_log(self.config.user_audit_log_file)

        if verbose:
            logger.info("[2/4] Constructing Multi-Hop Temporal Identity Graph...")
        self.identity_engine = IdentityEngine(identities, audit_logs)

        if verbose:
            logger.info("[3/4] Extracting and indexing multi-modal evidence across manifests...")
        total_obs = self.normalizer.load_and_extract_all()
        if verbose:
            logger.info(f"      Indexed {total_obs:,} grounded evidence observations.")

        self._is_initialized = True

    def process_request(
        self,
        req: DeletionRequestRecord,
        return_proof: bool = False,
    ) -> Union[Tuple[DeletionStatus, List[Step]], Tuple[DeletionStatus, List[Step], CaseProof]]:
        """Process a single deletion request deterministically through the pipeline."""
        if not self._is_initialized:
            self.initialize(verbose=False)

        assert self.identity_engine is not None, "IdentityEngine must be initialized"

        # 1. Determine request authorization
        is_deletion, req_type, rationale = self.intent_classifier.classify(req.request_text)

        # 2. Resolve current and historical identity
        res: Optional[IdentityResolutionResult] = self.identity_engine.resolve_identity(req.email)
        user_id = res.canonical_user_id if res else None

        identifiers = {req.email.lower()}
        phones = set()
        hashes = set()
        if res and res.identity_node:
            identifiers.update(e.lower() for e in res.identity_node.all_emails)
            phones.update(p for p in res.identity_node.all_phones if p)
            hashes.update(h.lower() for h in res.identity_node.all_hashes if h)

        # 3. Retrieve grounded candidate observations
        candidate_obs = self.normalizer.get_observations_for_subject(
            user_id=user_id,
            emails=identifiers,
            phones=phones,
            hashes=hashes,
        ) if is_deletion else []

        # 4. Reconstruct temporal state at audit_at cutoff
        snapshots = self.tsm.evaluate_resource_states_at_audit(candidate_obs, req.audit_at) if is_deletion else {}

        # 5. Evaluate statutory deletion rules against all reconstructed resources
        evaluated_resources = []
        for res_id, snap in snapshots.items():
            eval_res = self.policy_engine.evaluate_resource_policy(snap)
            evaluated_resources.append(eval_res)

        # 6. Build canonical ordered remediation and verification plan
        status, steps = self.planner.build_plan(
            case_id=req.case_id,
            is_deletion_authorized=is_deletion,
            evaluated_resources=evaluated_resources,
        )

        # 7. Evaluate 11-point explainable statutory CaseProof
        proof = self.decision_engine.evaluate_case(
            request=req,
            is_deletion_authorized=is_deletion,
            identity_res=res,
            all_observations=candidate_obs,
            snapshots=snapshots,
            evaluated_resources=evaluated_resources,
            steps=steps,
        )

        if return_proof:
            return proof.final_decision, proof.steps, proof
        return proof.final_decision, proof.steps

    def run_evaluation(
        self,
        output_csv_path: Optional[str] = None,
        validate: bool = False,
        verbose: bool = True,
    ) -> Dict[str, Any]:
        """Execute full evaluation across all cases in deletion_requests.csv."""
        target_output = output_csv_path or self.config.output_path
        self.initialize(verbose=verbose)

        if verbose:
            logger.info("[4/4] Auditing all evaluation deletion requests...")
        eval_requests = self.loader.load_deletion_requests(self.config.deletion_requests_file)

        results = []
        status_counts: Dict[str, int] = defaultdict(int)

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

        # Sort results deterministically by case_id using natural numerical sorting
        def case_sort_key(r: Dict[str, Any]) -> Any:
            cid = r["case_id"]
            if cid.startswith("case_"):
                try:
                    return int(cid.split("_")[1])
                except ValueError:
                    return cid
            return cid

        results.sort(key=case_sort_key)

        # Write output.csv at specified path
        if verbose:
            logger.info(f"Writing final canonical predictions to {target_output}...")
        with open(target_output, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["case_id", "deletion_status", "steps_json"])
            writer.writeheader()
            for r in results:
                writer.writerow(r)

        stats = {
            "total_cases": len(results),
            "status_counts": dict(status_counts),
            "duration_seconds": duration,
            "output_path": target_output,
        }

        # Optional strict output validation
        if validate:
            if verbose:
                logger.info("Running strict OutputValidator on generated output...")
            validator = OutputValidator(self.config.dataset_dir)
            validation_passed, val_errors, _ = validator.validate_file(target_output, expected_count=518)
            stats["validation_passed"] = validation_passed
            if not validation_passed:
                raise OutputValidationError(f"Generated output {target_output} failed strict validation: {len(val_errors)} errors")

        return stats


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Ghost Data Still Exists: Autonomous Deletion Audit Agent",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--dataset-dir",
        default="dataset",
        help="Path to directory containing dataset files",
    )
    parser.add_argument(
        "--output",
        default="output.csv",
        help="Path where output.csv should be written",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run strict OutputValidator after generation",
    )
    parser.add_argument(
        "--case-id",
        help="Inspect a single case_id in detail and print its explainable CaseProof",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress informational output",
    )
    return parser.parse_args()


def configure_logging(verbose: bool = False, quiet: bool = False) -> None:
    """Configure structured logging level and formatting."""
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> int:
    """CLI entry point for running evaluation or inspecting cases."""
    args = parse_args()
    configure_logging(verbose=args.verbose, quiet=args.quiet)

    config = EngineConfig(
        dataset_dir=args.dataset_dir,
        output_path=args.output,
        log_level="DEBUG" if args.verbose else "INFO",
    )

    engine = DeletionAuditEngine(config=config)

    # Single-case diagnostic mode
    if args.case_id:
        engine.initialize(verbose=not args.quiet)
        requests = engine.loader.load_deletion_requests(config.deletion_requests_file)
        matching = [r for r in requests if r.case_id == args.case_id]
        if not matching:
            logger.error(f"Case '{args.case_id}' not found in {config.deletion_requests_file}")
            return 1

        req = matching[0]
        status, steps, proof = engine.process_request(req, return_proof=True)
        print(f"\n{'='*60}")
        print(f"CASE AUDIT DIAGNOSTIC: {req.case_id} ({req.email})")
        print(f"{'='*60}")
        print(f"Requested At:    {req.requested_at}")
        print(f"Audit Cutoff:    {req.audit_at}")
        print(f"Reported Claim:  {req.reported_status}")
        print(f"Final Decision:  {status.value}")
        print(f"Checklist Proof: {proof.checklist}")
        print(f"Decision Reasons: {[r.value for r in proof.decision_reasons]}")
        print(f"Total Steps:     {len(steps)}")
        print(f"Steps JSON:\n{json.dumps([s.to_dict() for s in steps], indent=2)}")
        print(f"{'='*60}\n")
        return 0

    # Full dataset evaluation mode
    try:
        stats = engine.run_evaluation(
            output_csv_path=args.output,
            validate=args.validate,
            verbose=not args.quiet,
        )
    except GhostDataError as ex:
        logger.error(f"Audit failed: {ex}")
        return 1

    if not args.quiet:
        print(f"\nAudit completed successfully in {stats['duration_seconds']:.2f} seconds!")
        print(f"Total Cases:   {stats['total_cases']}")
        print(f"Status Counts: {stats['status_counts']}")
        print(f"Output File:   {stats['output_path']}")
        if "validation_passed" in stats:
            print(f"Validation:    {'PASSED [OK]' if stats['validation_passed'] else 'FAILED'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
