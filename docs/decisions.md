# Architecture decisions

## Internal control with justified delegation

**Decision:** Keep the sensitive agent control plane internally controlled while allowing existing enterprise systems and justified external capabilities behind narrow adapters. **Why:** “in-house” is a risk and control objective, not a requirement to rebuild databases, identity platforms, enterprise applications, or every model. ERP and Microsoft 365 already own authoritative business data; selected external capabilities may also outperform an internal implementation when their data boundary is acceptable. **Alternative considered:** prohibit all external dependencies or, at the other extreme, delegate orchestration and persistence to a hosted agent platform. **Tradeoff:** each external integration needs explicit vendor, data, availability, and exit analysis, but the platform retains control of authorization, approvals, memory, audit, and execution.

## Modular monolith

**Decision:** Run all modules in one FastAPI deployment. **Why:** it makes the take-home operable and transactions understandable while retaining explicit interfaces. **Alternative:** microservices. **Tradeoff:** independent scaling is deferred; modules can be extracted when measured scale or ownership requires it.

## Enterprise systems remain source of truth

**Decision:** read, mutate, and verify through ERP and Outlook connectors while those existing enterprise systems remain authoritative. **Why:** agent memory cannot supersede operational records, and recreating established ERP/mail capabilities would be expensive and less trustworthy. **Alternative:** copy operational state into an agent-owned system. **Tradeoff:** connector availability affects actions, but avoids divergent truth and keeps source-system permissions enforceable.

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

**Decision:** ERP, Outlook, identity, knowledge, and model implementations sit behind focused adapters. **Why:** existing ERP APIs, Microsoft Graph/Entra, internal repositories, and approved model providers can be used without moving their vendor-specific behavior into orchestration. Each adapter defines the minimum data allowed to cross its boundary. **Alternative:** direct vendor/API access throughout agent code. **Tradeoff:** small interface overhead in exchange for replaceability, testability, policy control, and an exit path.

## External model inference is optional and untrusted

**Decision:** support local inference and permit an approved external model provider only through `LLMProvider`; neither is an authority. **Why:** model quality, capacity, and operating economics may justify delegation, while some data classes may require local inference or deterministic processing. **Alternative:** mandate one self-hosted model or tightly couple to one hosted API. **Tradeoff:** provider-neutral prompts and structured outputs require some normalization, but sensitive controls remain stable and workloads can choose an appropriate privacy boundary.

## Reuse maintained infrastructure rather than rebuild commodities

**Decision:** self-host maintained open-source components such as PostgreSQL, FastAPI, and Next.js instead of authoring equivalents. **Why:** internal control means controlling deployment, configuration, access, and data—not owning every line of infrastructure code. **Alternative:** custom database, web framework, or runtime components. **Tradeoff:** introduces supply-chain and patch-management duties but greatly reduces implementation and reliability risk.
