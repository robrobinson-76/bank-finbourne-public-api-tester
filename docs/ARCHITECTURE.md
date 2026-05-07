# Bank FINBOURNE API Tester: Architecture

> **Status:** Scaffold — to be completed from plan.

## Core Pattern

One Pydantic model registry drives a shared service layer exposed identically via three transports.

### Three Invariants

1. **Models are the schema** — Pydantic definitions drive all validation and GraphQL SDL generation
2. **Single access point** — All FINBOURNE API calls flow through `bank_finbourne_tester.services.*`
3. **Transport parity** — MCP, REST, and GraphQL return identical results for identical inputs

## Technology Stack

- **MCP server**: fastmcp (≥0.4)
- **REST framework**: FastAPI + uvicorn
- **GraphQL**: Ariadne (≥0.23)
- **HTTP client**: httpx (async)
- **Data validation**: Pydantic v2
- **Runtime**: Python ≥3.11
- **FINBOURNE SDK**: lusid-sdk (≥2.0)

## Domain Model

FINBOURNE LUSID entities (to be defined in plan):
- Portfolios
- Instruments
- Transactions
- Holdings
- Corporate Actions
- Reference data

## Service Layer

Async functions handling all FINBOURNE API interactions. All functions return standardized error envelopes rather than raising exceptions, enabling consistent error translation at each transport boundary.

## Testing

- Direct service function validation
- REST endpoint behaviour
- GraphQL query structure
- **Cross-layer parity enforcement** — all three transports produce identical results

## Deployment

Local development via uv. Transport servers run independently on separate ports.
