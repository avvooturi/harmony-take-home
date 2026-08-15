# System design

## Overall architecture

The POC is a modular monolith: one backend process and database, with boundaries expressed as Python modules and interfaces. Connectors can later move behind remote adapters without changing agent logic.

```mermaid
flowchart LR
  UI[Next.js UI] --> API[FastAPI API]
  subgraph M[Modular monolith]
    API --> ID[Identity and authorization]
    API --> OR[Agent orchestrator]
    OR --> CTX[Context service]
    OR --> TR[Tool registry]
    OR --> AP[Approval module]
    PRO[Proactive detector] --> OR
    CTX --> CE[ERP connector]
    CTX --> CO[Outlook connector]
    CTX --> CK[Knowledge connector]
    TR --> CE
    AP --> TR
    OR --> AU[Audit and memory]
  end
  M --> PG[(PostgreSQL)]
  OR -. optional .-> OL[Local Ollama/vLLM]
```

## User-request data flow

```mermaid
sequenceDiagram
  User->>API: Request with demo identity
  API->>Authorization: Resolve permissions
  API->>Orchestrator: Authorized request
  Orchestrator->>Context: Retrieve task-scoped data
  Context->>Connectors: ERP, Outlook, knowledge, memory
  Orchestrator->>LLM: Sanitized authorized context
  LLM-->>Orchestrator: Recommendation/tool request
  Orchestrator-->>User: Recommendation (no mutation)
```

## Proactive detection data flow

```mermaid
flowchart LR
  T[Manual trigger] --> D[Deterministic inventory check]
  D -->|threshold plus active order| E[Shortage event]
  E --> C[Authorized context gathering]
  C --> R[Reason and recommend]
  R --> F[Attention feed]
  R --> P[Pending approval]
```

## Tool execution and approval

```mermaid
stateDiagram-v2
  [*] --> Requested
  Requested --> Authorized: policy permits request
  Authorized --> PendingApproval: high-risk write
  PendingApproval --> Rejected: user rejects
  PendingApproval --> Reauthorized: user approves
  Reauthorized --> Executed: permission still present
  Executed --> Verified
  Verified --> Audited
  Reauthorized --> Denied: permission removed
```

## Failure and retry

```mermaid
flowchart TD
  A[Approved plan] --> B[PO step with idempotency key]
  B -->|version conflict| R[Mark stale and require reevaluation]
  B -->|success| C[Persist completed step]
  C --> D[Notification step]
  D -->|transient failure| E[Retry failed step only, bounded]
  D -->|success| V[Verify ERP and audit]
  E --> D
```

The current happy-path mock notification succeeds immediately. Step records and distinct idempotency keys provide the seam for bounded background retries without repeating the PO mutation.

