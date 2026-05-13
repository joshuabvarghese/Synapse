"""
Diagnostic command simulator.

``simulate(command, scenario_key)`` returns a realistic-looking terminal
output string for the given command and active scenario.  All logic is
pure: no I/O, no side effects, no global state.
"""
from __future__ import annotations

import random
from datetime import datetime


def simulate(command: str, scenario_key: str) -> str:
    """
    Return simulated CLI output for *command* in the context of *scenario_key*.

    Parameters
    ----------
    command:
        The full command string the agent wants to run.
    scenario_key:
        The slug of the active scenario (e.g. ``"cassandra_compaction"``).
    """
    cmd = command.lower().strip()
    now = datetime.utcnow().strftime("%H:%M:%S")

    # Dispatch to the first matching handler
    for predicate, handler in _HANDLERS:
        if predicate(cmd, scenario_key):
            return handler(cmd, scenario_key, now)

    return f"$ {command}\n[{now}] Command executed successfully"


# ── Handlers ──────────────────────────────────────────────────────────────────
#
# Each entry is (predicate, handler).
# predicate(cmd, scenario_key) -> bool
# handler(cmd, scenario_key, now) -> str

def _kubectl_top(cmd: str, key: str, now: str) -> str:
    if key == "cpu_runaway":
        return (
            "NAME                              CPU(cores)   MEMORY(bytes)\n"
            "nginx-deploy-7f9b2-xkp4q          971m         312Mi\n"
            "nginx-deploy-7f9b2-m3rz1          989m         298Mi\n"
            "nginx-deploy-7f9b2-c9wq8          CrashLoopBackOff"
        )
    if key == "memory_leak":
        return (
            "NAME                              CPU(cores)   MEMORY(bytes)\n"
            "auth-svc-76f9-kpx2m               312m         14200Mi\n"
            "auth-svc-76f9-rtzq1               287m         13890Mi"
        )
    svc = key.split("_")[0]
    return (
        f"NAME                              CPU(cores)   MEMORY(bytes)\n"
        f"{svc}-deploy-ab1cd                 {random.randint(30, 80)}m  {random.randint(100, 400)}Mi"
    )


def _kubectl_get_pod(cmd: str, key: str, now: str) -> str:
    if key == "cpu_runaway":
        return (
            "NAME                          READY   STATUS             RESTARTS\n"
            "nginx-deploy-7f9b2-xkp4q      0/1     CrashLoopBackOff   6\n"
            "nginx-deploy-7f9b2-m3rz1      0/1     CrashLoopBackOff   4\n"
            "nginx-deploy-7f9b2-c9wq8      1/1     Running            0"
        )
    if key == "bad_deploy":
        return (
            "NAME                          READY   STATUS    RESTARTS\n"
            "checkout-deploy-v241-aab12    0/1     Running   0\n"
            "checkout-deploy-v241-bcd34    0/1     Running   0\n"
            "checkout-deploy-v240-xyz99    1/1     Running   0  (previous)"
        )
    svc = key.split("_")[0]
    return f"NAME                          READY   STATUS    RESTARTS\n{svc}-deploy-ab1cd-xk1          1/1     Running   0"


def _kubectl_rollout(cmd: str, key: str, now: str) -> str:
    svc = key.split("_")[0]
    if "undo" in cmd or "restart" in cmd:
        return f"deployment.apps/{svc} restarted\nWaiting for rollout: 0 of 3 updated replicas available..."
    if "status" in cmd:
        return f'deployment "{svc}" successfully rolled out'
    return f"deployment.apps/{svc} rolled out"


def _kubectl_logs(cmd: str, key: str, now: str) -> str:
    if key == "cpu_runaway":
        return (
            f"[{now}] ERROR nginx worker_processes=512 — expected 'auto'\n"
            f"[{now}] ERROR nginx worker_0: CPU 97% accept() loop stalled\n"
            f"[{now}] WARN  nginx OOM killer invoked on worker_2"
        )
    if key == "memory_leak":
        return (
            f"[{now}] WARN  JWTCache: size=14.2GB entries=2847301\n"
            f"[{now}] ERROR java.lang.OutOfMemoryError: Java heap space\n"
            f"[{now}] ERROR heap: 94% used, GC pause 2.1s"
        )
    svc = key.split("_")[0]
    return f"[{now}] INFO  {svc}: serving requests normally"


