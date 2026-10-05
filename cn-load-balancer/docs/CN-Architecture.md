# Intelligent Network Load Balancer with Dynamic Traffic Routing

## Project Master Architecture and Implementation Plan

**Project type:** Computer Networks implementation project  
**Development strategy:** Modular software development  
**Primary goal:** Build a working software load balancer that simulates multiple backend servers, observes their load, dynamically routes traffic, and compares routing strategies.

---

## 1. PROJECT PURPOSE

The system models a small network in which multiple clients generate TCP/UDP traffic toward a single logical entry point. The load balancer selects a healthy backend server and forwards the request. A monitoring layer continuously collects server state, while a dynamic routing engine can use that state to influence the routing algorithm.

The project must demonstrate actual Computer Networks concepts rather than only visual simulation:

- TCP/UDP sockets
- client-server architecture
- connection handling
- packet/request forwarding
- routing decisions
- load balancing
- congestion/load effects
- latency and throughput measurement
- server failure and recovery
- modular protocol and software design

---

## 2. NON-NEGOTIABLE DESIGN PRINCIPLES

### Modular boundaries
Each module owns one responsibility. A module communicates with another module only through the interfaces defined in `docs/CN-module-contracts.md`.

### Replaceability
Routing algorithms are plugins behind one common interface. The load balancer must not contain separate hard-coded implementations for every algorithm.

### No hidden cross-module state
A module must not directly modify another module's internal data structures. Shared information is exchanged through contracts/events.

### Real networking first
The core demonstration must use real local sockets. A purely mocked packet-flow animation is insufficient.

### Deterministic experiments
Traffic generation, server capacity, routing policy, and fault profiles must be configurable so the same experiment can be repeated.

### Observability is separate
Metrics and visualization observe the system; they do not control routing directly. Routing receives normalized monitor data through the routing contract.

---

## 3. CANONICAL MODULE SEQUENCE

| Module | Responsibility | Completion gate |
|---|---|---|
| **M1** | Traffic Generator / Clients | Configurable TCP/UDP traffic generation |
| **M2** | Network Protocol & Message Model | Stable request/response/event schemas |
| **M3** | Backend Server Simulator | Multiple independently configurable servers |
| **M4** | Load Balancer Core | Receives, routes and forwards traffic |
| **M5** | Routing Algorithms | Round Robin, Least Connections, Weighted policies |
| **M6** | Health & Load Monitor | Live server health/load snapshots |
| **M7** | Dynamic Routing Engine | Feedback-based route scoring/selection |
| **M8** | Network Conditions & Fault Injection | Delay, overload, packet-loss/failure scenarios |
| **M9** | Metrics & Experiment Engine | Latency, throughput, loss, distribution and comparison |
| **M10** | Dashboard & Visualization | Live topology, traffic flow and experiment results |

M4 must work with at least one routing policy before M6/M7 are required. M7 extends the routing decision; it does not replace M5's algorithm interface.

---

## 4. SYSTEM ARCHITECTURE

```text
                         +----------------------+
                         |   M10 DASHBOARD      |
                         | topology / metrics   |
                         +----------+-----------+
                                    | read-only API
                                    v
+-------------+              +------+-------+
| M1 CLIENTS  | --TCP/UDP--> | M4 LOAD      |
| traffic gen |               | BALANCER     |
+-------------+               +--+----+------+
                                  |    |
                         decision |    | telemetry
                                  |    v
                                  |  +---------+
                                  |  | M9      |
                                  |  | Metrics |
                                  |  +---------+
                                  |
                         +--------v---------+
                         | M5 Routing       |
                         | algorithms       |
                         +--------+---------+
                                  ^
                                  | server snapshots
                         +--------+---------+
                         | M7 Dynamic       |
                         | Routing Engine    |
                         +--------+---------+
                                  ^
                                  |
                         +--------+---------+
                         | M6 Health/Load   |
                         | Monitor           |
                         +-------------------+

       +-----------+   +-----------+   +-----------+
       | M3 Server |   | M3 Server |   | M3 Server |
       |     A     |   |     B     |   |     C     |
       +-----------+   +-----------+   +-----------+
             ^               ^               ^
             +---------------+---------------+
                     M8 fault profiles

M2 defines common request/response/telemetry schemas.
```

---

## 5. MODULE RESPONSIBILITIES

### M1 — Traffic Generator / Clients
Creates configurable traffic patterns: request rate, duration, payload size, protocol, client count and burst behavior. It records request IDs and timestamps but does not decide the backend.

### M2 — Network Protocol & Message Model
Defines canonical request, response, server-state and telemetry structures plus serialization/deserialization. M2 contains no routing policy.

### M3 — Backend Server Simulator
Runs multiple independently configured backend instances. Each accepts forwarded traffic, simulates processing time/capacity, tracks active connections and returns a response. It exposes health information needed by M6.

### M4 — Load Balancer Core
Owns the listening socket, backend registry, request forwarding, connection lifecycle and route invocation. It asks the routing interface for a target; it does not contain algorithm-specific logic.

