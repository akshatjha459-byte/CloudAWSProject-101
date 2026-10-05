# CN Module Contracts

This document defines the interfaces between the 10 modules of **Intelligent Network Load Balancer with Dynamic Traffic Routing**. Implementations must follow these contracts. If an interface changes, update this document before changing dependent modules.

## Module Map

1. Traffic Generator / Clients
2. Network Protocol & Message Model
3. Backend Server Simulator
4. Load Balancer Core
5. Routing Algorithms
6. Health & Load Monitor
7. Dynamic Routing Engine
8. Network Conditions & Fault Injection
9. Metrics & Experiment Engine
10. Dashboard & Visualization

---

## Shared Identifiers

Every request has a unique `request_id`. Every backend has a stable `server_id`. Use a monotonic clock for latency measurement and wall-clock time only for display/logging.

---

## M1 <-> M2: Traffic Contract

M1 produces a `TrafficRequest` through M2's serialization layer.

```text
request_id
client_id
protocol: TCP | UDP
payload_size
payload
created_at
timeout_ms
```

M1 must not select a backend.

---

## M2 <-> M4: Load Balancer Request Contract

M2 provides serialization/deserialization for requests and responses. M4 accepts a normalized request independent of the traffic-generator implementation.

Response minimum:

```text
request_id
status: SUCCESS | FAILURE | TIMEOUT
server_id
server_latency_ms
completed_at
error_code?
```

M2 owns schemas and encoding; M4 owns routing.

---

## M4 <-> M3: Backend Contract

M4 forwards a request to one selected backend endpoint:

```text
server_id
host
port
protocol
request_id
payload
timeout_ms
```

M3 returns a response associated with the same `request_id` and exposes a health endpoint or equivalent health probe for M6.

---

## M4 <-> M5: Routing Strategy Contract

M5 exposes one common interface:

```text
select_server(request, server_snapshots, routing_context) -> RouteDecision
```

`RouteDecision` minimum fields:

```text
request_id
server_id
strategy_name
reason
score?
```

Required strategies:
- `round_robin`
- `least_connections`
- `weighted_round_robin` or equivalent weighted selection

Optional:
- `weighted_least_connections`

A strategy may not open sockets or forward traffic. It only chooses a target.

---

## M6 -> M5/M7: Server Snapshot Contract

M6 publishes immutable snapshots:

```text
server_id
healthy
active_connections
capacity
weight
avg_latency_ms
failure_rate
last_seen
timestamp
```

M5 may use the fields needed by its algorithm. M7 may use the complete snapshot.

---

## M6 <-> M3: Health Contract

M6 probes each backend without modifying application state. A failed or timed-out health check marks the backend unhealthy. Recovery requires a successful probe.

M3 should expose enough state for active connection count and capacity to be measured or reported.

---

## M7 <-> M5: Dynamic Routing Contract

M7 must not duplicate algorithm implementations. It may decorate or compose an M5 strategy using live M6 snapshots.

Minimum interface:

```text
decide(request, server_snapshots, base_strategy, dynamic_config) -> RouteDecision
```

Example dynamic configuration:

```text
load_weight
latency_weight
failure_weight
capacity_weight
minimum_health
```

The result must contain a reason that can be displayed by M10, for example `lowest_normalized_load`.

---

## M8 -> M3/M4: Fault Contract

M8 supplies a `FaultProfile` that can be applied to a server or traffic path:

```text
target_server_id?
delay_ms
drop_probability
failure_enabled
max_concurrent_requests?
start_time?
end_time?
seed?
```

Fault injection must be explicit and disabled by default. It must not permanently modify server configuration.

---

## M9 <- M1/M3/M4/M6: Telemetry Contract

Modules emit normalized `TelemetryEvent` records:

```text
event_type
request_id?
server_id?
timestamp
latency_ms?
bytes?
status?
strategy?
metadata
```

Minimum event types:

```text
REQUEST_SENT
ROUTE_SELECTED
REQUEST_FORWARDED
RESPONSE_RECEIVED
REQUEST_FAILED
HEALTH_CHANGED
SERVER_SNAPSHOT
```

M9 is the owner of aggregate metrics. Producers must not maintain competing global metric definitions.

---

## M9 -> M10: Dashboard Read Contract

M10 receives read-only data such as:

```text
current_server_states
recent_route_decisions
traffic_distribution
latency_summary
throughput
loss_rate
experiment_comparison
```

M10 must not directly access sockets, server internals or routing objects.

---

## Core Dependency Chain

```text
M1 -> M2 -> M4 -> M3
             |
             v
             M5
             ^
             |
             M7 <- M6

M8 -> M3/M4
M1/M3/M4/M6 -> M9 -> M10
```

---

## Contract Rules

1. No module imports another module's private implementation files.
2. Shared models live in M2 or a clearly defined shared-contract package.
3. Routing algorithms return decisions; they never perform I/O.
4. Monitoring observes; it does not mutate routing state.
5. Dashboard reads; it does not control routing.
6. Fault injection is disabled unless explicitly configured.
7. Request IDs must survive the complete request path.
8. Metrics must be based on emitted telemetry, not UI state.
9. Tests for a module should be runnable without starting the entire system whenever possible.
10. A module is complete only when its README completion gate is satisfied.