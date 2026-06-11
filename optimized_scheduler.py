"""
optimized_scheduler.py — GPU-Aware Optimized Scheduler

Methodology
-----------
This scheduler is specifically designed for heterogeneous GPU clusters
like the Alibaba OpenB dataset. It addresses four key weaknesses in the
standard Kubernetes scheduler:

1. GPU TIER MATCHING (vs. K8s ignoring GPU model differences)
   ─────────────────────────────────────────────────────────
   K8s treats all GPUs as generic 'count' integers. Our scheduler
   maintains a compute-power ranking: A10 > G3 > V100M32 > V100M16 > G2 > T4 > P100
   A job requesting a weak GPU will NOT be placed on a premium node unless
   no better match exists. This preserves high-tier GPUs for demanding workloads.

2. GPU-WEIGHTED BIN-PACKING (vs. K8s's LeastAllocated spread)
   ────────────────────────────────────────────────────────────
   K8s's LeastAllocated score SPREADS pods across nodes (50% CPU + 50% mem).
   This causes GPU fragmentation: many nodes with 1 leftover GPU slot that
   can't serve large multi-GPU jobs.
   
   Our scheduler uses BIN-PACKING for GPU resources (prefer nodes already
   partially full of GPUs before spreading). We score as:
       GPU Bin-Pack score = GPU_used_after / GPU_total  (higher = more packed)
   Combined with a ceiling: avoid nodes at >85% utilization in ANY dimension.

3. MULTI-RESOURCE WEIGHTED SCORING
   ─────────────────────────────────
   Weights are calibrated to this specific dataset:
       GPU score   : weight 0.50  (dominant resource in a GPU cluster)
       CPU score   : weight 0.30
       Memory score: weight 0.20
   
   K8s uses equal weights (0.5 CPU + 0.5 mem, GPU ignored in BalancedAlloc).

4. TAIL-LATENCY PREVENTION (resource headroom)
   ─────────────────────────────────────────────
   Nodes at >85% in ANY resource are deprioritized (score penalty × 0.4).
   This reserves headroom for burst workloads, reducing evictions and
   scheduling failures.

5. LOOK-AHEAD ANTI-FRAGMENTATION (for large GPU jobs ≥4 GPUs)
   ─────────────────────────────────────────────────────────────
   For large GPU requests, the scheduler checks whether placing this pod
   would leave a node with an odd number of remaining GPUs (< minimum job
   need). Such placements are penalized to prevent stranded capacity.
"""

from typing import List, Tuple, Optional, Dict
from simulator import Cluster, Node, Pod, SchedulingResult, GPU_TIER, GPU_COMPUTE_TFLOPS


# ---------------------------------------------------------------------------
# Configurable hyper-parameters
# ---------------------------------------------------------------------------
GPU_WEIGHT    = 0.50
CPU_WEIGHT    = 0.30
MEM_WEIGHT    = 0.20
CEILING       = 0.85   # avoid nodes already at >85% utilization
PENALTY       = 0.40   # score multiplier when ceiling exceeded


# ---------------------------------------------------------------------------
# Filter Phase — same as K8s (correctness baseline)
# ---------------------------------------------------------------------------
def _filter(node: Node, pod: Pod) -> Tuple[bool, str]:
    a = node.available
    if a.cpu_milli < pod.cpu_milli:
        return False, "cpu"
    if a.memory_mi < pod.memory_mi:
        return False, "memory"
    if a.gpu_count < pod.gpu_count:
        return False, "gpu-count"
    if a.gpu_milli < pod.gpu_milli:
        return False, "gpu-milli"
    if node.pod_count >= node.max_pods:
        return False, "max-pods"
    return True, "ok"


# ---------------------------------------------------------------------------
# GPU Tier filter (soft — used in scoring, not hard filter)
# ---------------------------------------------------------------------------
def _tier_penalty(node: Node, pod: Pod) -> float:
    """
    Returns a multiplier [0.1, 1.0].
    - 1.0 if GPU model matches or pod has no GPU
    - 0.6 if node GPU is overkill (higher tier than needed) — better to save it
    - 0.1 if node GPU is LOWER tier than preferred (placement of last resort)
    """
    if pod.preferred_gpu_model is None or not pod.is_gpu_pod():
        return 1.0

    node_tier = GPU_TIER.get(node.allocatable.gpu_model, 0)
    pod_tier  = GPU_TIER.get(pod.preferred_gpu_model,    0)

    if node_tier == pod_tier:
        return 1.0
    elif node_tier > pod_tier:
        # Node is MORE powerful than needed — slight penalty to preserve premium nodes
        delta = node_tier - pod_tier
        return max(0.60, 1.0 - delta * 0.08)
    else:
        # Node is LESS powerful — significant penalty
        delta = pod_tier - node_tier
        return max(0.10, 1.0 - delta * 0.20)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def _score_gpu_bin_pack(node: Node, pod: Pod) -> float:
    """
    GPU bin-packing: prefer nodes that are already using their GPUs.
    Score = (GPU used after placement) / GPU total
    Returns 0 if node has no GPU (irrelevant for CPU-only pods).
    """
    alloc = node.allocatable
    if alloc.gpu_milli == 0:
        return 0.0

    used_after = (alloc.gpu_milli - node.available.gpu_milli + pod.gpu_milli)
    return min(1.0, used_after / alloc.gpu_milli) * 100


