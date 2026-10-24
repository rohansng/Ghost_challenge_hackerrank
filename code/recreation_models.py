"""
Phase 4 Recreation Models
Directed graph models, flow channels, activity statuses, and explainable recreation proofs.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any, Set, Tuple

from code.evidence_models import ObservedState
from code.models import Operation, ResourceState, Phase, Step


class FlowType(str, Enum):
    SYNC = "SYNC"
    RESTORE = "RESTORE"
    REPLICATE = "REPLICATE"
    EXPORT = "EXPORT"
    INDEX = "INDEX"
    CACHE_REFRESH = "CACHE_REFRESH"


class ActivityStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    BLOCKED = "BLOCKED"
    HISTORICAL_COMPLETED = "HISTORICAL_COMPLETED"
    INACTIVE = "INACTIVE"
    UNKNOWN = "UNKNOWN"


@dataclass
class FlowChannel:
    """Represents a discrete data pipeline, connector, or restore channel."""
    channel_id: str
    source_system: str
    target_system: str
    flow_type: FlowType
    status: ActivityStatus
    last_event_time: Optional[datetime] = None
    evidence_id: str = ""
    is_recurring: bool = False
    recreates_pii: bool = True
    affected_resource_id: Optional[str] = None
    affected_user_id: Optional[str] = None
    details: str = ""


@dataclass
class GraphNode:
    """Represents a system, service, database, or resource entity in the recreation graph."""
    node_id: str
    node_type: str  # SYSTEM, RESOURCE, BACKUP, CONNECTOR, EXPORT
    system_id: str
    has_subject_data: bool = False
    state_at_audit: ObservedState = ObservedState.UNKNOWN
    contains_pii: bool = False


@dataclass
class GraphEdge:
    """Represents a directed synchronization, restore, or export flow between nodes."""
    edge_id: str
    source_node: str
    target_node: str
    flow_type: FlowType
    channel_id: str
    status: ActivityStatus
    event_time: Optional[datetime] = None
    evidence_id: str = ""
    is_active: bool = False
    can_recreate_pii: bool = True


@dataclass
class RecreationPath:
    """Identified pathway through which deleted or preserved subject data can reach a target system."""
    path_id: str
    source_node: str
    target_node: str
    edges: List[GraphEdge]
    is_active: bool
    recreation_risk: str
    affected_resource: str
    evidence_id: str = ""


@dataclass
class RecreationProof:
    """Canonical explainable decision model for process-level recreation analysis."""
    source: str
    destination: str
    operation: Operation
    current_activity_status: ActivityStatus
    affected_identity: str
    affected_resource: str
    can_recreate_prohibited_data: bool
    evidence_id: str
    remediation_needed: Optional[Operation]
    verification_needed: Optional[Operation]
    proof_rationale: str
    finding_step: Optional[Step] = None
    remediation_step: Optional[Step] = None
    verification_step: Optional[Step] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "destination": self.destination,
            "operation": self.operation.value,
            "status": self.current_activity_status.value,
            "affected_identity": self.affected_identity,
            "affected_resource": self.affected_resource,
            "can_recreate_prohibited_data": self.can_recreate_prohibited_data,
            "evidence_id": self.evidence_id,
            "remediation_needed": self.remediation_needed.value if self.remediation_needed else None,
            "verification_needed": self.verification_needed.value if self.verification_needed else None,
            "proof_rationale": self.proof_rationale,
        }


class DataFlowGraph:
    """
    Directed graph representing cross-system data movement and recovery paths.
    Enables deterministic reachability analysis and cycle detection.
    """

    def __init__(self):
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: Dict[str, List[GraphEdge]] = {}  # source_node -> outgoing edges

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.node_id] = node
        if node.node_id not in self.edges:
            self.edges[node.node_id] = []

    def add_edge(self, edge: GraphEdge) -> None:
        if edge.source_node not in self.nodes:
            self.add_node(GraphNode(edge.source_node, "SYSTEM", edge.source_node))
        if edge.target_node not in self.nodes:
            self.add_node(GraphNode(edge.target_node, "SYSTEM", edge.target_node))
        self.edges[edge.source_node].append(edge)

    def find_active_recreation_paths(
        self,
        surviving_source_nodes: List[str],
        target_systems: Optional[List[str]] = None,
    ) -> List[RecreationPath]:
        """
        Traverses active edges from surviving source nodes to discover any downstream target
        where deleted subject data could be repopulated.
        """
        active_paths: List[RecreationPath] = []
        targets = set(target_systems) if target_systems else None

        for src in surviving_source_nodes:
            if src not in self.nodes:
                continue

            # BFS / DFS traversal tracking paths
            queue: List[Tuple[str, List[GraphEdge]]] = [(src, [])]
            visited: Set[str] = set()

            while queue:
                curr_node, path_edges = queue.pop(0)
                if curr_node in visited and len(path_edges) > 0:
                    continue
                visited.add(curr_node)

                for edge in self.edges.get(curr_node, []):
                    if not edge.is_active:
                        continue

                    new_path = path_edges + [edge]
                    dest = edge.target_node

                    if targets is None or dest in targets:
                        path_id = f"path_{src}_{dest}_{edge.channel_id}"
                        active_paths.append(RecreationPath(
                            path_id=path_id,
                            source_node=src,
                            target_node=dest,
                            edges=new_path,
                            is_active=True,
                            recreation_risk=f"Active {edge.flow_type.value} flow via {edge.channel_id} can recreate data in {dest}",
                            affected_resource=edge.channel_id,
                            evidence_id=edge.evidence_id,
                        ))

                    if dest not in visited:
                        queue.append((dest, new_path))

        return active_paths

    def detect_cycles(self) -> List[List[str]]:
        """
        Detects directed cycles in data flow graph using DFS color coding.
        Returns list of cycles where each cycle is a list of node IDs.
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n: WHITE for n in self.nodes}
        cycles: List[List[str]] = []
        parent_map: Dict[str, Optional[str]] = {}

        def dfs(u: str, current_path: List[str]):
            color[u] = GRAY
            current_path.append(u)

            for edge in self.edges.get(u, []):
                v = edge.target_node
                if color.get(v, WHITE) == GRAY:
                    # Cycle found
                    cycle_start = current_path.index(v)
                    cycles.append(current_path[cycle_start:] + [v])
                elif color.get(v, WHITE) == WHITE:
                    dfs(v, current_path)

            current_path.pop()
            color[u] = BLACK

        for node_id in self.nodes:
            if color[node_id] == WHITE:
                dfs(node_id, [])

        return cycles
