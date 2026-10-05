# M6 — Health & Load Monitor

## Responsibility
Continuously observe backend health and load and publish normalized server snapshots.

## Metrics
- health
- active connections
- capacity
- weight
- recent latency
- failure rate
- last-seen timestamp

## Rules
A monitor failure must not terminate the load balancer. Stale snapshots must have an explicit expiry policy.

## Completion gate
Stopping a backend is detected and new routing decisions exclude it; restarting it allows recovery after successful health checks.