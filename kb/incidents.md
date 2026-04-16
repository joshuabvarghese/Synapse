# Incident Knowledge Base

This folder contains your runbooks in plain Markdown.
Add your own files here — ops-context will embed and index them automatically on startup.

File format is flexible. The loader reads: incident ID, title, severity, tags, and resolution steps.

---

## INC-2024-0312 · P1 · nginx · cpu, kubernetes, configmap

**Title:** CPU runaway — nginx worker_processes fork storm post-deploy

**Resolution:**
Root cause: `worker_processes` directive set to `512` in nginx.conf (should be `auto`).
Under load this caused exponential worker forking until kernel OOM killer intervened.
Two pods entered CrashLoopBackOff. HAProxy circuit breaker opened, dropping 61% of traffic.

Steps:
1. Immediate: rolling restart to clear zombie workers
   `kubectl rollout restart deployment/nginx -n prod`
2. Fix the config: patch nginx ConfigMap
   `kubectl patch cm nginx-config -n prod --patch '{"data":{"worker_processes":"auto","worker_rlimit_nofile":"65535"}}'`
3. Verify CPU drops below 30% within 60 seconds
   `kubectl top pods -n prod -l app=nginx --sort-by=cpu`
4. Add HPA to prevent recurrence
   `kubectl autoscale deployment/nginx -n prod --cpu-percent=70 --min=2 --max=8`

MTTR: 6 minutes.
Prevention: Kyverno policy rejecting nginx ConfigMaps with worker_processes > 32.

---

## INC-2024-0455 · P1 · postgres · replica-lag, checkout, aurora

**Title:** DB replica lag 8.4 seconds — checkout NullPointerExceptions during failover

**Resolution:**
Root cause: Aurora primary failed, streaming replication lag reached 8,412ms.
Checkout service reads from replica and received stale/null rows for `user_id` and `cart_total`.
1,847 NullPointerExceptions in 60 seconds, SLO breach.

Steps:
1. Failover Aurora cluster to promote replica
   `aws rds failover-db-cluster --db-cluster-id prod-aurora-cluster --region ap-southeast-2`
2. Update DB_HOST secret to new primary endpoint
   `kubectl create secret generic db-creds -n prod --from-literal=DB_HOST=<new-primary-fqdn> --dry-run=client -o yaml | kubectl apply -f -`
3. Restart checkout to pick up new endpoint
   `kubectl rollout restart deployment/checkout -n prod`
4. Confirm error rate drops below 1%
   `kubectl exec -it deploy/checkout -n prod -- curl -s localhost:8080/metrics | grep http_error_rate`

MTTR: 5 minutes.
Prevention: Aurora Multi-AZ with automatic failover < 30s. Alert at replica lag > 1000ms.

---

## INC-2023-1108 · P2 · auth-svc · memory-leak, oom, java, jwt

**Title:** OOM — JWTCache unbounded in auth-svc v1.4.1, heap 94%

**Resolution:**
Root cause: auth-svc v1.4.1 introduced JWTCache with no TTL or max-size.
Cache grew to 14.2GB over 6 hours. GC pause reached 2.1s. OOMKill triggered.
HPA was already at max replicas (5/5) so horizontal scaling could not help.

Steps:
1. Roll back to v1.4.0 immediately
   `kubectl set image deployment/auth-svc auth-svc=registry.internal/auth-svc:v1.4.0 -n prod`
2. Confirm heap drops below 30% within 2 minutes
   `kubectl top pods -n prod -l app=auth-svc --sort-by=memory`
3. Verify auth flow end-to-end
   `curl -sf https://api.prod.internal/auth/validate -H "Authorization: Bearer $TEST_TOKEN" -o /dev/null -w "%{http_code}"`
4. Schedule fix: add JVM flags to deployment manifest
   `-XX:MaxHeapSize=2g -Dcache.jwt.maxSize=50000 -Dcache.jwt.ttl=3600`

MTTR: 8 minutes.
Prevention: Heap alert at 80%. Require cache TTL and max-size in all service config reviews.

---

## INC-2024-0711 · P2 · checkout · bad-deploy, configmap, helm, null-pointer

**Title:** Bad deploy v2.4.1 — DB_REPLICA_HOST missing from Helm ConfigMap template

**Resolution:**
Root cause: Helm chart v2.4.1 dropped `DB_REPLICA_HOST` from the ConfigMap template.
`db_client` initialized with `None` host, throwing NullPointerException on every DB call.
3 of 6 pods stalled on readiness probe. Rollout halted at 50%.

Steps:
1. Immediate rollback
   `kubectl rollout undo deployment/checkout -n prod`
2. Confirm all 6 pods healthy
   `kubectl rollout status deployment/checkout -n prod --timeout=120s`
3. Patch ConfigMap to prevent re-deploy regression
   `kubectl patch cm checkout-config -n prod --patch '{"data":{"DB_REPLICA_HOST":"prod-replica.internal"}}'`
4. Fix Helm template values.yaml before next deploy
   Add: `db.replicaHost: prod-replica.internal` under checkout config block

MTTR: 6 minutes.
Prevention: Pre-upgrade Helm hook that validates all required ConfigMap keys exist.

---

## INC-2024-0891 · P2 · redis · cluster-fail, inventory, cascade, disk

**Title:** Redis cluster node disk-full — inventory cascade timeout to checkout

**Resolution:**
Root cause: Redis node 10.0.1.7 disk reached 100%. AOF write failures caused cluster
to mark the node FAIL. Inventory fell back to Postgres for all stock reads (4200ms vs 2ms).
InventoryClient hard-timeout at 5000ms caused checkout to return 503s.

Steps:
1. Trigger cluster failover to healthy node
   `redis-cli -h 10.0.1.9 -p 6379 CLUSTER FAILOVER FORCE`
2. Clear disk on failed node — enable LRU eviction
   `redis-cli -h 10.0.1.7 -p 6379 CONFIG SET maxmemory-policy allkeys-lru`
   `redis-cli -h 10.0.1.7 -p 6379 BGREWRITEAOF`
3. Restart inventory to reset circuit breaker
   `kubectl rollout restart deployment/inventory -n prod`
4. Confirm cache hit ratio returns above 90%
   `redis-cli -h 10.0.1.9 INFO stats | grep keyspace_hits`

MTTR: 9 minutes.
Prevention: Disk alert at 75% for all Redis nodes. Set maxmemory-policy=allkeys-lru by default.

---

## INC-2025-0034 · P1 · k8s · etcd, control-plane, node-notready

**Title:** etcd leader election failure — 3 nodes NotReady, cluster control plane degraded

**Resolution:**
Root cause: etcd quorum lost after network partition between control-plane nodes.
Leader election failed, kube-apiserver returned 503s, kubectl commands hung.
New deployments and pod scheduling halted entirely.

Steps:
1. Check etcd member health
   `etcdctl --endpoints=https://10.0.0.1:2379 member list --cacert=/etc/kubernetes/pki/etcd/ca.crt --cert=/etc/kubernetes/pki/etcd/server.crt --key=/etc/kubernetes/pki/etcd/server.key`
2. Remove failed member and re-add
   `etcdctl member remove <member-id>`
   `etcdctl member add etcd-3 --peer-urls=https://10.0.0.3:2380`
3. Restart kubelet on affected node
   `systemctl restart kubelet`
4. Verify nodes Ready
   `kubectl get nodes --watch`

MTTR: 14 minutes.
Prevention: Odd number of etcd nodes (3 or 5). Cross-AZ placement. etcd backup every 30 minutes.
