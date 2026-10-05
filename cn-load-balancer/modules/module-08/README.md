# M8 — Network Conditions & Fault Injection

## Responsibility
Create controlled network/server stress scenarios without permanently changing the core system.

## Faults
- artificial delay
- request/packet drops
- temporary server failure
- reduced capacity
- burst/congestion scenarios

## Rules
Faults are opt-in, configurable and reproducible. Production/default mode has no injected faults.

## Completion gate
A scripted experiment can reproduce at least one delay case and one failure/loss case.