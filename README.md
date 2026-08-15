# Harmony Enterprise Agent POC

A locally runnable vertical slice of an enterprise purchasing agent. It detects a material shortage, correlates authorized ERP, supplier-email, and policy evidence, recommends a supplier change, and waits for explicit human approval before executing an idempotent, version-checked mutation.

## Run it

Prerequisite: Docker Desktop with Compose.

```bash
docker compose up --build
```

Open `http://localhost:3000`. API docs are at `http://localhost:8000/docs`.

An LLM is optional for the deterministic demo. The provider boundary supports Ollama at `OLLAMA_URL`; the fallback produces the stable interview scenario without network access. For non-Docker development, install `backend/requirements-dev.txt`, run `uvicorn app.main:app --reload` from `backend`, then `npm install && npm run dev` from `frontend`. Local development defaults to SQLite; Docker uses PostgreSQL.

## Demo walkthrough

1. Select **Maya Chen — Purchasing Manager** and click **Run proactive analysis**.
2. Review the inventory, production-order, supplier-email, and alternate-supplier evidence.
3. Open **Approvals**. Before approval, `GET /api/erp/purchase-orders/PO-1007` still reports `SUP-Y`, version `1`.
4. Approve. The app rechecks authority, updates exactly once, verifies `SUP-Z`, version `2`, and sends a mock production notification.
5. Open **Audit** for recommendation, authorization, and execution evidence.
6. Switch to **Frank Ortiz — Floor Employee**. Purchasing analysis and PO access return `403`.

To reset the demo, run `docker compose down -v` (this deletes only the demo volume) and start it again.

## Architecture

This is a **modular monolith**: one Next.js UI, one FastAPI deployment, and one PostgreSQL database. Internal modules own identity/policy, orchestration, context, tools, approvals, proactive detection, memory, audit, and source connectors. Their narrow in-process interfaces are extraction seams if measured scale or team ownership later justifies services.

```text
UNDERSTAND → RETRIEVE_CONTEXT → REASON → PLAN → RECOMMEND
→ REQUEST_TOOL → AUTHORIZE → REQUEST_APPROVAL → EXECUTE → VERIFY → AUDIT
```

The model receives task-scoped authorized context, never database access. ERP, Outlook, and knowledge are accessed only through connectors. See [system design](docs/system-design.md) and [architecture decisions](docs/decisions.md).

## Safety and threat model

- Model responses and tool requests are untrusted input.
- Permissions are deny-by-default and enforced in application code for every tool call.
- Approval proves intent, not authority; permission is checked again at execution.
- High-risk writes cannot bypass the persisted approval gate.
- Mutations use an idempotency key (`agentRunId:action`) and optimistic object version.
- Stale versions stop execution and require reevaluation rather than overwriting changes.
- Retrieval is task- and employee-scoped.
- Audit stores concise evidence, decisions, calls, provider metadata, and outcomes—not hidden chain-of-thought.
- Demo identity is local-only. Production must validate Entra ID tokens and map immutable subjects to policy.

## Real and mocked components

**Real behavior:** policy enforcement, connector boundaries, deterministic detection, context assembly, structured run state, approval gating, reauthorization, mutation, version checks, idempotency, verification, notification workflow, selective-memory schema, and audit.

**Mock adapters:** demo header authentication, ERP, Outlook, and local documents. Microsoft Graph and real ERP adapters can implement the same contracts without changing orchestration. `OllamaProvider` supplies the local-model boundary; deterministic output keeps the core demo reliable.

## Tests and checks

```bash
cd backend
pip install -r requirements-dev.txt
pytest
ruff check .

cd ../frontend
npm install
npm run typecheck
npm run build
```

Tests cover unauthorized reads/tools, approval enforcement, rejection, exactly-once execution, duplicate idempotency keys, stale versions, proactive correlation, and audit creation.

## Infrastructure control and delegation

The POC keeps orchestration, authorization, permissions, approvals, memory, audit, tool policy/execution, and primary persistence internally controlled. PostgreSQL and the application run in the local environment. ERP, Outlook/Microsoft Graph, Entra ID, and internal document repositories are treated as existing enterprise systems and are reached through least-privilege connectors rather than recreated.

No mandatory hosted model, SaaS database, hosted agent platform, or SaaS observability dependency exists. That is a pragmatic POC choice, not a prohibition on delegation: an approved external capability may be used when it offers a concrete quality, security, operational, or cost advantage and its data boundary, privacy implications, coupling, and exit path are documented. See the [infrastructure ownership and delegation register](docs/system-design.md#infrastructure-ownership-and-delegation-register).

Redis, Kafka, and a vector database remain omitted because they do not strengthen this vertical slice.

## Known limitations

- Demo header authentication is not secure outside a local demonstration.
- Policies are permission strings, not a full ABAC engine.
- Detection is manually triggered and in-process; persisted steps provide a retry seam, but the happy-path mock notification has no retry endpoint.
- Knowledge retrieval is basic department-filtered text matching.
- Startup table creation replaces migrations for the POC.
- Only the purchasing vertical slice is deeply implemented.

## Production evolution

Replace demo auth with Entra ID/OIDC, add Alembic migrations, secrets management, TLS, richer policy, retention controls, signed approval events, and operational metrics. Run detection as a database-backed worker initially and add the company broker only as load demands. Add bounded retry scheduling and dead-letter handling. Use real ERP and Microsoft Graph adapters with delegated permissions. Scale the monolith horizontally first; extract modules only for demonstrated latency, throughput, isolation, or ownership needs.
