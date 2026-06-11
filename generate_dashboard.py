import json
import os

def generate():
    with open('/home/smnaim/own-sim/results.json', 'r') as f:
        results_json = f.read()

    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kubernetes GPU Scheduler Simulator Results</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=Inter:wght@300;400&family=JetBrains+Mono&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        :root {
            --bg-base: #09090b;
            --bg-surface: rgba(24, 24, 27, 0.65);
            --bg-surface-hover: rgba(39, 39, 42, 0.8);
            --text-main: #f8fafc;
            --text-muted: #a1a1aa;
            --accent-primary: #38bdf8;
            --accent-secondary: #c084fc;
            --k8s-color: #3b82f6;
            --opt-color: #10b981;
            --danger: #f43f5e;
            --font-sans: 'Outfit', sans-serif;
            --font-body: 'Inter', sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }

        * { box-sizing: border-box; }

        body {
            background-color: var(--bg-base);
            background-image: 
                radial-gradient(circle at 15% 50%, rgba(56, 189, 248, 0.12), transparent 25%),
                radial-gradient(circle at 85% 30%, rgba(192, 132, 252, 0.12), transparent 25%),
                radial-gradient(circle at 50% 100%, rgba(16, 185, 129, 0.08), transparent 30%);
            background-attachment: fixed;
            color: var(--text-main);
            font-family: var(--font-sans);
            margin: 0;
            padding: 0;
            line-height: 1.6;
            overflow-x: hidden;
        }

        .container {
            max-width: 1440px;
            margin: 0 auto;
            padding: 3rem 2rem;
            position: relative;
            z-index: 1;
        }

        header {
            text-align: center;
            margin-bottom: 4rem;
            animation: slideDown 0.8s cubic-bezier(0.16, 1, 0.3, 1);
        }

        h1 {
            font-size: 3rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            background: linear-gradient(135deg, #fff 0%, #a1a1aa 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
            line-height: 1.2;
        }

        .subtitle {
            color: var(--text-muted);
            font-size: 1.2rem;
            font-weight: 300;
            max-width: 600px;
            margin: 0 auto;
        }

        .highlight-text {
            background: linear-gradient(to right, var(--accent-primary), var(--accent-secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 600;
        }

        /* Dashboard Grid */
        .dashboard-grid {
            display: grid;
            grid-template-columns: repeat(12, 1fr);
            gap: 1.5rem;
            margin-bottom: 3rem;
        }

        .card {
            background-color: var(--bg-surface);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border-radius: 1.25rem;
            padding: 1.5rem;
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.05);
            transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.3s ease, border-color 0.3s ease;
            animation: fadeIn 0.8s ease backwards;
        }

        .card:hover {
            transform: translateY(-4px);
            box-shadow: 0 12px 40px rgba(0, 0, 0, 0.3);
            border-color: rgba(255, 255, 255, 0.1);
        }

        /* Staggered card animations */
        .card:nth-child(1) { animation-delay: 0.1s; }
        .card:nth-child(2) { animation-delay: 0.2s; }
        .card:nth-child(3) { animation-delay: 0.3s; }
        .card:nth-child(4) { animation-delay: 0.4s; }
        .card:nth-child(5) { animation-delay: 0.5s; }
        .card:nth-child(6) { animation-delay: 0.6s; }
        .card:nth-child(7) { animation-delay: 0.7s; }

        /* Counters */
        .metric-card {
            grid-column: span 3;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            position: relative;
            overflow: hidden;
        }
        
        /* Subtle glow line at top of metric cards */
        .metric-card::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 2px;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
            opacity: 0.5;
        }

        @media (max-width: 1024px) {
            .metric-card { grid-column: span 6; }
        }

        .metric-title {
            font-size: 0.85rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin-bottom: 1.5rem;
            font-weight: 600;
        }

        .metric-comparison {
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            gap: 1rem;
        }

        .metric-value-container {
            display: flex;
            flex-direction: column;
            flex: 1;
        }

        .metric-value-container.k8s .metric-label { color: var(--k8s-color); }
        .metric-value-container.opt .metric-label { color: var(--opt-color); }

        .metric-label {
            font-size: 0.75rem;
            font-weight: 600;
            margin-bottom: 0.25rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            opacity: 0.9;
        }

        .metric-val {
            font-size: 2.25rem;
            font-weight: 800;
            font-family: var(--font-mono);
            line-height: 1;
            text-shadow: 0 0 20px rgba(255,255,255,0.1);
        }

        .metric-delta {
            font-size: 0.85rem;
            padding: 0.3rem 0.6rem;
            border-radius: 0.5rem;
            font-weight: 600;
            white-space: nowrap;
            backdrop-filter: blur(4px);
            align-self: center;
        }

        .delta-positive { background-color: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.2); }
        .delta-negative { background-color: rgba(244, 63, 94, 0.15); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.2); }
        .delta-neutral { background-color: rgba(161, 161, 170, 0.15); color: #e4e4e7; border: 1px solid rgba(161, 161, 170, 0.2); }

        /* Methodology */
        .methodology-card {
            grid-column: span 12;
            padding: 2.5rem;
        }

        .methodology-content {
            display: flex;
            gap: 3rem;
            align-items: center;
        }
        
        @media (max-width: 1024px) {
            .methodology-content { flex-direction: column; }
        }

        .methodology-text {
            flex: 1;
        }

        .methodology-diagram {
            flex: 1.2;
            background: rgba(0, 0, 0, 0.2);
            padding: 2rem;
            border-radius: 1rem;
            overflow-x: auto;
            border: 1px solid rgba(255, 255, 255, 0.03);
            box-shadow: inset 0 0 20px rgba(0,0,0,0.5);
        }

        /* Charts */
        .chart-card {
            grid-column: span 6;
            height: 450px;
            display: flex;
            flex-direction: column;
        }
        
        @media (max-width: 1024px) {
            .chart-card { grid-column: span 12; }
        }

        .chart-container {
            position: relative;
            flex-grow: 1;
            width: 100%;
            margin-top: 1rem;
        }

        /* Heatmap */
        .heatmap-card {
            grid-column: span 12;
        }

        .heatmap-controls {
            display: flex;
            gap: 1rem;
            margin-bottom: 1.5rem;
            background: rgba(0,0,0,0.2);
            padding: 0.5rem;
            border-radius: 0.75rem;
            display: inline-flex;
            border: 1px solid rgba(255,255,255,0.05);
        }

        .btn {
            background-color: transparent;
            color: var(--text-muted);
            border: none;
            padding: 0.6rem 1.2rem;
            border-radius: 0.5rem;
            cursor: pointer;
            font-family: var(--font-sans);
            font-weight: 600;
            transition: all 0.2s ease;
        }

        .btn:hover {
            color: var(--text-main);
            background-color: rgba(255,255,255,0.05);
        }

        .btn.active {
            background-color: var(--accent-primary);
            color: #fff;
            box-shadow: 0 4px 15px rgba(56, 189, 248, 0.4);
        }

        .heatmap-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(14px, 1fr));
            gap: 3px;
            margin-top: 1.5rem;
            padding: 1rem;
            background: rgba(0,0,0,0.2);
            border-radius: 0.75rem;
            border: 1px solid rgba(255,255,255,0.02);
        }

        .node-cell {
            aspect-ratio: 1;
            border-radius: 3px;
            cursor: pointer;
            position: relative;
            transition: transform 0.1s ease, filter 0.2s ease;
        }
        
        .node-cell:hover {
            transform: scale(1.3);
            z-index: 2;
            filter: brightness(1.2);
            box-shadow: 0 0 10px rgba(0,0,0,0.5);
        }

        .tooltip {
            position: absolute;
            background: rgba(9, 9, 11, 0.95);
            border: 1px solid rgba(255, 255, 255, 0.1);
            padding: 1rem;
            border-radius: 0.75rem;
            font-size: 0.8rem;
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.2s ease, transform 0.2s ease;
            transform: translateY(10px);
            z-index: 10;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
            width: 220px;
            font-family: var(--font-mono);
            backdrop-filter: blur(8px);
        }

        .node-cell:hover .tooltip {
            opacity: 1;
            transform: translateY(0);
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        @keyframes slideDown {
            from { opacity: 0; transform: translateY(-30px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        /* Research Paper Style elements - Modernized for Dark Theme */
        .paper-style {
            background: linear-gradient(145deg, rgba(30, 41, 59, 0.4) 0%, rgba(15, 23, 42, 0.6) 100%);
            border-left: 4px solid var(--accent-primary);
        }
        
        .paper-style h2 {
            font-size: 1.75rem;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            padding-bottom: 0.75rem;
            color: #fff;
            margin-top: 0;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .paper-style h2::before {
            content: '';
            display: inline-block;
            width: 8px; height: 8px;
            background: var(--accent-primary);
            border-radius: 50%;
            box-shadow: 0 0 10px var(--accent-primary);
        }
        
        .paper-style p, .paper-style li {
            font-family: var(--font-body);
            color: var(--text-muted);
            font-size: 0.95rem;
            line-height: 1.7;
            margin-bottom: 1.25rem;
        }
        
        .paper-style strong {
            color: #e2e8f0;
            font-family: var(--font-sans);
            font-weight: 600;
        }
        
        .paper-style code {
            font-family: var(--font-mono);
            background: rgba(255,255,255,0.1);
            padding: 0.2rem 0.4rem;
            border-radius: 0.25rem;
            font-size: 0.85em;
            color: var(--accent-secondary);
        }
        
        .paper-style .mermaid {
            background: transparent;
        }
    </style>
</head>
<body>

<div class="container">
    <header>
        <h1>Kubernetes <span class="highlight-text">GPU Scheduler</span> Simulator</h1>
        <div class="subtitle">Performance Analysis & Optimization on Alibaba OpenB Dataset (1,213 GPU Nodes)</div>
    </header>

    <div class="dashboard-grid">
        
        <!-- Metrics Row -->
        <div class="card metric-card">
            <div class="metric-title">Active Nodes Used <span style="text-transform:none;opacity:0.6;font-weight:400;">(Lower = Better)</span></div>
            <div class="metric-comparison">
                <div class="metric-value-container k8s">
                    <span class="metric-label">K8S Default</span>
                    <span class="metric-val counter" data-target="active_nodes_k8s">0</span>
                </div>
                <div class="metric-value-container opt">
                    <span class="metric-label">Optimized</span>
                    <span class="metric-val counter" data-target="active_nodes_opt">0</span>
                </div>
                <div id="delta_nodes" class="metric-delta delta-neutral">-</div>
            </div>
        </div>

        <div class="card metric-card">
            <div class="metric-title">Fragmentation Rate <span style="text-transform:none;opacity:0.6;font-weight:400;">(Lower = Better)</span></div>
            <div class="metric-comparison">
                <div class="metric-value-container k8s">
                    <span class="metric-label">K8S Default</span>
                    <span class="metric-val counter" data-target="frag_k8s" data-decimals="1" data-suffix="%">0%</span>
                </div>
                <div class="metric-value-container opt">
                    <span class="metric-label">Optimized</span>
                    <span class="metric-val counter" data-target="frag_opt" data-decimals="1" data-suffix="%">0%</span>
                </div>
                <div id="delta_frag" class="metric-delta delta-neutral">-</div>
            </div>
        </div>

        <div class="card metric-card">
            <div class="metric-title">Load Balance Score <span style="text-transform:none;opacity:0.6;font-weight:400;">(Lower = Packed)</span></div>
            <div class="metric-comparison">
                <div class="metric-value-container k8s">
                    <span class="metric-label">K8S Default</span>
                    <span class="metric-val counter" data-target="load_k8s" data-decimals="1">0</span>
                </div>
                <div class="metric-value-container opt">
                    <span class="metric-label">Optimized</span>
                    <span class="metric-val counter" data-target="load_opt" data-decimals="1">0</span>
                </div>
                <div id="delta_load" class="metric-delta delta-neutral">-</div>
            </div>
        </div>

        <div class="card metric-card">
            <div class="metric-title">Scheduling Time <span style="text-transform:none;opacity:0.6;font-weight:400;">(ms)</span></div>
            <div class="metric-comparison">
                <div class="metric-value-container k8s">
                    <span class="metric-label">K8S Default</span>
                    <span class="metric-val counter" data-target="time_k8s" data-decimals="1">0</span>
                </div>
                <div class="metric-value-container opt">
                    <span class="metric-label">Optimized</span>
                    <span class="metric-val counter" data-target="time_opt" data-decimals="1">0</span>
                </div>
                <div id="delta_time" class="metric-delta delta-neutral">-</div>
            </div>
        </div>

        <!-- Methodology Section -->
        <div class="card methodology-card paper-style">
            <h2>Methodology: GPU-Aware Bin-Packing Scheduler</h2>
            <div class="methodology-content">
                <div class="methodology-text">
                    <p>
                        <strong>Abstract:</strong> Traditional Kubernetes scheduling relies heavily on the <code>LeastAllocated</code> and <code>BalancedAllocation</code> scoring functions, which distribute workloads evenly across nodes to minimize resource contention. While effective for CPU and memory, this "spreading" strategy leads to severe resource fragmentation in heterogeneous GPU clusters.
                    </p>
                    <p>
                        <strong>Proposed Algorithm:</strong> We introduce an optimized, multi-dimensional bin-packing scheduler designed specifically for GPU workloads. The algorithm ranks nodes based on a composite score:
                    </p>
                    <ul>
                        <li><strong>GPU Tier Matching:</strong> Penalizes placing workloads requesting lower-tier GPUs (e.g., T4) on nodes equipped with premium accelerators (e.g., A10, V100M32) unless absolutely necessary.</li>
                        <li><strong>GPU-Weighted Bin-Packing:</strong> Concentrates workloads onto fewer nodes to preserve contiguous blocks of unallocated GPUs, mitigating the "stranded capacity" problem.</li>
                        <li><strong>Anti-Fragmentation Lookahead:</strong> Applies heuristics for large requests (&ge; 4 GPUs) to avoid leaving nodes with odd numbers of remaining GPUs.</li>
                    </ul>
                </div>
                <div class="methodology-diagram">
                    <div class="mermaid">
                        graph TD
                            A("Incoming Pod") --> B{"Is GPU Workload?"}
                            B -- No --> C["Spread Allocation CPU/Mem"]
                            B -- Yes --> D["Filter Feasible Nodes"]
                            D --> E["Score Nodes Phase"]
                            E --> F("Compute Bin-Pack Score")
                            E --> G("Apply GPU Tier Penalty")
                            E --> H("Anti-Fragmentation Bonus")
                            E --> I("Ceiling Penalty > 85%")
                            F --> J["Final Node Score"]
                            G --> J
                            H --> J
                            I --> J
                            J --> K{"Select Highest Score"}
                            K --> L("Bind to Node")
                            C --> L
                            
                            style A fill:#1e293b,stroke:#cbd5e1,stroke-width:2px,color:#fff
                            style B fill:#0c4a6e,stroke:#38bdf8,stroke-width:2px,color:#fff
                            style C fill:#334155,stroke:#475569,stroke-width:2px,color:#f8fafc
                            style D fill:#713f12,stroke:#eab308,stroke-width:2px,color:#fff
                            style E fill:#713f12,stroke:#eab308,stroke-width:2px,color:#fff
                            style F fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#fff
                            style G fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#fff
                            style H fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#fff
                            style I fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#fff
                            style J fill:#4c1d95,stroke:#a855f7,stroke-width:2px,color:#fff
                            style K fill:#0c4a6e,stroke:#38bdf8,stroke-width:2px,color:#fff
                            style L fill:#1e293b,stroke:#cbd5e1,stroke-width:2px,color:#fff
                    </div>
                </div>
            </div>
        </div>

        <!-- Charts -->
        <div class="card chart-card">
            <div class="metric-title">Resource Utilization Comparison</div>
            <div class="chart-container">
                <canvas id="utilizationChart"></canvas>
            </div>
        </div>

        <div class="card chart-card">
            <div class="metric-title">Scheduling Performance Metrics</div>
            <div class="chart-container">
                <canvas id="performanceChart"></canvas>
            </div>
        </div>

        <!-- Heatmap -->
        <div class="card heatmap-card">
            <div class="metric-title">Cluster Utilization Heatmap <span style="opacity:0.5;font-weight:400;text-transform:none;">(1,213 Nodes)</span></div>
            <div class="heatmap-controls">
                <button class="btn active" id="btn-k8s">K8S Default Distribution</button>
                <button class="btn" id="btn-opt">Optimized Packing Distribution</button>
            </div>
            <div style="margin-bottom: 0.5rem;"><small id="heatmap-desc" style="color:var(--text-muted);font-family:var(--font-body);padding:0.5rem;background:rgba(255,255,255,0.03);border-radius:0.5rem;display:inline-block;border:1px solid rgba(255,255,255,0.05);">K8S Default: Workloads are spread out (Load Balancing), leading to many nodes with low utilization and fragmentation.</small></div>
            <div class="heatmap-grid" id="heatmap"></div>
        </div>

    </div>
</div>

<script>
    mermaid.initialize({ startOnLoad: true, theme: 'default' });

    // Data injected via python script
    const data = __JSON_DATA_PLACEHOLDER__;

    // --- Counter Animation ---
    function animateValue(obj, start, end, duration, decimals = 0, suffix = "") {
        let startTimestamp = null;
        const step = (timestamp) => {
            if (!startTimestamp) startTimestamp = timestamp;
            const progress = Math.min((timestamp - startTimestamp) / duration, 1);
            const easeProgress = 1 - Math.pow(1 - progress, 4);
            const current = (start + easeProgress * (end - start)).toFixed(decimals);
            obj.innerHTML = current + suffix;
            if (progress < 1) {
                window.requestAnimationFrame(step);
            } else {
                obj.innerHTML = end.toFixed(decimals) + suffix;
            }
        };
        window.requestAnimationFrame(step);
    }

    function initCounters() {
        const k8s = data.schedulers.kubernetes;
        const opt = data.schedulers.optimized;

        const maps = {
            'active_nodes_k8s': { val: k8s.active_nodes },
            'active_nodes_opt': { val: opt.active_nodes },
            'frag_k8s': { val: k8s.fragmentation_rate },
            'frag_opt': { val: opt.fragmentation_rate },
            'load_k8s': { val: k8s.load_balance_score },
            'load_opt': { val: opt.load_balance_score },
            'time_k8s': { val: k8s.elapsed_ms },
            'time_opt': { val: opt.elapsed_ms }
        };

        document.querySelectorAll('.counter').forEach(el => {
            const targetKey = el.getAttribute('data-target');
            const targetVal = maps[targetKey].val;
            const decimals = parseInt(el.getAttribute('data-decimals') || '0');
            const suffix = el.getAttribute('data-suffix') || '';
            animateValue(el, 0, targetVal, 2000, decimals, suffix);
        });

        // Set deltas
        const setDelta = (id, k8sVal, optVal, lowerIsBetter, unit="") => {
            const diff = optVal - k8sVal;
            const el = document.getElementById(id);
            if (diff === 0) {
                el.innerText = `~ 0.0${unit}`;
                el.className = 'metric-delta delta-neutral';
            } else {
                const sign = diff > 0 ? '+' : '';
                el.innerText = `${sign}${diff.toFixed(1)}${unit}`;
                if ((diff < 0 && lowerIsBetter) || (diff > 0 && !lowerIsBetter)) {
                    el.className = 'metric-delta delta-positive';
                } else {
                    el.className = 'metric-delta delta-negative';
                }
            }
        };

        setDelta('delta_nodes', k8s.active_nodes, opt.active_nodes, true);
        setDelta('delta_frag', k8s.fragmentation_rate, opt.fragmentation_rate, true, '%');
        setDelta('delta_load', k8s.load_balance_score, opt.load_balance_score, true);
        setDelta('delta_time', k8s.elapsed_ms, opt.elapsed_ms, true, 'ms');
    }

    // --- Charts ---
    function initCharts() {
        const k8s = data.schedulers.kubernetes;
        const opt = data.schedulers.optimized;

        const colorK8s = 'rgba(50, 108, 229, 0.9)';
        const colorOpt = 'rgba(16, 185, 129, 0.9)';

        Chart.defaults.color = '#cbd5e1';
        Chart.defaults.font.family = "'Inter', sans-serif";

        // Utilization Chart
        const ctxUtil = document.getElementById('utilizationChart').getContext('2d');
        new Chart(ctxUtil, {
            type: 'bar',
            data: {
                labels: ['GPU Utilization (%)', 'CPU Utilization (%)', 'Mem Utilization (%)'],
                datasets: [
                    {
                        label: 'K8S Default',
                        data: [k8s.gpu_utilization, k8s.cpu_utilization, k8s.memory_utilization],
                        backgroundColor: colorK8s,
                        borderRadius: 4
                    },
                    {
                        label: 'Optimized',
                        data: [opt.gpu_utilization, opt.cpu_utilization, opt.memory_utilization],
                        backgroundColor: colorOpt,
                        borderRadius: 4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: { y: { beginAtZero: true, max: 100, grid: { color: 'rgba(255,255,255,0.05)' } }, x: { grid: { display: false } } },
                plugins: { legend: { position: 'top' } }
            }
        });

        // Performance Chart
        const ctxPerf = document.getElementById('performanceChart').getContext('2d');
        new Chart(ctxPerf, {
            type: 'bar',
            data: {
                labels: ['Active Nodes Used', 'Load Balance Score', 'Fragmentation Rate (%)'],
                datasets: [
                    {
                        label: 'K8S Default',
                        data: [k8s.active_nodes, k8s.load_balance_score, k8s.fragmentation_rate],
                        backgroundColor: colorK8s,
                        borderRadius: 4
                    },
                    {
                        label: 'Optimized',
                        data: [opt.active_nodes, opt.load_balance_score, opt.fragmentation_rate],
                        backgroundColor: colorOpt,
                        borderRadius: 4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: { y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' } }, x: { grid: { display: false } } },
                plugins: { legend: { position: 'top' } }
            }
        });
    }

    // --- Heatmap ---
    function renderHeatmap(datasetType) {
        const container = document.getElementById('heatmap');
        container.innerHTML = '';
        const nodes = data.node_utils[datasetType];

        // Sort nodes by GPU util, then CPU, then Mem, for visual appeal
        const sortedNodes = [...nodes].sort((a, b) => b.gpu_util - a.gpu_util || b.cpu_util - a.cpu_util);

        sortedNodes.forEach(node => {
            const cell = document.createElement('div');
            cell.className = 'node-cell';
            
            // Color logic: Bright blue for GPU util
            let color = '#1e293b'; // default idle
            if (node.pod_count > 0) {
                if (node.gpu_util > 0) {
                    const lightness = 25 + (node.gpu_util * 0.4); 
                    color = `hsl(217, 90%, ${lightness}%)`;
                } else {
                    const lightness = 25 + (node.cpu_util * 0.4);
                    color = `hsl(150, 60%, ${lightness}%)`;
                }
            }
            
            cell.style.backgroundColor = color;

            // Tooltip
            const tooltip = document.createElement('div');
            tooltip.className = 'tooltip';
            tooltip.innerHTML = `
                <div style="font-weight:bold;color:#fff;border-bottom:1px solid #334155;margin-bottom:4px;padding-bottom:4px;">${node.name}</div>
                <div>Model: <span style="color:var(--accent-primary)">${node.gpu_model}</span></div>
                <div>Pods: ${node.pod_count}</div>
                <div>GPU Util: ${node.gpu_util}%</div>
                <div>CPU Util: ${node.cpu_util}%</div>
                <div>Mem Util: ${node.mem_util}%</div>
            `;
            
            cell.addEventListener('mouseenter', (e) => {
                const rect = cell.getBoundingClientRect();
                const ttWidth = 200;
                let leftPos = rect.width + 5;
                if (rect.left + ttWidth > window.innerWidth) {
                    leftPos = -ttWidth - 5;
                }
                tooltip.style.left = leftPos + 'px';
                tooltip.style.top = '0px';
                tooltip.style.zIndex = 1000;
            });

            cell.appendChild(tooltip);
            container.appendChild(cell);
        });
    }

    document.getElementById('btn-k8s').addEventListener('click', (e) => {
        document.getElementById('btn-k8s').classList.add('active');
        document.getElementById('btn-opt').classList.remove('active');
        document.getElementById('heatmap-desc').innerText = "K8S Default: Workloads are spread out (Load Balancing), leading to many nodes with low utilization and fragmentation.";
        renderHeatmap('kubernetes');
    });

    document.getElementById('btn-opt').addEventListener('click', (e) => {
        document.getElementById('btn-opt').classList.add('active');
        document.getElementById('btn-k8s').classList.remove('active');
        document.getElementById('heatmap-desc').innerText = "Optimized: Workloads are densely packed (Bin-Packing), leaving more nodes completely idle for future large jobs.";
        renderHeatmap('optimized');
    });

    // --- Init ---
    window.addEventListener('DOMContentLoaded', () => {
        initCounters();
        initCharts();
        renderHeatmap('kubernetes');
    });

</script>
</body>
</html>"""

    final_html = html_template.replace('__JSON_DATA_PLACEHOLDER__', results_json)

    with open('/home/smnaim/own-sim/dashboard.html', 'w') as f:
        f.write(final_html)
        
    print("Successfully generated dashboard.html with injected JSON.")

if __name__ == '__main__':
    generate()
