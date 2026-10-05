# M7 — Dynamic Routing Engine

## Responsibility
Use live M6 state to make routing responsive to changing load, latency, capacity and failures while preserving the M5 strategy interface.

## First implementation
Use a configurable normalized score such as `active_connections / capacity`, then extend with latency/failure weights.

## Explainability
Every decision must provide a human-readable reason and the values used for the decision.

## Completion gate
Under an intentionally slowed or overloaded backend, traffic distribution changes compared with static Round Robin while healthy backends remain eligible.