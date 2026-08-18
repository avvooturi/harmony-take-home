# Harmony Enterprise Agent POC

A locally runnable proof of concept for a personalized enterprise AI agent.

The system demonstrates how an employee-specific agent can:

- understand authorized work context
- retrieve information across enterprise systems
- proactively identify work that needs attention
- reason over relevant context
- recommend actions with evidence
- require human approval for risky actions
- safely execute through controlled tools
- verify and audit what happened

The core design principle is:

> **Enterprise systems remain the source of truth. The AI reasons and recommends; application code controls authorization and execution.**

---

## Quick Start

### Requirements

- Docker Desktop
- Docker Compose

From the repository root:

```bash
docker compose up --build
```

Then open:

- Application: `http://localhost:3000`
- FastAPI docs: `http://localhost:8000/docs`

The core demo works without an LLM.

### Optional Local AI

Agent chat can use Ollama with:

```text
gemma3:4b
```

Install the model with:

```bash
ollama pull gemma3:4b
```

Then make sure Ollama is running before starting the demo.

The backend reaches host Ollama through:

```text
http://host.docker.internal:11434
```

The UI shows which mode handled the latest request:

- **Local AI — gemma3:4b**
- **Deterministic fallback — rules-v1**

If local inference is unavailable or times out, the application automatically falls back instead of breaking the workflow.

---

# Recommended Demo

The deepest implemented workflow is for:

**Maya Chen — Purchasing Manager**

The scenario follows a material shortage from detection all the way through a controlled ERP mutation.

## 1. Work Context

Open **Work Context** with Maya selected.

Her agent assembles authorized information from sources such as:

- ERP
- Outlook
- Calendar
- Teams
- organizational context
- long-term memory

The context is divided into:

- **Current Work** — what matters now
- **Recent Context** — relevant recent activity
- **Long-Term Memory** — selective durable information
- **Recommended Actions** — role-aware next steps

Current and recent enterprise data is retrieved on demand.

Long-term memory intentionally stores only useful durable information rather than copying every email, meeting, or ERP event.

---

## 2. Proactive Analysis

Click **Run proactive analysis**.

The demo detects that:

- Part X is projected to run out
- Production Order 4812 depends on Part X
- PO-1007 is associated with the material
- Supplier Y has reported a delay
- Supplier Z is an approved alternative

The first detection step is deterministic:

```text
ERP data
   ↓
Known shortage rule
   ↓
Potential problem
```

Once a potential problem is found, the system gathers richer authorized context and reasons about what to do:

```text
Detect
  ↓
Gather Context
  ↓
Reason
  ↓
Recommend
  ↓
Prepare Action
```

This is intentional.

A known inventory threshold does not need an LLM to decide whether it has been crossed. AI becomes useful after detection, when the system needs to interpret multiple pieces of context and recommend a response.

---

## 3. Recommendation

The resulting Attention item explains the risk and provides supporting evidence.

For the demo scenario, the recommendation is to move:

```text
PO-1007

Supplier Y
   ↓
Supplier Z
```

and notify production.

At this point **nothing has been changed in the ERP**.

The agent has only recommended/proposed an action.

---

## 4. Human Approval

Open **Approvals**.

Risky mutations require an explicit persisted approval.

Approval does not bypass authorization.

The application checks the employee's permissions again when execution occurs because permissions could have changed since the recommendation was created.

Even messages such as:

```text
approve
proceed
do it
```

inside Agent chat are not treated as authorization.

Chat instead directs the employee to the explicit approval workflow.

---

## 5. Controlled Execution

After approval, the trusted application path performs the action:

```text
Approve
   ↓
Load Approval
   ↓
Reauthorize
   ↓
Validate Action
   ↓
Idempotency Check
   ↓
Version Check
   ↓
ERP Connector
   ↓
Mutation
   ↓
Verify
   ↓
Audit
```

Two important protections are included.

### Idempotency

An idempotency key prevents the same action from executing twice if a request is retried or duplicated.