def _kubectl_describe(cmd: str, key: str, now: str) -> str:
    svc = key.split("_")[0]
    return (
        f"Name: {svc}-deploy-7f9b2-xkp4q\nStatus: CrashLoopBackOff\nEvents:\n"
        f"  {now}  Warning  BackOff  kubelet  Back-off restarting failed container\n"
        f"  {now}  Warning  OOMKilling  kernel  Out of memory: Kill process"
    )


def _kubectl_patch(cmd: str, key: str, now: str) -> str:
    svc = key.split("_")[0]
    return f"deployment.apps/{svc} patched"


def _kubectl_hpa(cmd: str, key: str, now: str) -> str:
    svc = key.split("_")[0]
    return f"horizontalpodautoscaler.autoscaling/{svc} created\nMin: 2  Max: 8  CPU target: 70%"


def _aws_rds(cmd: str, key: str, now: str) -> str:
    if "failover" in cmd:
        return (
            '{\n  "DBCluster": {\n    "Status": "failing-over",\n'
            '    "ReaderEndpoint": "prod-aurora-cluster.cluster-ro-xyz.ap-southeast-2.rds.amazonaws.com"\n  }\n}'
        )
    return '{"DBCluster": {"Status": "available", "ReplicaLag": "0ms"}}'


def _redis_cli(cmd: str, key: str, now: str) -> str:
    if "cluster failover" in cmd:
        return "OK\n# Failover started. New primary: 10.0.1.8:6379"
    if "config set" in cmd or "bgrewriteaof" in cmd:
        return "OK"
    if "info" in cmd:
        return (
            "# Stats\nkeyspace_hits:48291\nkeyspace_misses:512\n"
            "# Memory\nused_memory_human:2.41G\nmaxmemory_policy:allkeys-lru"
        )
    return "OK"


def _nodetool(cmd: str, key: str, now: str) -> str:
    if "status" in cmd:
        if key == "cassandra_compaction":
            return (
                "Datacenter: dc1\n===============\n"
                "UN  10.0.1.1      425.2 GiB  256     33.3%   a1b2c3...  rack1\n"
                "UN  10.0.1.2      423.8 GiB  256     33.3%   d4e5f6...  rack1\n"
                "DN  10.0.1.3      0 bytes    256     33.4%   g7h8i9...  rack1  ← DOWN"
            )
        return (
            "Datacenter: dc1\n===============\n"
            "UN  10.0.1.1      312.4 GiB  256     33.3%   a1b2c3...  rack1\n"
            "UN  10.0.1.2      309.1 GiB  256     33.3%   d4e5f6...  rack1\n"
            "UN  10.0.1.3      311.8 GiB  256     33.4%   g7h8i9...  rack1"
        )
    if "compactionstats" in cmd:
        return (
            "pending tasks: 847\n"
            "- keyspace: prod_keyspace, table: orders, completed: 12%, remaining: 142.3 GiB\n"
            "Active compaction remaining time : 0h18m32s"
        )
    if "tpstats" in cmd:
        return (
            "Pool Name                    Active   Pending   Completed\n"
            "CompactionExecutor              4        847       1,204,892\n"
            "ReadStage                       32       1,284     98,234,012"
        )
    if "repair" in cmd:
        return f"[{now}] Starting repair command #1\n[{now}] Repair completed successfully"
    return f"[{now}] nodetool: command executed"


