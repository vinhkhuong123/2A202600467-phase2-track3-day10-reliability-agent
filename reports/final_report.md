# Day 10 Reliability Final Report

## 1. Architecture summary

The gateway protects unreliable LLM providers with a cache, per-provider circuit breakers, a fallback chain, and a static degraded response. Provider calls are simulated locally, so the run is reproducible without API keys.

```
User Request
    |
    v
[Gateway] -> [Cache check] -> HIT: return cached response
    |
    v MISS
[Circuit Breaker: Primary] -> Provider primary
    | open/error
    v
[Circuit Breaker: Backup]  -> Provider backup
    | all failed
    v
[Static fallback message]
```

## 2. Configuration

| Setting | Value | Reason |
|---|---:|---|
| failure_threshold | 3 | Detects repeated failures quickly without opening on a single transient error. |
| reset_timeout_seconds | 2.0 | Keeps failing providers out of rotation briefly, then allows a recovery probe. |
| success_threshold | 1 | One successful probe is enough for this local lab to close the circuit. |
| cache TTL | 300 | Five minutes balances FAQ reuse with stale-answer risk. |
| similarity_threshold | 0.92 | High threshold reduces semantic false hits while still allowing near-duplicate prompts. |
| cache backend | memory | Matches the configured local lab backend. |
| load_test requests | 100 | Enough requests to exercise fallback and cache paths. |

## 3. SLO definitions

| SLI | SLO target | Actual value | Met? |
|---|---|---:|---|
| Availability | >= 99% | 99.00% | Yes |
| Latency P95 | < 2500 ms | 508.39 | Yes |
| Fallback success rate | >= 95% | 97.89% | Yes |
| Cache hit rate | >= 10% | 19.75% | Yes |
| Recovery time | < 5000 ms | 7023.9843527476 | No |

## 4. Metrics

| Metric | Value |
|---|---:|
| total_requests | 400 |
| availability | 0.99 |
| error_rate | 0.01 |
| latency_p50_ms | 236.56 |
| latency_p95_ms | 508.39 |
| latency_p99_ms | 534.17 |
| fallback_success_rate | 0.9789 |
| cache_hit_rate | 0.1975 |
| circuit_open_count | 23 |
| recovery_time_ms | 7023.9843527476 |
| estimated_cost | 0.142868 |
| estimated_cost_saved | 0.079 |

## 5. Cache comparison

The configured run records cache hits and estimated saved cost. A separate no-cache run can be used for a stricter side-by-side benchmark, but the current evidence shows cache behavior through cache hit rate and cost saved.

| Metric | Current configured run | Interpretation |
|---|---:|---|
| cache_hit_rate | 0.1975 | Higher means more provider calls avoided. |
| estimated_cost_saved | 0.079 | Approximate saved provider cost from cache hits. |
| latency_p50_ms | 236.56 | Cache hits reduce the median when prompts repeat. |
| latency_p95_ms | 508.39 | Tail latency includes provider calls and fallback. |

## 6. Redis shared cache

Bộ nhớ cache trong bộ nhớ chỉ hoạt động cục bộ trong một tiến trình, do đó nhiều phiên bản gateway sẽ bỏ lỡ các phản hồi được lưu trong cache của nhau. `SharedRedisCache` lưu trữ các mã băm truy vấn/phản hồi trong Redis với TTL, cho phép các phiên bản gateway riêng biệt sử dụng lại cùng một phản hồi được lưu trong cache trong khi bỏ qua các truy vấn nhạy cảm về quyền riêng tư và các kết quả trùng lặp sai liên quan đến ngày tháng.

Bằng chứng để tái tạo:

```powershell
C:\Users\Admin\miniconda3\envs\day25\python.exe -m pytest tests/test_redis_cache.py -q

docker compose exec redis redis-cli KEYS "rl:cache:*"

```
Bằng chứng Redis quan sát được từ lần chạy này:

```
SharedRedisCache exact get: ('redis shared evidence response', 1.0)
Khóa Redis: rl:cache:e6bb724160ee
```

## 7. Chaos scenarios

| Scenario | Expected behavior | Status |
|---|---|---|
| primary_timeout_100 | Primary circuit opens and backup serves traffic. | pass |
| primary_flaky_50 | Gateway survives flaky primary with fallback/circuit activity. | pass |
| all_healthy | Healthy providers serve requests without static fallback. | pass |
| cache_stale_candidate | Different year queries do not return a cached stale answer. | pass |

## 8. Failure analysis

Điểm yếu chính còn lại trong quá trình sản xuất là trạng thái của bộ ngắt mạch vẫn được lưu trữ trong bộ nhớ. Trong một triển khai mở rộng theo chiều ngang, mỗi phiên bản cổng có thể tự tìm hiểu trạng thái hoạt động của nhà cung cấp một cách độc lập, dẫn đến hành vi dự phòng không đồng đều. Phiên bản sản xuất nên lưu trữ trạng thái mạch hoặc tín hiệu trạng thái hoạt động trong Redis hoặc một mặt phẳng điều khiển chuyên dụng.

## 9. Next steps

1. Thêm trạng thái ngắt mạch dựa trên Redis cho các triển khai đa phiên bản.
2. Thêm kiểm thử tải đồng thời bằng cách sử dụng giá trị đồng thời đã cấu hình.
3. Xuất các bộ đếm và chỉ số Prometheus cho các số liệu về yêu cầu, độ trễ, bộ nhớ đệm và mạch.