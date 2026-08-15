# Architecture decisions

## Modular monolith

**Decision:** Run all modules in one FastAPI deployment. **Why:** it makes the take-home operable and transactions understandable while retaining explicit interfaces. **Alternative:** microservices. **Tradeoff:** independent scaling is deferred; modules can be extracted when measured scale or ownership requires it.

## Enterprise systems remain source of truth

**Decision:** mutate and verify through ERP/Outlook connectors. **Why:** agent memory cannot supersede authoritative records. **Alternative:** copy operational state into an agent store. **Tradeoff:** connector availability affects actions, but avoids divergent truth.

## Authorization outside the model

**Decision:** deny-by-default application policy checks every tool invocation and checks again after approval. **Why:** model output is untrusted input. **Alternative:** authorization instructions in prompts. **Tradeoff:** policies require explicit maintenance but are deterministic and testable.

## Query structured ERP data directly

**Decision:** connector queries rather than embeddings for ERP records. **Why:** exact fields, versions, and relationships matter. **Alternative:** vector retrieval. **Tradeoff:** natural-language flexibility is lower, while correctness and explainability improve.

## Human approval between planning and mutation

**Decision:** high-risk write tools require a persisted approval. **Why:** recommendation and authority are separate concerns. **Alternative:** autonomous execution. **Tradeoff:** adds latency but provides clear accountability.

## Persist plans and steps

**Decision:** store run state and independently retryable steps. **Why:** conversation history is not reliable workflow state. **Alternative:** keep state in model context. **Tradeoff:** more tables, much stronger recovery and auditability.

## Simple database-backed worker seam

**Decision:** manually trigger deterministic detection and persist its work. **Why:** Kafka adds little to one demonstration flow. **Alternative:** Kafka/Redis queue. **Tradeoff:** lower throughput; production can add an enterprise broker behind the module boundary.

## Selective long-term memory

**Decision:** memory has explicit type, source, importance, and expiry. **Why:** storing every conversation increases privacy and relevance risk. **Alternative:** automatic transcript retention. **Tradeoff:** fewer remembered details, better governance.

## Connector boundaries

**Decision:** ERP, Outlook, and knowledge implementations sit behind focused adapters. **Why:** mock sources can later be replaced by ERP APIs and Microsoft Graph. **Alternative:** direct database access throughout agent code. **Tradeoff:** small interface overhead in exchange for replaceability and policy control.