def _kafka_cli(cmd: str, key: str, now: str) -> str:
    if key == "kafka_consumer_lag":
        if "consumer-groups" in cmd and "describe" in cmd:
            return (
                "GROUP                TOPIC           PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG\n"
                "order-processor      orders          0          1,234,891        2,891,234       1,656,343\n"
                "order-processor      orders          1          1,189,023        2,834,891       1,645,868\n"
                "order-processor      orders          2          1,201,445        2,812,334       1,610,889\n"
                "Total consumer lag: 4,913,100"
            )
        if "topics" in cmd and "describe" in cmd:
            return (
                "Topic: orders\n  PartitionCount: 12\n  ReplicationFactor: 3\n"
                "  Under-replicated Partitions: 0\n  Leader: broker-1 (10.0.2.1:9092)"
            )
    if "reassign" in cmd:
        return "Reassignment of partition [orders, 0] completed successfully"
    return f"[{now}] Kafka command executed successfully"


def _opensearch_curl(cmd: str, key: str, now: str) -> str:
    if key == "opensearch_shard_fail":
        if "_cluster/health" in cmd:
            return (
                '{"cluster_name":"prod-os","status":"red","number_of_nodes":3,'
                '"active_shards":847,"unassigned_shards":24,"active_shards_percent":97.2}'
            )
        if "_cat/shards" in cmd:
            return (
                "INDEX          SHARD  PRIREP  STATE       DOCS    STORE\n"
                "logs-2024.04   3      p       UNASSIGNED  -       -\n"
                "events-prod    1      p       UNASSIGNED  -       -"
            )
        if "reroute" in cmd or "allocate" in cmd:
            return '{"acknowledged":true}'
    if "_cluster/health" in cmd:
        return '{"cluster_name":"prod-os","status":"green","number_of_nodes":3,"active_shards":912}'
    return '{"acknowledged":true}'


def _psql(cmd: str, key: str, now: str) -> str:
    return "synapse:5432 - accepting connections"


def _curl_health(cmd: str, key: str, now: str) -> str:
    return 'HTTP/1.1 200 OK\n{"status":"ok"}'


def _etcdctl(cmd: str, key: str, now: str) -> str:
    if "member list" in cmd:
        return (
            "8e9e05c52164694d, started, etcd-1, https://10.0.0.1:2380\n"
            "91bc3c398fb3c146, started, etcd-2, https://10.0.0.2:2380\n"
            "fd422379fda50e48, failed,  etcd-3, https://10.0.0.3:2380"
        )
    return "Member removed\nMember added"


# ── Handler dispatch table ────────────────────────────────────────────────────

_HANDLERS: list[tuple] = [
    (lambda cmd, _k: "top pod" in cmd,                                                  _kubectl_top),
    (lambda cmd, _k: "get pod" in cmd,                                                  _kubectl_get_pod),
    (lambda cmd, _k: "rollout" in cmd,                                                  _kubectl_rollout),
    (lambda cmd, _k: "logs" in cmd and "kafka" not in cmd,                              _kubectl_logs),
    (lambda cmd, _k: "describe" in cmd,                                                 _kubectl_describe),
    (lambda cmd, _k: "patch" in cmd or "set image" in cmd,                             _kubectl_patch),
    (lambda cmd, _k: "autoscale" in cmd or "hpa" in cmd,                               _kubectl_hpa),
    (lambda cmd, _k: "aws rds" in cmd,                                                  _aws_rds),
    (lambda cmd, _k: "redis-cli" in cmd or ("redis" in cmd and "kafka" not in cmd),    _redis_cli),
    (lambda cmd, _k: "nodetool" in cmd,                                                 _nodetool),
    (lambda cmd, _k: any(k in cmd for k in ("kafka-consumer-groups", "kafka-topics")), _kafka_cli),
    (lambda cmd, _k: "kafka" in cmd,                                                    _kafka_cli),
    (lambda cmd, _k: "curl" in cmd and ("_cluster" in cmd or "_cat" in cmd or "9200" in cmd), _opensearch_curl),
    (lambda cmd, _k: "psql" in cmd or "pg_isready" in cmd,                             _psql),
    (lambda cmd, _k: "curl" in cmd and "health" in cmd,                                _curl_health),
    (lambda cmd, _k: "etcdctl" in cmd,                                                 _etcdctl),
]
