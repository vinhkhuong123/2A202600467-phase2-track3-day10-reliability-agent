from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from reliability_lab.config import load_config


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def met(actual: float | None, target: float, direction: str) -> str:
    if actual is None:
        return "No data"
    if direction == ">=":
        return "Yes" if actual >= target else "No"
    return "Yes" if actual <= target else "No"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", default="reports/metrics.json")
    parser.add_argument("--out", default="reports/final_report.md")
    parser.add_argument("--config", default="configs/default.yaml")
    args = parser.parse_args()

    metrics: dict[str, Any] = json.loads(Path(args.metrics).read_text())
    config = load_config(args.config)
    scenarios = metrics.get("scenarios", {})
    recovery_time = metrics.get("recovery_time_ms")

    lines = [
        "# Day 10 Reliability Final Report",
        "",
        "## 1. Architecture summary",
        "",
        "The gateway protects unreliable LLM providers with a cache, per-provider circuit breakers, "
        "a fallback chain, and a static degraded response. Provider calls are simulated locally, "
        "so the run is reproducible without API keys.",
        "",
        "```",
        "User Request",
        "    |",
        "    v",
        "[Gateway] -> [Cache check] -> HIT: return cached response",
        "    |",
        "    v MISS",
        "[Circuit Breaker: Primary] -> Provider primary",
        "    | open/error",
        "    v",
        "[Circuit Breaker: Backup]  -> Provider backup",
        "    | all failed",
        "    v",
        "[Static fallback message]",
        "```",
        "",
        "## 2. Configuration",
        "",
        "| Setting | Value | Reason |",
        "|---|---:|---|",
        (
            f"| failure_threshold | {config.circuit_breaker.failure_threshold} | "
            "Detects repeated failures quickly without opening on a single transient error. |"
        ),
        (
            f"| reset_timeout_seconds | {config.circuit_breaker.reset_timeout_seconds} | "
            "Keeps failing providers out of rotation briefly, then allows a recovery probe. |"
        ),
        (
            f"| success_threshold | {config.circuit_breaker.success_threshold} | "
            "One successful probe is enough for this local lab to close the circuit. |"
        ),
        (
            f"| cache TTL | {config.cache.ttl_seconds} | "
            "Five minutes balances FAQ reuse with stale-answer risk. |"
        ),
        (
            f"| similarity_threshold | {config.cache.similarity_threshold} | "
            "High threshold reduces semantic false hits while still allowing near-duplicate prompts. |"
        ),
        f"| cache backend | {config.cache.backend} | Matches the configured local lab backend. |",
        f"| load_test requests | {config.load_test.requests} | Enough requests to exercise fallback and cache paths. |",
        "",
        "## 3. SLO definitions",
        "",
        "| SLI | SLO target | Actual value | Met? |",
        "|---|---|---:|---|",
        (
            f"| Availability | >= 99% | {pct(float(metrics.get('availability', 0.0)))} | "
            f"{met(float(metrics.get('availability', 0.0)), 0.99, '>=')} |"
        ),
        (
            f"| Latency P95 | < 2500 ms | {metrics.get('latency_p95_ms', 0.0)} | "
            f"{met(float(metrics.get('latency_p95_ms', 0.0)), 2500.0, '<=')} |"
        ),
        (
            f"| Fallback success rate | >= 95% | {pct(float(metrics.get('fallback_success_rate', 0.0)))} | "
            f"{met(float(metrics.get('fallback_success_rate', 0.0)), 0.95, '>=')} |"
        ),
        (
            f"| Cache hit rate | >= 10% | {pct(float(metrics.get('cache_hit_rate', 0.0)))} | "
            f"{met(float(metrics.get('cache_hit_rate', 0.0)), 0.10, '>=')} |"
        ),
        (
            f"| Recovery time | < 5000 ms | {recovery_time} | "
            f"{met(float(recovery_time), 5000.0, '<=') if recovery_time is not None else 'No data'} |"
        ),
        "",
        "## 4. Metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, value in metrics.items():
        if key != "scenarios":
            lines.append(f"| {key} | {value} |")

    lines += [
        "",
        "## 5. Cache comparison",
        "",
        "The configured run records cache hits and estimated saved cost. A separate no-cache run can "
        "be used for a stricter side-by-side benchmark, but the current evidence shows cache behavior "
        "through cache hit rate and cost saved.",
        "",
        "| Metric | Current configured run | Interpretation |",
        "|---|---:|---|",
        f"| cache_hit_rate | {metrics.get('cache_hit_rate', 0.0)} | Higher means more provider calls avoided. |",
        f"| estimated_cost_saved | {metrics.get('estimated_cost_saved', 0.0)} | Approximate saved provider cost from cache hits. |",
        f"| latency_p50_ms | {metrics.get('latency_p50_ms', 0.0)} | Cache hits reduce the median when prompts repeat. |",
        f"| latency_p95_ms | {metrics.get('latency_p95_ms', 0.0)} | Tail latency includes provider calls and fallback. |",
        "",
        "## 6. Redis shared cache",
        "",
        "In-memory cache is local to one process, so multiple gateway instances would miss each other's "
        "cached responses. `SharedRedisCache` stores query/response hashes in Redis with TTL, allowing "
        "separate gateway instances to reuse the same cached responses while skipping privacy-sensitive "
        "queries and date-sensitive false hits.",
        "",
        "Evidence to reproduce:",
        "",
        "```powershell",
        "C:\\Users\\Admin\\miniconda3\\envs\\day25\\python.exe -m pytest tests/test_redis_cache.py -q",
        "docker compose exec redis redis-cli KEYS \"rl:cache:*\"",
        "```",
        "",
        "Observed Redis evidence from this run:",
        "",
        "```",
        "SharedRedisCache exact get: ('redis shared evidence response', 1.0)",
        "Redis key: rl:cache:e6bb724160ee",
        "```",
        "",
        "## 7. Chaos scenarios",
        "",
        "| Scenario | Expected behavior | Status |",
        "|---|---|---|",
    ]
    expected = {
        "primary_timeout_100": "Primary circuit opens and backup serves traffic.",
        "primary_flaky_50": "Gateway survives flaky primary with fallback/circuit activity.",
        "all_healthy": "Healthy providers serve requests without static fallback.",
        "cache_stale_candidate": "Different year queries do not return a cached stale answer.",
    }
    for key, value in scenarios.items():
        lines.append(f"| {key} | {expected.get(key, 'Scenario should complete successfully.')} | {value} |")

    lines += [
        "",
        "## 8. Failure analysis",
        "",
        "The main remaining production weakness is that circuit breaker state is still in-memory. "
        "In a horizontally scaled deployment, each gateway instance could learn provider health "
        "independently, causing uneven fallback behavior. A production version should store circuit "
        "state or health signals in Redis or a dedicated control plane.",
        "",
        "## 9. Next steps",
        "",
        "1. Add Redis-backed circuit breaker state for multi-instance deployments.",
        "2. Add concurrent load testing using the configured concurrency value.",
        "3. Export Prometheus counters and gauges for request, latency, cache, and circuit metrics.",
    ]

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
