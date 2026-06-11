# Kubernetes GPU Scheduler Simulator — Implementation Plan

## Dataset
- **File**: `openb_node_list_gpu_node.yaml` — 1213 real Alibaba Cloud GPU nodes from the OpenB benchmark
- **GPU Models**: G2 (549), T4 (404), P100 (134), V100M16 (55), G3 (39), V100M32 (30), A10 (2)
- **Resources tracked**: `cpu (millicores)`, `memory (Mi)`, `gpu-count`, `gpu-milli`

---

## Components to Build

### 1. `simulator.py` — Core Simulator
- Parse all 1213 nodes from YAML
- Maintain cluster state: available resources per node
- Generate synthetic GPU workload (pods with cpu/mem/gpu demands)
- Provide plug-in interface for any scheduler

### 2. `k8s_scheduler.py` — Kubernetes Default Scheduler
Replicates official Kubernetes scheduling pipeline:
- **Filter phase**: NodeResourcesFit, NodeUnschedulable
- **Score phase**: LeastAllocated + BalancedAllocation + NodeAffinity
- Final: select highest scored node

### 3. `optimized_scheduler.py` — Our Custom GPU-Aware Scheduler
**Methodology:**
- **GPU Tiering**: Rank GPU models by compute power (A10 > G3 > V100M32 > V100M16 > G2 > T4 > P100) — match workload GPU demand to tier
- **Bin-Packing with GPU Affinity**: Pack pods onto fewest nodes while respecting GPU model fitness, reducing fragmentation
- **Weighted Multi-Resource Scoring**: Compute composite score balancing GPU utilization (weight 0.5), CPU utilization (weight 0.3), Memory utilization (weight 0.2) — GPU-heavy workloads get highest priority on GPU tier
- **Look-ahead Reservation**: For large GPU jobs (≥4 GPUs), check if fragmentation would block future placements
- **Tail-latency Prevention**: Avoid placing on nodes already at >85% utilization in any dimension

### 4. `run_comparison.py` — Orchestrator
- Run both schedulers on identical 500-pod workloads
- Collect metrics: scheduled %, GPU utilization %, fragmentation ratio, avg score, unscheduled count, bin packing efficiency

### 5. `dashboard.html` — Rich Visualization
- Side-by-side comparison charts (Chart.js)
- Node heatmap (utilization per node)
- Methodology explanation section
- Animated metric counters

---

## Metrics for Comparison

| Metric | Kubernetes Default | Our Scheduler |
|---|---|---|
| Pods Scheduled (%) | baseline | expected higher |
| GPU Utilization (%) | baseline | expected higher |
| CPU Fragmentation | baseline | expected lower |
| Memory Fragmentation | baseline | expected lower |
| Avg Node Load Balance Score | baseline | expected higher |
| GPU Tier Match Rate | baseline | expected higher |

