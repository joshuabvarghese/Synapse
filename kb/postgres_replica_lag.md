## INC-002 · P1 · postgres · replication, replica-lag, checkout

**Title:** Checkout 500s caused by stale reads during replica lag

**Root cause:** A long-running analytics query on the read replica held a
snapshot open and blocked WAL replay, pushing replication lag to over 8
seconds. The `checkout` service reads from the replica for performance, so
it began receiving stale or missing rows — surfacing as
`NullPointerException: row.get('user_id') is None` and HTTP 500s on
`/api/v2/checkout`.

**Remediation steps:**
1. Find and terminate the blocking query:
   ```sql
   SELECT pg_terminate_backend(pid) FROM pg_stat_activity
   WHERE state = 'active' AND query_start < now() - interval '2 minutes';
   ```
2. Temporarily route checkout reads to the primary:
   `set service_routing.checkout_reads=primary`
3. Once lag drops below 1 second, revert routing back to the replica.

**Verification:**
```sql
SELECT now() - pg_last_xact_replay_timestamp() AS replication_lag;
```
Confirm this is under 1 second, and that checkout's 500 rate has dropped
back under 1%.

**Prevention:** Move long-running analytics/reporting queries to a
dedicated reporting replica, separate from the one application traffic
reads from. Tune `max_standby_streaming_delay` appropriately, and add an
alert that fires when replication lag exceeds 3 seconds — well before it
becomes customer-visible.
