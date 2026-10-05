# M3 — Backend Server Simulator

## Responsibility
Provide multiple independent backend servers that accept forwarded traffic and simulate different capacities/processing times.

## Configuration
Each server has:
- `server_id`
- host/port
- capacity
- base processing delay
- weight
- health state

## Behavior
Track active connections, request count, failures and response time. Expose a health probe for M6.

## Completion gate
At least three servers can run concurrently and respond independently to forwarded requests.