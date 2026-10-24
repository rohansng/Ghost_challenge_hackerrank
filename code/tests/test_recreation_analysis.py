"""
Unit Tests for Phase 4 Recreation Analysis
Covers all 10 adversarial test scenarios, graph traversal, cycle detection,
active vs historical event distinction, and recreation proofs.
"""

import unittest
from datetime import datetime, timezone

from code.models import Operation, ResourceState, Phase, Step
from code.evidence_models import ObservedState
from code.recreation_models import (
    FlowType,
    ActivityStatus,
    GraphNode,
    GraphEdge,
    DataFlowGraph,
    RecreationProof,
)
from code.recreation_analyzer import RecreationAnalyzer


class TestRecreationAnalysis(unittest.TestCase):
    def setUp(self):
        self.analyzer = RecreationAnalyzer(dataset_dir="dataset")
        self.dt = datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc)

    # -------------------------------------------------------------
    # 1. Active Sync
    # -------------------------------------------------------------
    def test_01_active_sync(self):
        """Active sync connector generates REPORT_ACTIVE_DATA_FLOW, DISABLE_DATA_FLOW, VERIFY_DATA_FLOW_DISABLED."""
        proofs, graph = self.analyzer.analyze_subject_recreation(
            user_id="user_synth_01",
            emails=["user01@example.com"],
            candidate_resources=["data_flow_3518"],
            audit_at=self.dt,
        )
        flow_proofs = [p for p in proofs if p.affected_resource == "data_flow_3518"]
        self.assertEqual(len(flow_proofs), 1)
        p = flow_proofs[0]
        self.assertEqual(p.current_activity_status, ActivityStatus.ACTIVE)
        self.assertTrue(p.can_recreate_prohibited_data)
        self.assertEqual(p.operation, Operation.REPORT_ACTIVE_DATA_FLOW)
        self.assertEqual(p.remediation_needed, Operation.DISABLE_DATA_FLOW)
        self.assertEqual(p.verification_needed, Operation.VERIFY_DATA_FLOW_DISABLED)
        self.assertEqual(p.finding_step.operation, Operation.REPORT_ACTIVE_DATA_FLOW)
        self.assertEqual(p.remediation_step.operation, Operation.DISABLE_DATA_FLOW)

    # -------------------------------------------------------------
    # 2. Inactive Sync
    # -------------------------------------------------------------
    def test_02_inactive_sync(self):
        """Inactive/disabled sync connector produces compliant VERIFY_DATA_FLOW_DISABLED."""
        proofs, graph = self.analyzer.analyze_subject_recreation(
            user_id="user_synth_02",
            emails=["user02@example.com"],
            candidate_resources=["data_flow_6987"],  # disabled via DISABLE_DATA_FLOW in dataset
            audit_at=self.dt,
        )
        flow_proofs = [p for p in proofs if p.affected_resource == "data_flow_6987"]
        self.assertEqual(len(flow_proofs), 1)
        p = flow_proofs[0]
        self.assertEqual(p.current_activity_status, ActivityStatus.DISABLED)
        self.assertFalse(p.can_recreate_prohibited_data)
        self.assertIsNone(p.finding_step)
        self.assertIsNone(p.remediation_step)
        self.assertEqual(p.verification_step.operation, Operation.VERIFY_DATA_FLOW_DISABLED)

    # -------------------------------------------------------------
    # 3. Unrelated Sync
    # -------------------------------------------------------------
    def test_03_unrelated_sync(self):
        """Sync events belonging to unrelated subjects produce zero false positives."""
        proofs, graph = self.analyzer.analyze_subject_recreation(
            user_id="user_unrelated_999",
            emails=["completely_unrelated_person@nowhere.org"],
            candidate_resources=["account_99999"],
            audit_at=self.dt,
        )
        self.assertEqual(len(proofs), 0)

    # -------------------------------------------------------------
    # 4. Deleted Source but Surviving Backup
    # -------------------------------------------------------------
    def test_04_deleted_source_but_surviving_backup(self):
        """Primary profile deleted, but backup archive retains unblocked restore capability."""
        proofs, graph = self.analyzer.analyze_subject_recreation(
            user_id="user_synth_04",
            emails=["user04@example.com"],
            candidate_resources=["backup_8264"],  # CHECK_RESTORE_ACCESS confirmed can be restored
            audit_at=self.dt,
        )
        bak_proofs = [p for p in proofs if p.affected_resource == "backup_8264"]
        self.assertEqual(len(bak_proofs), 1)
        p = bak_proofs[0]
        self.assertEqual(p.current_activity_status, ActivityStatus.ACTIVE)
        self.assertTrue(p.can_recreate_prohibited_data)
        self.assertEqual(p.operation, Operation.REPORT_RESTORE_RISK)
        self.assertEqual(p.remediation_needed, Operation.BLOCK_RESTORE)
        self.assertEqual(p.finding_step.operation, Operation.REPORT_RESTORE_RISK)
        self.assertEqual(p.remediation_step.operation, Operation.BLOCK_RESTORE)
        self.assertEqual(p.verification_step.operation, Operation.VERIFY_RESTORE_BLOCKED)

    # -------------------------------------------------------------
    # 5. Restore After Deletion
    # -------------------------------------------------------------
    def test_05_restore_after_deletion(self):
        """Restore operation repopulating downstream resource triggers recreation finding."""
        # activity_3387: backup_9287 repopulated downstream resource search_4882
        proofs, graph = self.analyzer.analyze_subject_recreation(
            user_id="user_16",
            emails=["areed1433@gmail.com"],
            candidate_resources=["backup_9287", "search_4882"],
            audit_at=datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc),
        )
        bak_proofs = [p for p in proofs if p.affected_resource == "backup_9287"]
        self.assertGreaterEqual(len(bak_proofs), 1)
        p = bak_proofs[0]
        self.assertEqual(p.current_activity_status, ActivityStatus.ACTIVE)
        self.assertEqual(p.operation, Operation.REPORT_RESTORE_RISK)

    # -------------------------------------------------------------
    # 6. Stale Export (Static Resource vs. Pipeline)
    # -------------------------------------------------------------
    def test_06_stale_export(self):
        """Stale export archive in object store without active pipeline is not labeled active sync."""
        proofs, graph = self.analyzer.analyze_subject_recreation(
            user_id="user_synth_06",
            emails=["user06@example.com"],
            candidate_resources=["export_388"],
            audit_at=self.dt,
        )
        # Exports are static resources evaluated by policy engine, not active flow channels
        self.assertEqual(len(proofs), 0)

    # -------------------------------------------------------------
    # 7. Recurring Job
    # -------------------------------------------------------------
    def test_07_recurring_job(self):
        """Active recurring connector schedule identified as ongoing recreation risk."""
        proofs, graph = self.analyzer.analyze_subject_recreation(
            user_id="user_synth_07",
            emails=["user07@example.com"],
            candidate_resources=["data_flow_006"],
            audit_at=self.dt,
        )
        self.assertEqual(len(proofs), 1)
        self.assertEqual(proofs[0].operation, Operation.REPORT_ACTIVE_DATA_FLOW)

    # -------------------------------------------------------------
    # 8. One-Time Historical Job
    # -------------------------------------------------------------
    def test_08_one_time_historical_job(self):
        """Historical batch job completed in the past without active connector produces no active risk."""
        proofs, graph = self.analyzer.analyze_subject_recreation(
            user_id="user_synth_08",
            emails=["user08@example.com"],
            candidate_resources=["cache_9558"],  # historical cache refresh
            audit_at=self.dt,
        )
        self.assertEqual(len(proofs), 0)

    # -------------------------------------------------------------
    # 9. Contradictory Activity Status
    # -------------------------------------------------------------
    def test_09_contradictory_activity_status(self):
        """Workflow claims deletion complete, but connector check proves data flow remains enabled."""
        # data_flow_3518 was checked and found enabled; claim of deletion cannot override it
        proofs, graph = self.analyzer.analyze_subject_recreation(
            user_id="user_synth_09",
            emails=["user09@example.com"],
            candidate_resources=["data_flow_3518"],
            audit_at=self.dt,
        )
        self.assertEqual(len(proofs), 1)
        self.assertEqual(proofs[0].current_activity_status, ActivityStatus.ACTIVE)
        self.assertTrue(proofs[0].can_recreate_prohibited_data)

    # -------------------------------------------------------------
    # 10. Cycle in Flow Graph
    # -------------------------------------------------------------
    def test_10_cycle_in_flow_graph(self):
        """DataFlowGraph detects directed synchronization cycles using DFS."""
        g = DataFlowGraph()
        g.add_node(GraphNode("node_A", "SYSTEM", "account_service"))
        g.add_node(GraphNode("node_B", "SYSTEM", "profile_service"))
        g.add_node(GraphNode("node_C", "SYSTEM", "analytics_platform"))

        # Create cycle A -> B -> A
        g.add_edge(GraphEdge("e1", "node_A", "node_B", FlowType.SYNC, "flow_ab", ActivityStatus.ACTIVE, is_active=True))
        g.add_edge(GraphEdge("e2", "node_B", "node_A", FlowType.SYNC, "flow_ba", ActivityStatus.ACTIVE, is_active=True))
        # Non-cyclic branch B -> C
        g.add_edge(GraphEdge("e3", "node_B", "node_C", FlowType.SYNC, "flow_bc", ActivityStatus.ACTIVE, is_active=True))

        cycles = g.detect_cycles()
        self.assertGreaterEqual(len(cycles), 1)
        # Verify cycle contains node_A and node_B
        flat_cycle = [item for sublist in cycles for item in sublist]
        self.assertIn("node_A", flat_cycle)
        self.assertIn("node_B", flat_cycle)


if __name__ == "__main__":
    unittest.main()
