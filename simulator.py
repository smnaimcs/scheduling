"""
simulator.py — Simplified Kubernetes Cluster Simulator
Parses the OpenB GPU node dataset and provides cluster state management.
"""

import yaml
import random
import copy
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum


# ---------------------------------------------------------------------------
# GPU Tier ranking (higher = more powerful)
# ---------------------------------------------------------------------------
GPU_TIER = {
    "A10":     7,
    "G3":      6,
    "V100M32": 5,
    "V100M16": 4,
    "G2":      3,
    "T4":      2,
    "P100":    1,
}

GPU_COMPUTE_TFLOPS = {
    "A10":     31.2,
    "G3":      14.0,   # Alibaba G3 ≈ A100 class
    "V100M32": 14.0,
    "V100M16": 14.0,
    "G2":       6.0,
    "T4":       8.1,
    "P100":     9.3,
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class NodeResources:
    cpu_milli: int          # millicores
    memory_mi: int          # MiB
    gpu_count: int
    gpu_milli: int          # milli-GPUs (1000 = 1 full GPU)
    gpu_model: str


@dataclass
class Node:
    name: str
    labels: Dict[str, str]
    capacity: NodeResources
    allocatable: NodeResources
    # Available = allocatable minus what's currently used
    available: NodeResources = field(init=False)
    pod_count: int = 0
    max_pods: int = 1001

    def __post_init__(self):
        self.available = copy.deepcopy(self.allocatable)

    def gpu_tier(self) -> int:
        return GPU_TIER.get(self.allocatable.gpu_model, 0)

    def utilization(self) -> Dict[str, float]:
        alloc = self.allocatable
        avail = self.available
        cpu_used  = alloc.cpu_milli  - avail.cpu_milli
        mem_used  = alloc.memory_mi  - avail.memory_mi
        gpu_used  = alloc.gpu_milli  - avail.gpu_milli
        return {
            "cpu":    cpu_used  / max(alloc.cpu_milli, 1),
            "memory": mem_used  / max(alloc.memory_mi, 1),
            "gpu":    gpu_used  / max(alloc.gpu_milli, 1) if alloc.gpu_milli > 0 else 0.0,
        }

    def can_fit(self, pod: "Pod") -> bool:
        a = self.available
        return (
            a.cpu_milli  >= pod.cpu_milli  and
            a.memory_mi  >= pod.memory_mi  and
            a.gpu_count  >= pod.gpu_count  and
            a.gpu_milli  >= pod.gpu_milli  and
            self.pod_count < self.max_pods
        )

    def allocate(self, pod: "Pod") -> None:
        self.available.cpu_milli  -= pod.cpu_milli
        self.available.memory_mi  -= pod.memory_mi
        self.available.gpu_count  -= pod.gpu_count
        self.available.gpu_milli  -= pod.gpu_milli
        self.pod_count += 1


@dataclass
class Pod:
    name: str
    cpu_milli: int
    memory_mi: int
    gpu_count: int
    gpu_milli: int
    preferred_gpu_model: Optional[str] = None   # hints only — not hard constraint
    priority: int = 0                            # 0-9 (higher = schedule first)

    def is_gpu_pod(self) -> bool:
        return self.gpu_count > 0


@dataclass
class SchedulingResult:
    pod_name: str
    node_name: Optional[str]
    scheduled: bool
    score: float = 0.0
    reason: str = ""


# ---------------------------------------------------------------------------
# Cluster
# ---------------------------------------------------------------------------
class Cluster:
    """Holds cluster state. Passed to each scheduler."""

    def __init__(self, nodes: List[Node]):
        self.nodes: Dict[str, Node] = {n.name: n for n in nodes}
        self._snapshot: Optional[Dict] = None

    def snapshot(self) -> "Cluster":
        """Return a deep copy for independent simulation runs."""
        c = Cluster.__new__(Cluster)
        c.nodes = {k: copy.deepcopy(v) for k, v in self.nodes.items()}
        return c

    def node_list(self) -> List[Node]:
        return list(self.nodes.values())

    def total_gpu_milli(self) -> int:
        return sum(n.allocatable.gpu_milli for n in self.nodes.values())

    def used_gpu_milli(self) -> int:
        return sum(
            n.allocatable.gpu_milli - n.available.gpu_milli
            for n in self.nodes.values()
        )

    def total_cpu_milli(self) -> int:
        return sum(n.allocatable.cpu_milli for n in self.nodes.values())

    def used_cpu_milli(self) -> int:
        return sum(
            n.allocatable.cpu_milli - n.available.cpu_milli
            for n in self.nodes.values()
        )

    def total_memory_mi(self) -> int:
        return sum(n.allocatable.memory_mi for n in self.nodes.values())

    def used_memory_mi(self) -> int:
        return sum(
            n.allocatable.memory_mi - n.available.memory_mi
            for n in self.nodes.values()
        )


# ---------------------------------------------------------------------------
# YAML parser
# ---------------------------------------------------------------------------
def _parse_cpu(val: str) -> int:
    """Convert Kubernetes cpu string to millicores."""
    val = str(val).strip()
    if val.endswith("m"):
        return int(val[:-1])
    return int(float(val) * 1000)


def _parse_memory(val: str) -> int:
    """Convert Kubernetes memory string to MiB."""
    val = str(val).strip()
    units = {"Ki": 1/1024, "Mi": 1, "Gi": 1024, "Ti": 1024*1024,
             "K": 1/1.024/1000, "M": 1/1.024, "G": 1024/1.024}
    for suffix, factor in units.items():
        if val.endswith(suffix):
            return int(float(val[:-len(suffix)]) * factor)
    return int(val) // (1024 * 1024)   # assume bytes


def load_cluster(yaml_path: str) -> Cluster:
    """Parse all Node documents from the YAML file and return a Cluster."""
    with open(yaml_path, "r") as f:
        raw = f.read()

    docs = list(yaml.safe_load_all(raw))
    nodes: List[Node] = []

    for doc in docs:
        if not doc or doc.get("kind") != "Node":
            continue

        meta   = doc.get("metadata", {})
        labels = meta.get("labels", {})
        name   = meta.get("name", "unknown")
        status = doc.get("status", {})

        def parse_resources(section: dict) -> NodeResources:
            cpu    = _parse_cpu(section.get("cpu", "0"))
            mem    = _parse_memory(section.get("memory", "0Mi"))
            gpuc   = int(section.get("alibabacloud.com/gpu-count", "0"))
            gpum   = int(section.get("alibabacloud.com/gpu-milli", "0"))
            model  = labels.get("alibabacloud.com/gpu-card-model", "unknown")
            return NodeResources(cpu, mem, gpuc, gpum, model)

        capacity    = parse_resources(status.get("capacity",    {}))
        allocatable = parse_resources(status.get("allocatable", {}))

        nodes.append(Node(
            name=name,
            labels=labels,
            capacity=capacity,
            allocatable=allocatable,
        ))

    print(f"[Cluster] Loaded {len(nodes)} nodes.")
    return Cluster(nodes)


# ---------------------------------------------------------------------------
# Workload generator
# ---------------------------------------------------------------------------
WORKLOAD_PROFILES = [
    # (name, cpu_range, mem_range, gpu_count, gpu_milli, preferred_gpu, weight, priority)
    ("small-cpu-job",    (500,  2000),  (512,   4096),  0, 0,    None,       20, 2),
    ("medium-cpu-job",   (2000, 8000),  (4096,  16384), 0, 0,    None,       15, 3),
    ("p100-training",    (4000, 16000), (32768, 65536), 1, 1000, "P100",     10, 5),
    ("t4-inference",     (2000, 8000),  (16384, 32768), 1, 1000, "T4",       12, 4),
    ("v100-training",    (8000, 32000), (65536, 131072),2, 2000, "V100M32",   6, 7),
    ("v100-16-job",      (4000, 16000), (32768, 65536), 1, 1000, "V100M16",   5, 6),
    ("g2-training",      (8000, 32000), (65536, 131072),4, 4000, "G2",        8, 6),
    ("g3-large-job",     (16000,48000), (131072,262144),8, 8000, "G3",        3, 9),
    ("a10-cutting-edge", (8000, 32000), (65536, 131072),2, 2000, "A10",       1, 9),
    ("multi-gpu-g2",     (16000,32000), (65536, 131072),4, 4000, "G2",        4, 7),
]

def generate_workload(n_pods: int = 500, seed: int = 42) -> List[Pod]:
    """Generate a realistic mixed GPU/CPU workload."""
    random.seed(seed)
    pods: List[Pod] = []

    weights   = [p[7] for p in WORKLOAD_PROFILES]
    total_w   = sum(weights)
    cumulative = []
    acc = 0
    for w in weights:
        acc += w
        cumulative.append(acc / total_w)

    for i in range(n_pods):
        r = random.random()
        for j, c in enumerate(cumulative):
            if r <= c:
                profile = WORKLOAD_PROFILES[j]
                break

        name, cpu_r, mem_r, gpuc, gpum, pref_gpu, _, priority = profile
        cpu = random.randint(*cpu_r)
        mem = random.randint(*mem_r)
        pods.append(Pod(
            name=f"pod-{i:04d}-{name}",
            cpu_milli=cpu,
            memory_mi=mem,
            gpu_count=gpuc,
            gpu_milli=gpum,
            preferred_gpu_model=pref_gpu,
            priority=priority,
        ))

    # Sort by priority (highest first) — simulates PriorityClass
    pods.sort(key=lambda p: -p.priority)
    return pods


# ---------------------------------------------------------------------------
# Metrics collector
# ---------------------------------------------------------------------------
class SimulationMetrics:
    def __init__(self, scheduler_name: str, cluster: Cluster, results: List[SchedulingResult], pods: List[Pod]):
        self.scheduler_name = scheduler_name
        self.results = results
        self.cluster = cluster
        self.pods = pods
        self._compute()

    def _compute(self):
        total = len(self.results)
        scheduled = [r for r in self.results if r.scheduled]

        self.total_pods         = total
        self.scheduled_count    = len(scheduled)
        self.unscheduled_count  = total - len(scheduled)
        self.schedule_rate      = self.scheduled_count / max(total, 1) * 100

        # GPU utilization
        total_gpu = self.cluster.total_gpu_milli()
        used_gpu  = self.cluster.used_gpu_milli()
        self.gpu_utilization    = used_gpu  / max(total_gpu, 1) * 100

        # CPU utilization
        total_cpu = self.cluster.total_cpu_milli()
        used_cpu  = self.cluster.used_cpu_milli()
        self.cpu_utilization    = used_cpu  / max(total_cpu, 1) * 100

        # Memory utilization
        total_mem = self.cluster.total_memory_mi()
        used_mem  = self.cluster.used_memory_mi()
        self.memory_utilization = used_mem  / max(total_mem, 1) * 100

        # Fragmentation: nodes that have resources but can fit NO more GPU pods
        gpu_pods_remaining = [p for p in self.pods if p.is_gpu_pod()]
        fragment_nodes = 0
        total_nodes_with_gpu = 0
        for node in self.cluster.node_list():
            if node.allocatable.gpu_count > 0:
                total_nodes_with_gpu += 1
                # Check if any GPU pod could fit
                can_fit_any = any(node.can_fit(p) for p in gpu_pods_remaining[:20])
                if not can_fit_any and node.available.gpu_milli > 0:
                    fragment_nodes += 1

        self.fragmentation_rate = fragment_nodes / max(total_nodes_with_gpu, 1) * 100

        # Load balance score: std dev of utilization across nodes (lower = better balanced)
        utils = [node.utilization()["cpu"] for node in self.cluster.node_list()]
        if utils:
            mean_u = sum(utils) / len(utils)
            variance = sum((u - mean_u)**2 for u in utils) / len(utils)
            self.load_balance_score = max(0, 100 - (variance**0.5) * 200)
        else:
            self.load_balance_score = 0

        # Average scheduling score
        self.avg_score = sum(r.score for r in scheduled) / max(len(scheduled), 1)

        # GPU pod metrics
        gpu_pods = [p for p in self.pods if p.is_gpu_pod()]
        gpu_scheduled = [r for r in scheduled if any(
            p.name == r.pod_name and p.is_gpu_pod() for p in self.pods
        )]
        self.gpu_pod_total       = len(gpu_pods)
        self.gpu_pod_scheduled   = len(gpu_scheduled)
        self.gpu_pod_schedule_rate = self.gpu_pod_scheduled / max(len(gpu_pods), 1) * 100

        # Active node count
        self.active_nodes = sum(1 for n in self.cluster.node_list() if n.pod_count > 0)
        self.total_nodes  = len(self.cluster.node_list())

        # Per-node utilization for heatmap
        self.node_utils = []
        for node in self.cluster.node_list():
            u = node.utilization()
            self.node_utils.append({
                "name": node.name,
                "gpu_model": node.allocatable.gpu_model,
                "cpu_util": round(u["cpu"] * 100, 1),
                "mem_util": round(u["memory"] * 100, 1),
                "gpu_util": round(u["gpu"] * 100, 1),
                "pod_count": node.pod_count,
            })

    def summary(self) -> str:
        lines = [
            f"\n{'='*60}",
            f"  Scheduler: {self.scheduler_name}",
            f"{'='*60}",
            f"  Pods Total          : {self.total_pods}",
            f"  Pods Scheduled      : {self.scheduled_count} ({self.schedule_rate:.1f}%)",
            f"  Pods Unscheduled    : {self.unscheduled_count}",
            f"  GPU Pods Scheduled  : {self.gpu_pod_scheduled}/{self.gpu_pod_total} ({self.gpu_pod_schedule_rate:.1f}%)",
            f"  GPU Utilization     : {self.gpu_utilization:.1f}%",
            f"  CPU Utilization     : {self.cpu_utilization:.1f}%",
            f"  Memory Utilization  : {self.memory_utilization:.1f}%",
            f"  Fragmentation Rate  : {self.fragmentation_rate:.1f}%",
            f"  Load Balance Score  : {self.load_balance_score:.1f}/100",
            f"  Active Nodes        : {self.active_nodes}/{self.total_nodes}",
            f"  Avg Scheduling Score: {self.avg_score:.2f}",
            f"{'='*60}",
        ]
        return "\n".join(lines)
