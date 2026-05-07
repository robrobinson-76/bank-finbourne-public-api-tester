# bank-finbourne-public-api-tester — Claude Code Project Context

## Purpose

This project tests and demonstrates interaction with the FINBOURNE public API (LUSID), exposing a unified access layer through three transports — MCP, REST, and GraphQL — while maintaining a shared data model and service layer. The domain covers FINBOURNE's investment management platform including portfolios, transactions, holdings, instruments, and corporate actions.

## Key Documentation

- **docs/ARCHITECTURE.md** — current-state design, layers, domain model, service API, and deployment patterns
- **docs/AGENTS.md** — MCP tool reference with parameter formats and best practices
- Planning documents (reference-only, do not modify): any PLAN*.md files in docs/

New developers should start with ARCHITECTURE.md for codebase orientation, then review AGENTS.md before writing queries or extending MCP tools.

## Quick Start

The project uses uv for dependency management:

```bash
uv sync
cp .env.example .env   # fill in FINBOURNE credentials
pytest tests/ -v
```

Three transports run independently: MCP via stdio, REST on port 8000, and GraphQL on port 8001.

## Critical Constraints

- All FINBOURNE API calls must route through the service layer (`bank_finbourne_tester.services.*`)
- MCP server is read-only — no mutation tools
- No query logic in transport layers (MCP tools, REST routers, GraphQL resolvers call services only)
- Maintain transport parity — all three interfaces must return identical results for identical inputs
- No ad-hoc entity additions without updating the model registry

## Architecture Pattern

```
FINBOURNE Public API
        ↓
  Pydantic Models (models/)
        ↓
   Service Layer (services/)
   ↙        ↓        ↘
MCP        REST      GraphQL
```

The codebase is located at `C:\dev\clio-git\bank-finbourne-public-api-tester\`.
