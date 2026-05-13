"""
Incident scenario catalogue.

Each entry is a pure-data dict — no functions, no side effects.
The key is a stable slug used throughout the application.
"""
from __future__ import annotations

from typing import TypedDict


class ScenarioMetrics(TypedDict):
    cpu: str
    error_rate: str
    p99_latency: str


class Scenario(TypedDict):
    label:    str
    icon:     str
    severity: str
    service:  str
    stack:    str
    alert:    str
    metrics:  ScenarioMetrics
    logs:     list[tuple[str, str, str]]   # (level, service, message)


SCENARIOS: dict[str, Scenario] = {
    "cpu_runaway": {
        "label":    "CPU runaway — nginx fork storm",
        "icon":     "🔥",
        "severity": "P1",
        "service":  "nginx",
        "stack":    "kubernetes",
        "alert":    "[P1] CPU 97% prod-{1,2,3} · nginx workers unresponsive · HAProxy circuit open",
        "metrics":  {"cpu": "97%", "error_rate": "61%", "p99_latency": "8,200ms"},
        "logs": [
            ("ERROR", "nginx",       "worker_0: CPU 94% — accept() loop stalled"),
            ("ERROR", "nginx",       "worker_1: CPU 97% — accept() loop stalled"),
            ("ERROR", "nginx",       "worker_2: CPU 99% — OOM killer invoked"),
            ("WARN",  "api-gateway", "upstream timeout: nginx→api 3,002ms [threshold 1,000ms]"),
            ("ERROR", "k8s",         "pod nginx-deploy-7f9b2 — CrashLoopBackOff [restarts:6]"),
            ("ERROR", "k8s",         "pod nginx-deploy-4a1c9 — CrashLoopBackOff [restarts:4]"),
            ("WARN",  "haproxy",     "backend nginx_pool: 2/4 DOWN, circuit OPEN"),
            ("ERROR", "slo-mon",     "slo:availability=0.74 < 0.999 [5m window] — BREACH"),
        ],
    },
    "db_replica_lag": {
        "label":    "DB replica lag — checkout 500s",
        "icon":     "🐢",
        "severity": "P1",
        "service":  "postgres",
        "stack":    "postgresql",
        "alert":    "[P1] Postgres replica lag 8.4s · checkout 500 rate 42% · SLO breach",
        "metrics":  {"cpu": "31%", "error_rate": "42%", "p99_latency": "6,100ms"},
        "logs": [
            ("ERROR", "checkout",  "NullPointerException: row.get('user_id') is None [read: replica]"),
            ("ERROR", "checkout",  "NullPointerException: row.get('cart_total') is None [read: replica]"),
            ("ERROR", "checkout",  "GET /api/v2/checkout 500 — stale read, lag=8412ms"),
            ("WARN",  "postgres",  "streaming_replication: lag=8412ms primary_lsn=A1/B7 replica=A0/C2"),
            ("ERROR", "sentry",    "CheckoutService: 1,847 NullPointerException in 60s"),
            ("WARN",  "postgres",  "autovacuum: table 'orders' dead_tup_ratio=0.41 [threshold 0.2]"),
            ("ERROR", "pagerduty", "P1 created: checkout.http_500_rate=0.42 > 0.05 [5m]"),
            ("WARN",  "haproxy",   "server postgres_replica1 DOWN — health check 3/3 failed"),
        ],
    },
    "memory_leak": {
        "label":    "Memory leak — auth-svc OOM",
        "icon":     "💧",
        "severity": "P2",
        "service":  "auth-svc",
        "stack":    "kubernetes",
        "alert":    "[P2] auth-svc heap 94% · JWTCache 14GB · OOM imminent · HPA maxed",
        "metrics":  {"cpu": "78%", "error_rate": "18%", "p99_latency": "9,800ms"},
        "logs": [
            ("WARN",  "auth-svc",    "JWTCache: size=14.2GB entries=2,847,301 — no eviction policy"),
            ("WARN",  "auth-svc",    "JWTCache: size=14.8GB — GC pause 2.1s"),
            ("ERROR", "auth-svc",    "java.lang.OutOfMemoryError: Java heap space [heap: 94%]"),
            ("ERROR", "k8s",         "pod auth-svc-76f9 OOMKilled [exit:137] — restarting"),
            ("WARN",  "api-gateway", "auth upstream: 3 consecutive 503s — weight→0"),
            ("ERROR", "checkout",    "AuthClient: token validation timeout [12s, auth unreachable]"),
            ("WARN",  "k8s",         "HPA: auth-svc at max replicas (5/5) — cannot scale"),
            ("ERROR", "slo-mon",     "slo:auth.validate_token p99=9800ms > 200ms — BREACH"),
        ],
    },
    "bad_deploy": {
        "label":    "Bad deploy — ConfigMap missing key",
        "icon":     "💥",
        "severity": "P2",
        "service":  "checkout",
        "stack":    "kubernetes",
        "alert":    "[P2] checkout error rate 0.2%→28% post-deploy v2.4.1 [12:47 UTC]",
        "metrics":  {"cpu": "42%", "error_rate": "28%", "p99_latency": "2,100ms"},
        "logs": [
            ("ERROR", "checkout", "ConfigError: DB_REPLICA_HOST not in env — initialized None"),
            ("ERROR", "checkout", "NullPointerException: db_client.connect() on None [db_client.py:84]"),
            ("ERROR", "checkout", "GET /api/v2/checkout 500 [52ms] — unhandled exception"),
            ("ERROR", "checkout", "GET /api/v2/orders   500 [48ms] — unhandled exception"),
            ("WARN",  "k8s",      "rollout checkout v2.4.1: 3/6 pods Ready — stalling"),
            ("ERROR", "sentry",   "checkout: 923 ConfigError exceptions since deploy 12:47"),
            ("WARN",  "argocd",   "health: checkout Degraded — readiness probe failing [3/6]"),
            ("INFO",  "k8s",      "rollout history: v2.4.0 [last-stable] v2.4.1 [current]"),
        ],
    },
    "redis_cascade": {
        "label":    "Redis cluster fail — cascade timeout",
        "icon":     "⛓",
        "severity": "P2",
        "service":  "redis",
        "stack":    "redis",
        "alert":    "[P2] Redis node 10.0.1.7 disk-full · cluster FAIL · inventory→checkout cascade",
        "metrics":  {"cpu": "55%", "error_rate": "31%", "p99_latency": "5,400ms"},
        "logs": [
            ("ERROR", "redis",     "CLUSTER FAIL — node 10.0.1.7:6379 unreachable [15s]"),
            ("ERROR", "inventory", "RedisConnectionError: [Errno 110] Connection timed out [10.0.1.7:6379]"),
            ("WARN",  "inventory", "cache MISS fallback postgres: stock_levels [4,200ms]"),
            ("WARN",  "inventory", "circuit breaker: redis OPEN — all reads→DB"),
            ("ERROR", "checkout",  "InventoryClient: check_stock() timeout 5,000ms — rejecting order"),
            ("WARN",  "checkout",  "GET /api/v2/checkout 503 — inventory unavailable"),
            ("ERROR", "slo-mon",   "slo:checkout_success_rate=0.68 < 0.995 [5m] — BREACH"),
            ("WARN",  "redis",     "sentinel: promoting 10.0.1.8:6379 as primary [election 2.1s]"),
        ],
    },
    "cassandra_compaction": {
        "label":    "Cassandra compaction backlog — read latency spike",
        "icon":     "💎",
        "severity": "P1",
        "service":  "cassandra",
        "stack":    "cassandra",
        "alert":    "[P1] Cassandra dc1 node 10.0.1.3 DOWN · compaction backlog 847 tasks · p99 read 28s",
        "metrics":  {"cpu": "72%", "error_rate": "38%", "p99_latency": "28,400ms"},
        "logs": [
            ("ERROR", "cassandra",  "node 10.0.1.3 is DOWN — last heartbeat 47s ago"),
            ("ERROR", "cassandra",  "CompactionExecutor: 847 pending tasks — threshold 32"),
            ("WARN",  "cassandra",  "ReadTimeout: keyspace=prod_keyspace table=orders cl=QUORUM [28.4s]"),
            ("ERROR", "cassandra",  "GC pause 14.2s — heap 91% used — young gen exhausted"),
            ("WARN",  "cassandra",  "SSTable count: 1,247 — above compaction_throughput_mb_per_sec limit"),
            ("ERROR", "order-svc",  "CassandraReadTimeout: read_cl=QUORUM 2/3 replicas responded"),
            ("WARN",  "cassandra",  "Dropping MUTATION messages: 1,284/s (coordinator overloaded)"),
            ("ERROR", "slo-mon",    "slo:order.create p99=28400ms > 500ms — BREACH"),
        ],
    },
    "kafka_consumer_lag": {
        "label":    "Kafka consumer lag — 4.9M messages behind",
        "icon":     "📨",
        "severity": "P2",
        "service":  "kafka",
        "stack":    "kafka",
        "alert":    "[P2] Kafka consumer group order-processor lag 4.9M · orders topic · rebalance loop",
        "metrics":  {"cpu": "45%", "error_rate": "0%", "p99_latency": "N/A"},
        "logs": [
            ("ERROR", "kafka",           "ConsumerGroup order-processor: lag=4,913,100 on topic orders"),
            ("WARN",  "kafka",           "Consumer rebalance triggered — member order-proc-7 left group"),
            ("WARN",  "order-processor", "ConsumerRebalanceListener: partitions revoked [0,1,2,3,4,5]"),
            ("ERROR", "order-processor", "CommitFailedException: offset commit failed during rebalance"),
            ("ERROR", "kafka",           "broker-2 UnderReplicatedPartitions: 4 [orders:0,1 events:2,3]"),
            ("WARN",  "kafka",           "HighWatermark stalling — follower 10.0.2.3 fetch lag: 1,247ms"),
            ("ERROR", "order-processor", "poll() took 32,412ms — exceeding max.poll.interval.ms=30000"),
            ("WARN",  "kafka",           "JoinGroup rebalance: 6 consumers, session.timeout.ms=10000"),
        ],
    },
    "opensearch_shard_fail": {
        "label":    "OpenSearch unassigned shards — cluster RED",
        "icon":     "🔴",
        "severity": "P1",
        "service":  "opensearch",
        "stack":    "opensearch",
        "alert":    "[P1] OpenSearch cluster status RED · 24 unassigned shards · logs-2024.04 degraded",
        "metrics":  {"cpu": "62%", "error_rate": "97%", "p99_latency": "12,100ms"},
        "logs": [
            ("ERROR", "opensearch",   "cluster status: RED — 24 unassigned shards [logs-2024.04, events-prod]"),
            ("ERROR", "opensearch",   "node os-data-3 failed to join cluster — disk watermark exceeded [94%]"),
            ("WARN",  "opensearch",   "disk.watermark.flood_stage reached: 94% — index writes blocked"),
            ("ERROR", "opensearch",   "ShardNotAssignedException: shard [logs-2024.04][3] has no assigned node"),
            ("WARN",  "opensearch",   "allocation explain: no node has enough disk space for shard (18.4 GiB)"),
            ("ERROR", "log-ingester", "OpenSearchException: blocked by [FORBIDDEN/12/index read-only]"),
            ("WARN",  "opensearch",   "segments: 12,847 — merge throttling at 120% of target"),
            ("ERROR", "slo-mon",      "slo:log_query_p99=12100ms > 2000ms — BREACH"),
        ],
    },
    "pg_vacuum_bloat": {
        "label":    "Postgres table bloat — autovacuum starvation",
        "icon":     "🫧",
        "severity": "P2",
        "service":  "postgres",
        "stack":    "postgresql",
        "alert":    "[P2] Postgres orders table 47GB bloat · autovacuum can't keep up · txid wraparound risk",
        "metrics":  {"cpu": "89%", "error_rate": "12%", "p99_latency": "3,800ms"},
        "logs": [
            ("WARN",  "postgres", "autovacuum: table prod.public.orders — 2,847,301 dead tuples [ratio: 0.41]"),
            ("WARN",  "postgres", "autovacuum worker cancelled: lock conflict on orders — retry in 300s"),
            ("ERROR", "postgres", "txid wraparound: age(relfrozenxid)=1,200,000,000 APPROACHING LIMIT"),
            ("WARN",  "postgres", "table bloat: orders estimated 47.2 GiB dead space"),
            ("WARN",  "postgres", "checkpoint: 312s — exceeding checkpoint_completion_target"),
            ("ERROR", "checkout", "slow query: SELECT * FROM orders WHERE user_id=$1 [3,847ms] — seq scan"),
            ("WARN",  "postgres", "shared_buffers hit ratio: 71% — below threshold 90%"),
            ("WARN",  "postgres", "lock wait: autovacuum vs OLTP — 847 queries waiting"),
        ],
    },
}
