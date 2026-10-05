# M2 — Network Protocol & Message Model

## Responsibility
Own the canonical request, response, telemetry, server snapshot and configuration schemas used by the project.

## Core models
- `TrafficRequest`
- `TrafficResponse`
- `RouteDecision`
- `ServerSnapshot`
- `FaultProfile`
- `TelemetryEvent`

## Rules
Schemas must be independent of M3/M4 implementation details. Serialization must be deterministic and validated.

## Completion gate
Every core object can be serialized/deserialized without losing required fields, and invalid messages are rejected clearly.