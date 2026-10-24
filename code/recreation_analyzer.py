"""
Phase 4 Recreation Analyzer
Deterministic analysis of active synchronization mechanisms and backup restore pathways.
Builds directed data flow graphs, evaluates temporal recreation risks at audit_at,
distinguishes active threats from historical completed jobs, and generates explainable proofs.
"""

import os
import csv
import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set, Tuple
from collections import defaultdict

from code.evidence_models import ObservedState
from code.models import Operation, ResourceState, Phase, Step
from code.recreation_models import (
    FlowType,
    ActivityStatus,
    FlowChannel,
    GraphNode,
    GraphEdge,
    RecreationPath,
    RecreationProof,
    DataFlowGraph,
)
from code.loaders import parse_iso_datetime, normalize_email


class RecreationAnalyzer:
    """
    Deterministic analyzer of process-level recreation risks across global activity streams.
    """

    def __init__(self, dataset_dir: str = "dataset"):
        self.dataset_dir = dataset_dir
        self.activity_path = os.path.join(dataset_dir, "system_activity.csv")
        self.activity_records: List[Dict[str, Any]] = []
        
        # Indexes for fast lookup
        self.events_by_resource: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.events_by_user: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.events_by_email: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.channel_to_resources: Dict[str, Set[str]] = defaultdict(set)
        self.resource_to_channels: Dict[str, Set[str]] = defaultdict(set)

        self.diagnostics: Dict[str, Any] = {
            "total_events_loaded": 0,
            "active_flows_detected": 0,
            "restore_risks_detected": 0,
            "historical_events_filtered": 0,
            "cycles_detected": 0,
        }

        self._load_and_index_activity()

    def _load_and_index_activity(self) -> None:
        if not os.path.exists(self.activity_path):
            return

        with open(self.activity_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = parse_iso_datetime(row["event_time"])
                row["_event_time"] = ts
                self.activity_records.append(row)
                res_id = row["resource_id"].strip()
                details = row["details"]

                if res_id:
                    self.events_by_resource[res_id].append(row)

                # Check for explicit identity linkage in details
                uid_m = re.search(r'\b(user_\d+)\b', details)
                if uid_m:
                    uid = uid_m.group(1)
                    row["_user_id"] = uid
                    self.events_by_user[uid].append(row)

                email_m = re.search(r'\b([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\b', details)
                if email_m:
                    em = normalize_email(email_m.group(1))
                    row["_email"] = em
                    self.events_by_email[em].append(row)

                # Track downstream resource linkages
                downstream_m = re.search(r'downstream resource (\w+)', details)
                if downstream_m:
                    ds_res = downstream_m.group(1)
                    row["_downstream_resource"] = ds_res
                    self.events_by_resource[ds_res].append(row)
                    self.channel_to_resources[res_id].add(ds_res)
                    self.resource_to_channels[ds_res].add(res_id)

        self.diagnostics["total_events_loaded"] = len(self.activity_records)

    def analyze_subject_recreation(
        self,
        user_id: Optional[str],
        emails: List[str],
        candidate_resources: List[str],
        audit_at: datetime,
    ) -> Tuple[List[RecreationProof], DataFlowGraph]:
        """
        Performs end-to-end recreation analysis for a subject strictly bounded by audit_at.
        Returns:
          - List of RecreationProof objects
          - The constructed DataFlowGraph
        """
        # 1. Discover all relevant channels (connectors, backup archives, pipelines)
        relevant_channels: Dict[str, Dict[str, Any]] = {}

        # a) Channels linked via identity in activity
        if user_id and user_id in self.events_by_user:
            for ev in self.events_by_user[user_id]:
                if ev["_event_time"] <= audit_at:
                    self._register_channel(ev, relevant_channels)

        for em in emails:
            norm_em = normalize_email(em)
            if norm_em in self.events_by_email:
                for ev in self.events_by_email[norm_em]:
                    if ev["_event_time"] <= audit_at:
                        self._register_channel(ev, relevant_channels)

        # b) Channels linked via candidate resources
        for r_id in candidate_resources:
            # Direct channel
            if r_id.startswith(("data_flow_", "backup_")):
                relevant_channels[r_id] = {"channel_id": r_id}
            # Indirect channel via downstream linkage
            if r_id in self.resource_to_channels:
                for ch in self.resource_to_channels[r_id]:
                    relevant_channels[ch] = {"channel_id": ch, "linked_resource": r_id}

            if r_id in self.events_by_resource:
                for ev in self.events_by_resource[r_id]:
                    if ev["_event_time"] <= audit_at:
                        self._register_channel(ev, relevant_channels)

        # 2. Reconstruct temporal status of each relevant channel at audit_at
        proofs: List[RecreationProof] = []
        graph = DataFlowGraph()

        # Add subject resource nodes
        for r_id in candidate_resources:
            graph.add_node(GraphNode(
                node_id=r_id,
                node_type="RESOURCE",
                system_id=self._infer_system_for_resource(r_id),
                has_subject_data=True,
                contains_pii=True,
            ))

        for ch_id in sorted(relevant_channels.keys()):
            proof, edge = self._evaluate_channel_at_audit(
                channel_id=ch_id,
                user_id=user_id or (emails[0] if emails else "unknown_subject"),
                audit_at=audit_at,
            )
            if proof:
                proofs.append(proof)
            if edge:
                graph.add_edge(edge)

        # Detect any cycles in the constructed graph
        cycles = graph.detect_cycles()
        if cycles:
            self.diagnostics["cycles_detected"] += len(cycles)

        return proofs, graph

    def _register_channel(self, ev: Dict[str, Any], channels: Dict[str, Dict[str, Any]]) -> None:
        res_id = ev["resource_id"].strip()
        if res_id.startswith(("data_flow_", "backup_")):
            channels[res_id] = {
                "channel_id": res_id,
                "source_system": ev.get("source_system", ""),
                "target_system": ev.get("target_system", ""),
                "latest_event": ev,
            }
        ds_res = ev.get("_downstream_resource")
        if ds_res and res_id.startswith(("data_flow_", "backup_")):
            channels[res_id]["downstream_resource"] = ds_res

    def _evaluate_channel_at_audit(
        self,
        channel_id: str,
        user_id: str,
        audit_at: datetime,
    ) -> Tuple[Optional[RecreationProof], Optional[GraphEdge]]:
        """
        Determines whether a specific channel is active, disabled, blocked, or historical at audit_at.
        """
        events = [
            e for e in self.events_by_resource.get(channel_id, [])
            if e["_event_time"] <= audit_at
        ]
        events.sort(key=lambda x: (x["_event_time"], x["activity_id"]))

        # Defaults
        is_connector = channel_id.startswith("data_flow_")
        is_backup = channel_id.startswith("backup_")

        source_sys = "integration_service" if is_connector else ("backup_service" if is_backup else "account_service")
        target_sys = "search_service" if is_connector else ("search_service" if is_backup else "analytics_platform")
        flow_type = FlowType.SYNC if is_connector else (FlowType.RESTORE if is_backup else FlowType.REPLICATE)

        latest_status = ActivityStatus.UNKNOWN
        latest_ev = None
        evidence_id = ""

        if events:
            latest_ev = events[-1]
            source_sys = latest_ev.get("source_system") or source_sys
            target_sys = latest_ev.get("target_system") or target_sys
            evidence_id = latest_ev["activity_id"]

            for ev in events:
                ev_type = ev["event_type"]
                result = ev["reported_result"]
                details = ev["details"].lower()

                if is_connector:
                    if ev_type == "CHECK_DATA_FLOW":
                        latest_status = ActivityStatus.ACTIVE if ("enabled" in details or result == "SUCCESS") else ActivityStatus.DISABLED
                    elif ev_type == "DISABLE_DATA_FLOW":
                        latest_status = ActivityStatus.DISABLED if result == "SUCCESS" else ActivityStatus.ACTIVE
                    elif ev_type == "SYNC_RECORD":
                        if "repopulated" in details:
                            latest_status = ActivityStatus.ACTIVE
                        else:
                            latest_status = ActivityStatus.HISTORICAL_COMPLETED
                elif is_backup:
                    if ev_type == "CHECK_RESTORE_ACCESS":
                        latest_status = ActivityStatus.ACTIVE if ("restored" in details or result == "SUCCESS") else ActivityStatus.BLOCKED
                    elif ev_type == "BLOCK_RESTORE":
                        latest_status = ActivityStatus.BLOCKED if result == "SUCCESS" else ActivityStatus.ACTIVE
                    elif ev_type == "RESTORE_BACKUP":
                        latest_status = ActivityStatus.ACTIVE

        # Default fallback if no activity events exist prior to audit_at
        if latest_status == ActivityStatus.UNKNOWN:
            latest_status = ActivityStatus.ACTIVE

        # Construct Edge for Graph
        is_active = (latest_status == ActivityStatus.ACTIVE)
        edge = GraphEdge(
            edge_id=f"edge_{source_sys}_{target_sys}_{channel_id}",
            source_node=source_sys,
            target_node=target_sys,
            flow_type=flow_type,
            channel_id=channel_id,
            status=latest_status,
            event_time=latest_ev["_event_time"] if latest_ev else None,
            evidence_id=evidence_id,
            is_active=is_active,
            can_recreate_pii=is_active,
        )

        # -------------------------------------------------------------
        # 1. Active Data Flow
        # -------------------------------------------------------------
        if is_connector:
            if is_active:
                self.diagnostics["active_flows_detected"] += 1
                finding = Step(
                    step_no=0,
                    phase=Phase.FINDING,
                    system_id=source_sys,
                    resource_id=channel_id,
                    operation=Operation.REPORT_ACTIVE_DATA_FLOW,
                    state=ResourceState.ACTIVE,
                    evidence_id=evidence_id,
                )
                remediation = Step(
                    step_no=0,
                    phase=Phase.REMEDIATION,
                    system_id=source_sys,
                    resource_id=channel_id,
                    operation=Operation.DISABLE_DATA_FLOW,
                    state=ResourceState.DISABLED,
                    evidence_id="",
                )
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=source_sys,
                    resource_id=channel_id,
                    operation=Operation.VERIFY_DATA_FLOW_DISABLED,
                    state=ResourceState.DISABLED,
                    evidence_id="",
                )
                proof = RecreationProof(
                    source=source_sys,
                    destination=target_sys,
                    operation=Operation.REPORT_ACTIVE_DATA_FLOW,
                    current_activity_status=ActivityStatus.ACTIVE,
                    affected_identity=user_id,
                    affected_resource=channel_id,
                    can_recreate_prohibited_data=True,
                    evidence_id=evidence_id,
                    remediation_needed=Operation.DISABLE_DATA_FLOW,
                    verification_needed=Operation.VERIFY_DATA_FLOW_DISABLED,
                    proof_rationale=f"Active connector {channel_id} remains enabled at audit_at and can replicate user data into {target_sys}.",
                    finding_step=finding,
                    remediation_step=remediation,
                    verification_step=verification,
                )
                return proof, edge
            else:
                self.diagnostics["historical_events_filtered"] += 1
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=source_sys,
                    resource_id=channel_id,
                    operation=Operation.VERIFY_DATA_FLOW_DISABLED,
                    state=ResourceState.DISABLED,
                    evidence_id=evidence_id,
                )
                proof = RecreationProof(
                    source=source_sys,
                    destination=target_sys,
                    operation=Operation.VERIFY_DATA_FLOW_DISABLED,
                    current_activity_status=ActivityStatus.DISABLED,
                    affected_identity=user_id,
                    affected_resource=channel_id,
                    can_recreate_prohibited_data=False,
                    evidence_id=evidence_id,
                    remediation_needed=None,
                    verification_needed=Operation.VERIFY_DATA_FLOW_DISABLED,
                    proof_rationale=f"Data flow {channel_id} is verified disabled at audit_at.",
                    finding_step=None,
                    remediation_step=None,
                    verification_step=verification,
                )
                return proof, edge

        # -------------------------------------------------------------
        # 2. Restore Risk / Backup Archive
        # -------------------------------------------------------------
        elif is_backup:
            if is_active:
                self.diagnostics["restore_risks_detected"] += 1
                finding = Step(
                    step_no=0,
                    phase=Phase.FINDING,
                    system_id=source_sys,
                    resource_id=channel_id,
                    operation=Operation.REPORT_RESTORE_RISK,
                    state=ResourceState.ACTIVE,
                    evidence_id=evidence_id,
                )
                remediation = Step(
                    step_no=0,
                    phase=Phase.REMEDIATION,
                    system_id=source_sys,
                    resource_id=channel_id,
                    operation=Operation.BLOCK_RESTORE,
                    state=ResourceState.BLOCKED,
                    evidence_id="",
                )
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=source_sys,
                    resource_id=channel_id,
                    operation=Operation.VERIFY_RESTORE_BLOCKED,
                    state=ResourceState.BLOCKED,
                    evidence_id="",
                )
                proof = RecreationProof(
                    source=source_sys,
                    destination=target_sys,
                    operation=Operation.REPORT_RESTORE_RISK,
                    current_activity_status=ActivityStatus.ACTIVE,
                    affected_identity=user_id,
                    affected_resource=channel_id,
                    can_recreate_prohibited_data=True,
                    evidence_id=evidence_id,
                    remediation_needed=Operation.BLOCK_RESTORE,
                    verification_needed=Operation.VERIFY_RESTORE_BLOCKED,
                    proof_rationale=f"Backup archive {channel_id} has active restore capability at audit_at, presenting ongoing recreation risk.",
                    finding_step=finding,
                    remediation_step=remediation,
                    verification_step=verification,
                )
                return proof, edge
            else:
                self.diagnostics["historical_events_filtered"] += 1
                verification = Step(
                    step_no=0,
                    phase=Phase.VERIFICATION,
                    system_id=source_sys,
                    resource_id=channel_id,
                    operation=Operation.VERIFY_RESTORE_BLOCKED,
                    state=ResourceState.BLOCKED,
                    evidence_id=evidence_id,
                )
                proof = RecreationProof(
                    source=source_sys,
                    destination=target_sys,
                    operation=Operation.VERIFY_RESTORE_BLOCKED,
                    current_activity_status=ActivityStatus.BLOCKED,
                    affected_identity=user_id,
                    affected_resource=channel_id,
                    can_recreate_prohibited_data=False,
                    evidence_id=evidence_id,
                    remediation_needed=None,
                    verification_needed=Operation.VERIFY_RESTORE_BLOCKED,
                    proof_rationale=f"Backup archive {channel_id} restore access is verified blocked at audit_at.",
                    finding_step=None,
                    remediation_step=None,
                    verification_step=verification,
                )
                return proof, edge

        return None, edge

    def _infer_system_for_resource(self, resource_id: str) -> str:
        if resource_id.startswith("account_"):
            return "account_service"
        elif resource_id.startswith("search_"):
            return "search_service"
        elif resource_id.startswith("analytics_"):
            return "analytics_platform"
        elif resource_id.startswith("support_"):
            return "support_platform"
        elif resource_id.startswith("export_"):
            return "export_service"
        elif resource_id.startswith("cache_"):
            return "cache_service"
        elif resource_id.startswith("backup_"):
            return "backup_service"
        elif resource_id.startswith("data_flow_"):
            return "integration_service"
        elif resource_id.startswith("audit_record_"):
            return "security_service"
        return "core_system"
