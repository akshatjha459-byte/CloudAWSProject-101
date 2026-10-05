# M1 — Traffic Generator / Clients

## Responsibility
Generate configurable TCP/UDP traffic toward the load balancer. M1 models multiple clients and traffic patterns; it does not choose backend servers.

## Inputs
- target host/port
- TCP or UDP
- client count
- request rate / burst size
- payload size
- duration
- timeout

## Outputs
`TrafficRequest` records defined by M2 and telemetry events for sent/completed/failed requests.

## Must support
- single-client mode
- concurrent clients
- configurable request rate
- unique `request_id`
- reproducible payload generation
- graceful shutdown

## Must not
- import routing algorithms
- select backend servers
- directly modify M3 state

## Completion gate
A repeatable command can generate a known number of TCP/UDP requests and produce request-level results.