def _score_cpu_pack(node: Node, pod: Pod) -> float:
    """CPU bin-pack score."""
    alloc = node.allocatable
    used_after = (alloc.cpu_milli - node.available.cpu_milli + pod.cpu_milli)
    return min(1.0, used_after / max(alloc.cpu_milli, 1)) * 100


def _score_mem_pack(node: Node, pod: Pod) -> float:
    """Memory bin-pack score."""
    alloc = node.allocatable
    used_after = (alloc.memory_mi - node.available.memory_mi + pod.memory_mi)
    return min(1.0, used_after / max(alloc.memory_mi, 1)) * 100


def _ceiling_penalty(node: Node) -> float:
    """Returns PENALTY multiplier if node exceeds ceiling in any dimension."""
    u = node.utilization()
    if any(v > CEILING for v in u.values()):
        return PENALTY
    return 1.0


def _anti_fragment_bonus(node: Node, pod: Pod) -> float:
    """
    For large GPU pods (≥4 GPUs): bonus if placement doesn't leave
    an odd stranded GPU count on this node.
    For small pods: small bonus if remaining GPU count >= 4 (avoids
    leaving a node unable to host any large jobs).
    """
    if node.allocatable.gpu_milli == 0:
        return 1.0

    remaining_gpu = node.available.gpu_count - pod.gpu_count
    if pod.gpu_count >= 4:
        # Ideal: use all remaining or leave a multiple of 4
        if remaining_gpu == 0:
            return 1.15   # perfect fit — bonus
        elif remaining_gpu % 4 == 0:
            return 1.10   # leaves clean chunks
        else:
            return 0.90   # fragments the node
    else:
        # Small pods: prefer leaving ≥4 GPU slots free for future large jobs
        if remaining_gpu >= 4:
            return 1.05
        elif remaining_gpu == 0:
            return 1.10   # full utilization is fine
        else:
            return 0.95   # leaves an awkward number


# ---------------------------------------------------------------------------
# Optimized Scheduler
# ---------------------------------------------------------------------------
class OptimizedScheduler:
    """
    GPU-Aware Bin-Packing Scheduler with Tier Matching and Anti-Fragmentation.
    Specifically tuned for heterogeneous GPU clusters (Alibaba OpenB dataset).
    """

    def __init__(self, cluster: Cluster):
        self.cluster = cluster
        self.name = "Optimized GPU-Aware Scheduler (Antigravity)"

    def schedule(self, pods: List[Pod]) -> List[SchedulingResult]:
        results: List[SchedulingResult] = []
        for pod in pods:
            result = self._schedule_one(pod)
            results.append(result)
        return results

    def _schedule_one(self, pod: Pod) -> SchedulingResult:
        # ── Phase 1: Filter ──────────────────────────────────────────────
        feasible: List[Node] = []
        last_fail_reason = "no nodes"

        for node in self.cluster.node_list():
            ok, reason = _filter(node, pod)
            if ok:
                feasible.append(node)
            else:
                last_fail_reason = reason

        if not feasible:
            return SchedulingResult(
                pod_name=pod.name,
                node_name=None,
                scheduled=False,
                score=0.0,
                reason=last_fail_reason,
            )

        # ── Phase 2: Score ───────────────────────────────────────────────
        node_scores: List[Tuple[Node, float]] = []

        for node in feasible:
            # Core multi-resource weighted score
            if pod.is_gpu_pod():
                core_score = (
                    _score_gpu_bin_pack(node, pod) * GPU_WEIGHT +
                    _score_cpu_pack(node, pod)     * CPU_WEIGHT +
                    _score_mem_pack(node, pod)     * MEM_WEIGHT
                )
            else:
                # For CPU-only pods: use least-allocated (spread), not bin-pack
                # This prevents wasting GPU nodes on CPU jobs
                avail_cpu = node.available.cpu_milli / max(node.allocatable.cpu_milli, 1)
                avail_mem = node.available.memory_mi  / max(node.allocatable.memory_mi, 1)
                core_score = (avail_cpu * 50 + avail_mem * 50)
                # Strong bonus for CPU-only nodes (no GPU waste)
                if node.allocatable.gpu_count == 0:
                    core_score *= 1.5

            # Apply modifiers
            score = (
                core_score
                * _tier_penalty(node, pod)
                * _anti_fragment_bonus(node, pod)
                * _ceiling_penalty(node)
            )

            node_scores.append((node, score))

        # ── Phase 3: Select ──────────────────────────────────────────────
        node_scores.sort(key=lambda x: -x[1])
        chosen_node, best_score = node_scores[0]

        # Bind
        self.cluster.nodes[chosen_node.name].allocate(pod)

        return SchedulingResult(
            pod_name=pod.name,
            node_name=chosen_node.name,
            scheduled=True,
            score=min(100.0, best_score),
            reason="scheduled",
        )