### Optimistic Concurrency

The action contains the expected PO version.

If someone changes the purchase order after the recommendation was created:

```text
expected version != current version
```

the stale write is rejected instead of overwriting newer ERP state.

---

## 6. Audit

Open **Audit** after running the scenario.

Important actions and interactions are recorded, including things such as:

- employee
- recommendation/action
- approval decision
- provider/model information
- execution result
- verification result
- failures when applicable

The application does not request or store hidden model chain-of-thought.

---

# Employee-Specific Agents

The same system behaves differently depending on the employee.

### Maya Chen — Purchasing Manager

Receives purchasing context and can propose supported purchasing actions.

### Frank Ortiz — Floor Employee

Receives production-related context and can escalate the Part X blocker, but does not have authority to modify purchase orders.

### Avery Brooks — Executive

Receives higher-level cross-functional context without purchasing mutation authority.

The goal is not one enterprise chatbot with access to everything.

The goal is:

> **Each employee receives the context and actions appropriate to their role and permissions.**

---

# Agent Chat

The Agent page lets employees ask questions about their authorized Work Context.

Example prompts:

```text
Why is Part X at risk?

What should I prioritize today?

What are my current tasks?

What is the impact on Production Order 4812?

Why should we consider Supplier Z?

What action do you recommend for the Part X shortage?
```

The flow is:

```text
Employee Question
      ↓
Authorized Work Context
      ↓
Question-Scoped Context
      ↓
LLMProvider
   /        \
Local AI   Failure
   ↓         ↓
Gemma    Deterministic
   \         /
      ↓
Response / Proposed Action
      ↓
Audit
```

The model may:

- understand questions
- summarize evidence
- reason
- recommend
- propose an action

The model may **not**:

- grant permissions
- approve actions
- directly modify ERP data
- bypass tool validation
- claim authority

---

# Local AI and Fallback

The current local provider uses Ollama with `gemma3:4b`.

Local inference may take several seconds depending on hardware and whether the model is already warm.

The application keeps generation bounded and uses a provider timeout.

If Ollama is:

- unavailable
- too slow
- missing the configured model
- returning an invalid response

the system switches to a deterministic question-aware fallback.

The fallback exists for graceful degradation.

It is not a second authorization mechanism.

---

# Architecture

The application is a modular monolith:

```text
             Next.js
                ↓
             FastAPI
                ↓
 ┌─────────────────────────────┐
 │ Authentication / AuthZ      │
 │ Work Context                │
 │ Agent                       │
 │ Proactive Detection         │
 │ Memory                      │
 │ Approvals                   │
 │ Tools                       │
 │ Audit                       │
 │ Enterprise Connectors       │
 └─────────────────────────────┘
                ↓
           PostgreSQL
```

Enterprise integrations sit behind connectors:

```text
ERP ──────────┐
Outlook ──────┤
Teams ────────┤
Knowledge ────┤
Organization ─┤
              ↓
          Connectors
              ↓
        Context / Agent
```

This keeps vendor-specific logic separate from agent orchestration and allows production integrations to replace the mock adapters later.

---

# Why a Modular Monolith?

For this proof of concept, microservices would add operational complexity without solving an existing problem.

The backend still has clear module boundaries so components can be extracted later.

I would split something into a separate service when it requires:

- independent scaling
- stronger failure isolation
- separate deployment
- specialized infrastructure
- separate team ownership

Inference and proactive/background processing would likely be early candidates.

---

# Source of Truth

Enterprise systems remain authoritative for business information such as:

```text
ERP
- inventory
- purchase orders
- production orders
- suppliers

Microsoft / enterprise systems
- email
- calendar
- meetings
- organization data
```

The agent platform owns state such as:

```text
- Agent Runs
- Memory
- Approval Requests
- Attention Items
- Audit Events
```

The POC stores mock enterprise records locally for demonstration.

A production implementation would retrieve the real data through the same connector boundaries.

---

