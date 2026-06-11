"""
run_comparison.py — Run both schedulers and produce comparison results + dashboard data.

Usage:
    python run_comparison.py
"""

import json
import os
import sys
import time
from simulator import load_cluster, generate_workload, SimulationMetrics
from k8s_scheduler import KubernetesScheduler
from optimized_scheduler import OptimizedScheduler

YAML_PATH  = os.path.join(os.path.dirname(__file__), "openb_node_list_gpu_node.yaml")
N_PODS     = 500
RANDOM_SEED = 42


def run_scheduler(scheduler_class, cluster_snapshot, pods, name):
    print(f"\n[Runner] Starting: {name}")
    t0 = time.perf_counter()
    sched = scheduler_class(cluster_snapshot)
    results = sched.schedule(pods)
    elapsed = time.perf_counter() - t0
    metrics = SimulationMetrics(name, cluster_snapshot, results, pods)
    print(metrics.summary())
    print(f"  ⏱  Scheduling time: {elapsed*1000:.1f} ms")
    metrics.elapsed_ms = elapsed * 1000
    return metrics, results


def main():
    print("=" * 60)
    print("  Kubernetes GPU Scheduler Comparison Simulator")
    print("  Dataset: Alibaba OpenB GPU Node List")
    print("=" * 60)

    # Load cluster
    cluster = load_cluster(YAML_PATH)

    # Generate pods (same seed → identical workload for both schedulers)
    pods = generate_workload(n_pods=N_PODS, seed=RANDOM_SEED)
    gpu_pods   = sum(1 for p in pods if p.is_gpu_pod())
    cpu_only   = N_PODS - gpu_pods
    print(f"\n[Workload] {N_PODS} pods generated: {gpu_pods} GPU pods, {cpu_only} CPU-only pods")

    # Run Kubernetes default scheduler
    k8s_cluster = cluster.snapshot()
    k8s_metrics, k8s_results = run_scheduler(
        KubernetesScheduler, k8s_cluster, pods,
        "Kubernetes Default Scheduler"
    )

    # Run optimized scheduler
    opt_cluster = cluster.snapshot()
    opt_metrics, opt_results = run_scheduler(
        OptimizedScheduler, opt_cluster, pods,
        "Optimized GPU-Aware Scheduler"
    )

    # Build comparison data
    comparison = {
        "workload": {
            "total_pods": N_PODS,
            "gpu_pods":   gpu_pods,
            "cpu_pods":   cpu_only,
            "seed":       RANDOM_SEED,
        },
        "schedulers": {
            "kubernetes": metrics_to_dict(k8s_metrics),
            "optimized":  metrics_to_dict(opt_metrics),
        },
        "node_utils": {
            "kubernetes": k8s_metrics.node_utils,
            "optimized":  opt_metrics.node_utils,
        },
        "improvements": compute_improvements(k8s_metrics, opt_metrics),
    }

    out_path = os.path.join(os.path.dirname(__file__), "results.json")
    with open(out_path, "w") as f:
        json.dump(comparison, f, indent=2)

    print(f"\n[Done] Results saved → {out_path}")
    print_improvement_table(k8s_metrics, opt_metrics)
    print(f"\n[Dashboard] Open: file://{os.path.abspath(os.path.join(os.path.dirname(__file__), 'dashboard.html'))}")


def metrics_to_dict(m: SimulationMetrics) -> dict:
    return {
        "name":                  m.scheduler_name,
        "total_pods":            m.total_pods,
        "scheduled_count":       m.scheduled_count,
        "unscheduled_count":     m.unscheduled_count,
        "schedule_rate":         round(m.schedule_rate, 2),
        "gpu_utilization":       round(m.gpu_utilization, 2),
        "cpu_utilization":       round(m.cpu_utilization, 2),
        "memory_utilization":    round(m.memory_utilization, 2),
        "fragmentation_rate":    round(m.fragmentation_rate, 2),
        "load_balance_score":    round(m.load_balance_score, 2),
        "avg_score":             round(m.avg_score, 2),
        "active_nodes":          m.active_nodes,
        "total_nodes":           m.total_nodes,
        "gpu_pod_total":         m.gpu_pod_total,
        "gpu_pod_scheduled":     m.gpu_pod_scheduled,
        "gpu_pod_schedule_rate": round(m.gpu_pod_schedule_rate, 2),
        "elapsed_ms":            round(m.elapsed_ms, 1),
    }


def compute_improvements(k8s: SimulationMetrics, opt: SimulationMetrics) -> dict:
    def pct_diff(a, b):
        return round(b - a, 2)

    def ratio_diff(a, b):
        return round((b - a) / max(abs(a), 0.001) * 100, 1)

    return {
        "schedule_rate_delta":       pct_diff(k8s.schedule_rate, opt.schedule_rate),
        "gpu_utilization_delta":     pct_diff(k8s.gpu_utilization, opt.gpu_utilization),
        "cpu_utilization_delta":     pct_diff(k8s.cpu_utilization, opt.cpu_utilization),
        "memory_utilization_delta":  pct_diff(k8s.memory_utilization, opt.memory_utilization),
        "fragmentation_delta":       pct_diff(opt.fragmentation_rate, k8s.fragmentation_rate),  # lower is better
        "load_balance_delta":        pct_diff(k8s.load_balance_score, opt.load_balance_score),
        "gpu_pod_rate_delta":        pct_diff(k8s.gpu_pod_schedule_rate, opt.gpu_pod_schedule_rate),
    }


def print_improvement_table(k8s: SimulationMetrics, opt: SimulationMetrics):
    print("\n")
    print("┌─────────────────────────────────┬─────────────┬─────────────┬──────────────┐")
    print("│ Metric                          │ K8s Default │  Optimized  │ Improvement  │")
    print("├─────────────────────────────────┼─────────────┼─────────────┼──────────────┤")

    rows = [
        ("Pods Scheduled (%)",      k8s.schedule_rate,         opt.schedule_rate,         True,  "%"),
        ("GPU Pods Scheduled (%)",  k8s.gpu_pod_schedule_rate, opt.gpu_pod_schedule_rate, True,  "%"),
        ("GPU Utilization (%)",     k8s.gpu_utilization,       opt.gpu_utilization,       True,  "%"),
        ("CPU Utilization (%)",     k8s.cpu_utilization,       opt.cpu_utilization,       True,  "%"),
        ("Memory Utilization (%)",  k8s.memory_utilization,    opt.memory_utilization,    True,  "%"),
        ("Fragmentation Rate (%)",  k8s.fragmentation_rate,    opt.fragmentation_rate,    False, "%"),
        ("Load Balance Score",      k8s.load_balance_score,    opt.load_balance_score,    True,  ""),
        ("Active Nodes Used",       k8s.active_nodes,          opt.active_nodes,          False, ""),
    ]

    for name, k_val, o_val, higher_better, unit in rows:
        diff = o_val - k_val
        if higher_better:
            arrow = "▲" if diff > 0.1 else ("▼" if diff < -0.1 else "~")
            color = "✅" if diff > 0.1 else ("❌" if diff < -0.1 else "")
        else:
            arrow = "▼" if diff < -0.1 else ("▲" if diff > 0.1 else "~")
            color = "✅" if diff < -0.1 else ("❌" if diff > 0.1 else "")

        diff_str = f"{arrow} {abs(diff):+.1f}{unit} {color}"
        print(f"│ {name:<31} │  {k_val:>8.1f}{unit} │  {o_val:>8.1f}{unit} │ {diff_str:<12} │")

    print("└─────────────────────────────────┴─────────────┴─────────────┴──────────────┘")


if __name__ == "__main__":
    main()