### M5 — Routing Algorithms
Provides interchangeable Round Robin, Least Connections and Weighted Round Robin/Weighted selection strategies. Weighted Least Connections is an optional extension.

### M6 — Health & Load Monitor
Periodically samples backend health, active connections, capacity, latency and recent failures, producing immutable server snapshots.

### M7 — Dynamic Routing Engine
Combines M5 policy behavior with M6 observations. A simple first implementation can score servers using active connections, health, latency and capacity. No machine-learning model is required.

### M8 — Network Conditions & Fault Injection
Adds controlled delay, response-time inflation, request/packet drops, temporary server failure and overload conditions. Faults are configurable and reproducible.

### M9 — Metrics & Experiment Engine
Consumes telemetry and calculates latency, throughput, request distribution, success/failure rate, loss/timeout rate, server utilization and algorithm comparisons.

### M10 — Dashboard & Visualization
Displays topology, server health, current connections, route decisions, traffic flow and experiment results. It consumes read-only M6/M9 data and never accesses internal module state.

---

## 6. END-TO-END REQUEST FLOW

```text
M1 Client
   |
   | TCP/UDP request + request_id
   v
M4 Load Balancer
   |
   | asks M7/M5 for target
   v
Routing Decision
   |
   v
Selected M3 Server
   |
   | response
   v
M4 -> M1

Telemetry from M1/M3/M4/M6 -> M9 -> M10
```

The route decision must use the same `request_id` so M9 can calculate end-to-end metrics.

---

## 7. DYNAMIC ROUTING MODEL

The first dynamic implementation should remain understandable for a CN project. Example normalized score:

```text
score(server) =
    w_load     * normalized_active_connections
  + w_latency  * normalized_recent_latency
  + w_failure  * normalized_failure_rate
  - w_capacity * normalized_capacity
```

The engine chooses the lowest valid score among healthy servers. Weights are configuration values, not magic constants buried in code.

A simpler initial mode may use:

```text
score = active_connections / capacity
```

The key requirement is that routing reacts to observed server state rather than blindly cycling through servers.

---

## 8. NETWORK CONDITIONS AND FAULTS

M8 should support:

1. Normal balanced traffic
2. One server with higher processing delay
3. One server with reduced capacity
4. Temporary server failure
5. Request/packet loss
6. Burst traffic / congestion
7. Recovery after failure

These scenarios allow comparison between static and dynamic routing.

---

## 9. METRICS

Minimum metrics:

- total requests
- successful requests
- failed requests
- request distribution per server
- average latency
- p95 latency when sample size permits
- throughput (requests/sec)
- timeout/loss rate
- active connections per server
- server utilization estimate
- routing-decision count

For the same traffic profile, compare at least Round Robin, Least Connections, and Weighted/Dynamic Routing.

---

## 10. CONCURRENCY MODEL

The implementation may use threads, asyncio, or a hybrid model. Keep the choice consistent within module boundaries.

A practical design is:

- M1: concurrent client workers
- M3: one server task/thread per simulated server
- M4: concurrent forwarding workers/tasks
- M6: periodic monitor loop
- M9: thread-safe/event-based metrics collector

Shared counters must be synchronized appropriately.

---

## 11. FAILURE RULES

If a backend is unhealthy, M4 must not route new traffic to it.

If the chosen server fails during a request, M4 records the failure and returns an explicit error/timeout rather than silently reporting success. Any retry must be bounded and preserve the request ID.

Monitoring failure must not crash the load balancer. Dashboard failure must not stop routing. Metrics failure must not stop request forwarding.

---

## 12. DEVELOPMENT / TESTING MODES

### Local Simulation Mode — Primary
All modules run on one laptop using localhost ports. Different backend servers use different ports.

### Experiment Mode
A fixed configuration produces repeatable workloads for algorithm comparison.

### Optional Distributed Mode
M3 server instances may run on different machines later. This is optional and must not complicate the local implementation.

---

## 13. REPOSITORY STRUCTURE

```text
cn-load-balancer/
├── docs/
│   ├── CN-Architecture.md
│   └── CN-module-contracts.md
├── modules/
│   ├── module-01/ ... module-10/
├── shared/
├── tests/
└── README.md
```

Each module owns its implementation and tests. Shared code is allowed only for M2 contracts and genuinely cross-cutting primitives.

---

## 14. COMPLETION ORDER

```text
M1 -> M2 -> M3 -> M4 -> M5
                         |
                         v
                    M6 -> M7
                         |
                         v
                    M8 -> M9 -> M10
```

Do not implement M7 by bypassing M5. Do not implement M10 by reading internal module variables. Do not add a second incompatible request schema for a later module.

---

## 15. DOCUMENTATION RULE

- `docs/CN-Architecture.md` — canonical architecture and module ownership.
- `docs/CN-module-contracts.md` — canonical interfaces between modules.
- `modules/module-XX/README.md` — implementation contract and completion checklist.

If implementation differs from a contract, update the contract deliberately before changing dependent modules. Planned behavior must be clearly marked as planned.