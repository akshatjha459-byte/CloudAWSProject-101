# Intelligent Network Load Balancer with Dynamic Traffic Routing

A modular Computer Networks project that implements a software load balancer using real TCP/UDP sockets, multiple simulated backend servers, pluggable routing algorithms, dynamic load-aware routing, fault injection, performance measurement and visualization.

## What the system demonstrates

- TCP/UDP client-server communication
- socket-based request forwarding
- Round Robin routing
- Least Connections routing
- Weighted routing
- health-aware routing
- dynamic routing based on live server conditions
- controlled delay, loss, overload and failure scenarios
- latency, throughput, request distribution and failure analysis
- modular software architecture

## Architecture

The project is divided into ten modules:

| Module | Responsibility |
|---|---|
| M1 | Traffic Generator / Clients |
| M2 | Network Protocol & Message Model |
| M3 | Backend Server Simulator |
| M4 | Load Balancer Core |
| M5 | Routing Algorithms |
| M6 | Health & Load Monitor |
| M7 | Dynamic Routing Engine |
| M8 | Network Conditions & Fault Injection |
| M9 | Metrics & Experiment Engine |
| M10 | Dashboard & Visualization |

See `docs/CN-Architecture.md` for the canonical architecture and `docs/CN-module-contracts.md` for the interfaces that modules must obey.

## Development order

```text
M1 -> M2 -> M3 -> M4 -> M5
                         |
                         v
                    M6 -> M7
                         |
                         v
                    M8 -> M9 -> M10
```

Build and test each module independently before moving to the next dependent module.

## Repository layout

```text
cn-load-balancer/
├── docs/
│   ├── CN-Architecture.md
│   └── CN-module-contracts.md
├── modules/
│   ├── module-01/README.md
│   ├── module-02/README.md
│   └── ...
│   └── module-10/README.md
├── shared/
└── tests/
```

## Design rule

A module owns its responsibility and exposes only its documented contract. Later modules must consume earlier contracts rather than reaching into their private implementation. Planned behavior must not be represented as completed functionality.