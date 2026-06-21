## INC-003 · P2 · auth-svc · memory-leak, oom, kubernetes

**Title:** auth-svc OOMKilled from unbounded session cache growth

**Root cause:** auth-svc's in-memory session cache had no TTL or eviction
policy. Under sustained traffic, the cache grew without bound until pods hit
their memory limit and were OOMKilled by kubelet — triggering rolling
restarts and intermittent authentication failures across dependent services.

**Remediation steps:**
1. Roll out the hotfix enabling TTL-based eviction:
   `SESSION_CACHE_TTL=900s`
2. `kubectl rollout restart deployment/auth-svc -n prod`
3. Temporarily raise the memory limit from 512Mi to 768Mi to give headroom
   while the rollout completes, then revert once the leak is confirmed
   fixed.

**Verification:**
`kubectl top pods --selector=app=auth-svc` should show stable memory usage
over a 15-minute window, instead of the previous sawtooth-then-OOM pattern.

**Prevention:** Add a Prometheus alert on per-pod memory growth rate (not
just absolute usage, so slow leaks get caught early). Require a TTL or
eviction policy for any in-process cache as part of the code review
checklist.
