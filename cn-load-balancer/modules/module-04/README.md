# M4 — Load Balancer Core

## Responsibility
Receive client traffic, obtain a routing decision, forward the request to the selected healthy backend, return the response, and emit telemetry.

## Owns
- listener socket
- backend registry
- connection lifecycle
- timeout handling
- request forwarding

## Does not own
Routing algorithms, dashboard rendering, experiment statistics or fault policies.

## Completion gate
A client request reaches exactly one selected healthy backend and the response returns with the original `request_id`.