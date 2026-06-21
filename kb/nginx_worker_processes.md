## INC-001 · P1 · nginx · cpu, kubernetes, haproxy, worker-processes

**Title:** nginx CPU runaway from hardcoded worker_processes

**Root cause:** The `nginx-config` ConfigMap pinned `worker_processes` to a fixed
value (512) instead of `auto`. Once traffic exceeded normal levels, nginx
spawned far more worker processes than available CPU cores, causing CPU
contention, `accept()` loop stalls, and the kernel OOM killer terminating
workers under memory pressure. HAProxy then opened its circuit breaker on the
upstream pool, compounding the outage.

**Remediation steps:**
1. `kubectl edit configmap nginx-config -n prod`
2. Change `worker_processes 512;` to `worker_processes auto;`
3. `kubectl rollout restart deployment/nginx-deploy -n prod`
4. Watch the rollout: `kubectl rollout status deployment/nginx-deploy -n prod`

**Verification:**
- `kubectl top pods --selector=app=nginx` — CPU should drop under 70% within
  two minutes of rollout completion.
- Confirm HAProxy backend `nginx_pool` returns to 4/4 UP.
- `slo:availability` should return above 0.999 within the next 5-minute
  window.

**Prevention:** Add a CI lint rule that rejects any explicit numeric
`worker_processes` value in nginx ConfigMaps — require `auto`. Add a
HorizontalPodAutoscaler targeting 60% CPU so the pod count scales with
traffic instead of relying on a fixed worker count.
