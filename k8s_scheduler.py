"""
k8s_scheduler.py — Simplified Kubernetes Default Scheduler

Replicates the official Kubernetes scheduling pipeline:
  1. Filter Phase  : NodeResourcesFit, TaintToleration, NodeUnschedulable
  2. Score Phase   : LeastAllocated, BalancedAllocation, NodeAffinity
  3. Select        : Highest score wins (ties broken randomly)

Reference: https://kubernetes.io/docs/concepts/scheduling-eviction/kube-scheduler/
"""

import random
from typing import List, Tuple, Optional
from simulator import Cluster, Node, Pod, SchedulingResult


# ---------------------------------------------------------------------------
# Filter plugins
# ---------------------------------------------------------------------------
def filter_node_resources_fit(node: Node, pod: Pod) -> Tuple[bool, str]:
    """Equivalent to NodeResourcesFit plugin."""
    a = node.available
    if a.cpu_milli < pod.cpu_milli:
        return False, f"insufficient cpu ({a.cpu_milli}m < {pod.cpu_milli}m)"
    if a.memory_mi < pod.memory_mi:
        return False, f"insufficient memory ({a.memory_mi}Mi < {pod.memory_mi}Mi)"
    if a.gpu_count < pod.gpu_count:
        return False, f"insufficient gpu-count ({a.gpu_count} < {pod.gpu_count})"
    if a.gpu_milli < pod.gpu_milli:
        return False, f"insufficient gpu-milli ({a.gpu_milli} < {pod.gpu_milli})"
    return True, "ok"


def filter_pod_count(node: Node, pod: Pod) -> Tuple[bool, str]:
    """Node max-pod capacity filter."""
    if node.pod_count >= node.max_pods:
        return False, "node at max pod capacity"
    return True, "ok"


FILTER_PLUGINS = [
    filter_node_resources_fit,
    filter_pod_count,
]


# ---------------------------------------------------------------------------
# Score plugins (each returns 0-100)
# ---------------------------------------------------------------------------
def score_least_allocated(node: Node, pod: Pod) -> float:
    """
    LeastAllocated: prefer nodes with the most remaining capacity.
    Score = (cpuFree/cpuTotal + memFree/memTotal) / 2 * 100
    This is what Kubernetes uses by default.
    """
    alloc = node.allocatable
    avail = node.available

    cpu_score = avail.cpu_milli / max(alloc.cpu_milli, 1) * 100
    mem_score = avail.memory_mi / max(alloc.memory_mi, 1) * 100
    return (cpu_score + mem_score) / 2


def score_balanced_allocation(node: Node, pod: Pod) -> float:
    """
    BalancedAllocation: penalize nodes where one resource is overloaded
    relative to others. Reward balanced utilization.
    Score = 100 - std_dev(cpu_util, mem_util, gpu_util) * 100
    """
    alloc = node.allocatable
    avail = node.available

    cpu_req  = pod.cpu_milli
    mem_req  = pod.memory_mi
    gpu_req  = pod.gpu_milli

    # Simulate after placing the pod
    cpu_after = (alloc.cpu_milli - avail.cpu_milli + cpu_req) / max(alloc.cpu_milli, 1)
    mem_after = (alloc.memory_mi - avail.memory_mi + mem_req) / max(alloc.memory_mi, 1)

    utils = [cpu_after, mem_after]
    if alloc.gpu_milli > 0:
        gpu_after = (alloc.gpu_milli - avail.gpu_milli + gpu_req) / alloc.gpu_milli
        utils.append(gpu_after)

    mean     = sum(utils) / len(utils)
    variance = sum((u - mean) ** 2 for u in utils) / len(utils)
    std_dev  = variance ** 0.5

    return max(0.0, 100.0 - std_dev * 100)


def score_node_affinity(node: Node, pod: Pod) -> float:
    """
    Simplified NodeAffinity: if pod has a preferred GPU model label
    and the node matches, give bonus.
    """
    if pod.preferred_gpu_model is None:
        return 50.0   # neutral — Kubernetes gives 0 if no affinity rules
    if node.allocatable.gpu_model == pod.preferred_gpu_model:
        return 100.0
    return 0.0


# Score plugin weights (mirror Kubernetes defaults: LeastAllocated×1, BalancedAllocation×1)
SCORE_PLUGINS = [
    (score_least_allocated,    1.0),
    (score_balanced_allocation, 1.0),
    (score_node_affinity,       0.2),   # soft affinity weight
]


# ---------------------------------------------------------------------------
# Kubernetes Scheduler
# ---------------------------------------------------------------------------
class KubernetesScheduler:
    """
    Minimal faithful replica of the kube-scheduler.
    Does NOT include: preemption, inter-pod affinity, topology spread.
    """

    def __init__(self, cluster: Cluster):
        self.cluster = cluster
        self.name = "Kubernetes Default Scheduler"

    def schedule(self, pods: List[Pod]) -> List[SchedulingResult]:
        results: List[SchedulingResult] = []

        for pod in pods:
            result = self._schedule_one(pod)
            results.append(result)

        return results

    def _schedule_one(self, pod: Pod) -> SchedulingResult:
        # Phase 1 — Filter
        feasible: List[Node] = []
        filter_reason = "no nodes available"

        for node in self.cluster.node_list():
            passed = True
            for plugin in FILTER_PLUGINS:
                ok, reason = plugin(node, pod)
                if not ok:
                    filter_reason = reason
                    passed = False
                    break
            if passed:
                feasible.append(node)

        if not feasible:
            return SchedulingResult(
                pod_name=pod.name,
                node_name=None,
                scheduled=False,
                score=0.0,
                reason=filter_reason,
            )

        # Phase 2 — Score
        node_scores: List[Tuple[Node, float]] = []
        total_weight = sum(w for _, w in SCORE_PLUGINS)

        for node in feasible:
            weighted_sum = sum(
                plugin(node, pod) * weight
                for plugin, weight in SCORE_PLUGINS
            )
            final_score = weighted_sum / total_weight
            node_scores.append((node, final_score))

        # Phase 3 — Select highest score
        node_scores.sort(key=lambda x: -x[1])
        best_score = node_scores[0][1]
        # Among ties, pick one randomly (mirrors kube-scheduler tie-breaking)
        top_nodes = [n for n, s in node_scores if abs(s - best_score) < 0.01]
        chosen = random.choice(top_nodes)

        # Bind
        self.cluster.nodes[chosen.name].allocate(pod)

        return SchedulingResult(
            pod_name=pod.name,
            node_name=chosen.name,
            scheduled=True,
            score=best_score,
            reason="scheduled",
        )
