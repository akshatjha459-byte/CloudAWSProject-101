# M9 — Metrics & Experiment Engine

## Responsibility
Convert telemetry into comparable network-performance measurements.

## Required metrics
- request count
- success/failure count
- latency
- throughput
- loss/timeout rate
- per-server distribution
- active connections
- utilization estimate

## Experiment rule
Algorithm comparisons must use the same traffic configuration and fault profile.

## Completion gate
Given a recorded run, M9 produces a summary that can compare at least Round Robin, Least Connections and Dynamic/Weighted routing.