# Safety Model

The most important boundary in the system is:

| AI / Probabilistic | Application / Deterministic |
|---|---|
| Understand | Authenticate |
| Summarize | Authorize |
| Reason | Enforce business rules |
| Recommend | Manage approvals |
| Propose actions | Validate tools |
|  | Execute |
|  | Enforce idempotency |
|  | Enforce concurrency |
|  | Verify |
|  | Audit |

In short:

> **AI reasons. Application code controls.**

Model output is treated as untrusted input.

---

# Failure Behavior

| Failure | Behavior |
|---|---|
| Employee lacks permission | Request denied |
| Permission changes before execution | Reauthorization stops execution |
| Action submitted twice | Idempotency prevents duplicate mutation |
| PO changed after recommendation | Version conflict blocks stale write |
| Local AI unavailable | Deterministic fallback |
| Local AI times out | Fallback and audit |
| Model claims it executed something | ERP remains unchanged |
| Model proposes unauthorized action | Application rejects it |
| User types `approve` in chat | Explicit approval still required |

The system is designed to:

> **Fail closed for authorization and mutations while degrading gracefully for AI availability.**

---

# Local vs Hosted Models

The demo currently prefers local Ollama inference.

The model boundary is provider-neutral, so an approved hosted model could also be used if justified by:

- model quality
- capacity
- latency
- cost
- operational simplicity
- privacy requirements

Regardless of provider choice, authorization, approvals, execution, verification, and audit remain application-owned.

---

# Scaling

The current architecture is intentionally simple.

At larger scale, likely bottlenecks include:

| Bottleneck | Possible response |
|---|---|
| LLM inference | Dedicated inference capacity / approved hosted provider |
| Backend traffic | Horizontally scale FastAPI |
| Database connections | Pooling / PostgreSQL scaling |
| Proactive jobs | Background workers / queue |
| ERP rate limits | Throttling, batching, retry |
| Microsoft API limits | Caching, batching, backoff |
| Context retrieval | Better filtering and ranking |
| Audit volume | Retention / archival |

The first step would be scaling the modular monolith horizontally.

Services would only be extracted when measured bottlenecks justify doing so.

---

# Demo Reset

Use **Reset Demo** to restore the original seeded scenario and rerun the complete workflow.

This capability is intentionally demo-only.

It is not intended to represent production transaction rollback.

A complete Docker reset can also be performed with:

```bash
docker compose down -v
docker compose up --build
```

---

# Testing

Backend:

```bash
cd backend
pip install -r requirements-dev.txt
pytest
ruff check .
```

Frontend:

```bash
cd frontend
npm install
npm run typecheck
npm run build
```

Tests cover the major safety properties, including:

- authorization
- approval enforcement
- approved/rejected actions
- idempotency
- stale writes
- proactive detection
- employee context isolation
- AI fallback
- model output unable to directly mutate ERP
- conversational approval safety
- demo reset

---

# Known Limitations

This is a proof of concept rather than a production deployment.

Current limitations include:

- demo authentication
- simple permission strings instead of full ABAC
- manually triggered proactive analysis
- mocked ERP and Microsoft integrations
- basic knowledge retrieval
- local inference latency
- only the purchasing vertical slice is deeply implemented

A production implementation would likely add:

- Entra ID / OIDC
- real ERP integrations
- Microsoft Graph
- production migrations
- background workers
- richer retrieval
- stronger policy controls
- observability
- retention/compliance controls

See [`docs/system-design.md`](docs/system-design.md) and [`docs/decisions.md`](docs/decisions.md) for deeper design details.

---

# Design Summary

```text
Enterprise Systems
       ↓
Authorized Context
       ↓
AI Reasoning
       ↓
Recommendation
       ↓
Authorization + Human Approval
       ↓
Controlled Execution
       ↓
Verification
       ↓
Audit
```

> **Use AI where ambiguity and reasoning are useful. Use deterministic application code where correctness, authorization, and safety matter.**