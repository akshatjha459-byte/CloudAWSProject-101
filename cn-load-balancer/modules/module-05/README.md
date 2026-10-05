# M5 — Routing Algorithms

## Responsibility
Implement interchangeable server-selection policies behind one interface.

## Required
1. Round Robin
2. Least Connections
3. Weighted Round Robin / weighted selection

## Optional
Weighted Least Connections.

## Rules
Algorithms receive snapshots and return `RouteDecision`. They do not perform network I/O.

## Completion gate
A unit-test suite proves each algorithm selects servers according to its documented rule, including unhealthy-server exclusion.