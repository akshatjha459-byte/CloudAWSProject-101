# M10 — Dashboard & Visualization

## Responsibility
Present the network topology, live server state, route decisions, packet/request flow and experiment results.

## Displays
- clients -> load balancer -> servers
- healthy/unhealthy state
- active connections
- traffic distribution
- latency/throughput/loss
- routing strategy
- recent decisions
- algorithm comparison

## Rules
Dashboard is read-only with respect to core routing state. It must not directly access sockets, server internals or M9 storage internals.

## Completion gate
A user can watch traffic flow and inspect the performance difference between at least two routing policies during a live or recorded experiment.