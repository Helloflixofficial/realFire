# Technical Assignment: Executive Write-Up
**AI Agent for Automated Lead & Patient Intake, Enrichment, and Outreach**

---

## 1. Architecture Decisions & Why

### A. Canonical Schema Contract (`UnifiedRecord` via Pydantic v2)
* **Decision:** Enforce a strict canonical schema boundary immediately after raw ingestion, normalizing disparate payloads (LinkedIn CSV flat rows and FHIR R4 nested JSON trees) into a single strongly typed `UnifiedRecord`.
* **Why:** Ingesting heterogeneous, unvalidated schemas directly into LLM reasoning prompts leads to prompt bloat, high token costs, hallucinated dictionary keys, and fragile downstream integrations. Pydantic v2 provides microsecond-level validation and explicit field contracts (`id`, `source`, `name`, `contact_info`, `context`, `priority_signal`, `raw_payload`), decoupling upstream schema variance from core agent reasoning.

### B. Deconstructed 3-Step State Machine vs. Single "Prompt-and-Done"
* **Decision:** Rather than relying on a single monolithic prompt to classify, route, draft, and enforce safety guardrails, the agent executes an explicit 3-step state machine:
  1. **Step 1: Context Analyzer & Completeness Quality Gate** (`Step1Analysis`): Audits channel reachability, calculates a data completeness score (0.0 to 1.0), evaluates seniority / clinical chronicity, and assigns triage (`HOT`, `WARM`, `COLD`, `HIGH_CLINICAL_URGENCY`, `ROUTINE_CARE`, `DATA_INCOMPLETE`).
  2. **Step 2: Policy & Action Router** (`Step2Action`): Deterministically decides outreach channel, voice/tone calibration, and human escalation flags (`escalate_flag=True/False`).
  3. **Step 3: Message Generator & Guardrail Critic** (`Step3Message`): Generates a hyper-personalized message followed immediately by an automated HIPAA/B2B compliance self-critique pass.
* **Why:** Monolithic prompts suffer from "attention diffusion" and output drift. Decomposing the agent into discrete nodes guarantees that each business decision is modular, auditable, independently testable, and capable of automated self-correction before emitting text.

### C. Automated HIPAA & Compliance Self-Critique Gate
* **Decision:** Implement a deterministic self-critique evaluator that intercepts drafted messages before downstream dispatch. If the recipient is a clinical patient, it strictly prohibits exposing specific diagnoses or condition names (e.g., Diabetes, Coronary Heart Disease) over insecure channels (SMS, cleartext email), automatically rewriting the draft to direct the patient securely to their authenticated portal or clinic direct line.
* **Why:** LLMs can inadvertently disclose Protected Health Information (PHI). Having an automated verification gate inside the state machine ensures compliance boundaries are respected unconditionally.

### D. Resilient Downstream Dispatch with Tenacity Exponential Backoff & DLQ
* **Decision:** Protect the pipeline at both ends:
  - **Ingress:** Malformed records (missing recipient names, uncontactable endpoints, corrupted FHIR records) are isolated into a Dead Letter Queue (`outputs/dead_letter_queue.json`).
  - **Egress:** CMS delivery uses Tenacity exponential backoff retries on transient network drops or HTTP 5xx errors.
* **Why:** Guarantees zero silent crashes and zero data loss in production environments.

---

## 2. Handling Scale (10,000+ Leads & Patients Per Day)

Scaling this pipeline from tens of records to 10,000–50,000 daily records requires transitioning from synchronous batch loops to an **event-driven distributed streaming architecture**:

```
+------------------+       +-------------------+       +-----------------------+       +-------------------+
|  Source Systems  | ----> | Kafka / AWS SQS   | ----> | Scalable Celery /     | ----> | Downstream CMS /  |
|  (CSV, FHIR Bulk)|       | Ingestion Topic   |       | Temporal Worker Pool  |       | Webhooks / DLQ    |
+------------------+       +-------------------+       +-----------------------+       +-------------------+
                                                                   |
                                                                   v
                                                       +-----------------------+
                                                       | Redis Semantic Cache  |
                                                       | & Token Bucket Limiter|
                                                       +-----------------------+
```

1. **Partitioned Asynchronous Message Queues (Kafka / AWS SQS):**
   * Decouple ingestion from agent execution. Raw events are published to partitioned Kafka topics (`intake.raw.events`).
   * Scalable consumer pools (Celery / Temporal / AWS ECS Fargate) pull batches concurrently, auto-scaling horizontally based on queue depth metrics.
2. **Bulk FHIR Streaming (`$export` Standard):**
   * Individual REST queries (`GET /Patient/{id}`) create network bottlenecks. At scale, the pipeline leverages the HL7 FHIR standard **`$export` operation** to stream compressed NDJSON files directly into object storage (S3/GCS), reading via memory-mapped streams.
3. **LLM Cost, Rate-Limiting & Latency Optimizations:**
   * **Semantic Caching:** Deploy a Redis-backed semantic cache (e.g., GPTCache). Routine follow-ups and standard B2B SDR patterns achieve >40% cache hit ratios (<15ms latency, $0 LLM token cost).
   * **Token-Bucket Rate Limiting:** Enforce distributed rate limiters across multi-key pools to avoid HTTP 429 throttling.
   * **Tiered Model Routing & Batch APIs:** Route routine, low-risk classification tasks to lightweight models (Groq Llama-3.1-8B, Gemini Flash), reserving heavy reasoning models for complex clinical triage. For non-urgent batch records, offload to asynchronous 24-hour Batch APIs for a 50% cost discount.
4. **Idempotency & Deduplication:**
   * Attach deterministic UUIDv5 hashes derived from `(source_system, source_record_id, event_timestamp)` to guarantee exactly-once processing across retries and distributed worker restarts.

---

## 3. Real PHI & HIPAA Compliance Considerations

If deployed in a live clinical environment handling Protected Health Information (PHI), the following security and regulatory controls are legally non-negotiable under HIPAA:

1. **Business Associate Agreements (BAAs) & Zero-Data-Retention (ZDR) LLMs:**
   * Never send patient data to standard public LLM endpoints.
   * Execute formal **BAAs** with enterprise HIPAA-compliant AI providers (e.g., AWS Bedrock, Azure OpenAI HIPAA edition, Google Cloud Vertex AI HIPAA).
   * Enforce **Zero Data Retention (ZDR)** configurations guaranteeing prompts and completions are never logged or stored for model training.
2. **Client-Side De-Identification & PHI Masking Vault:**
   * Prior to transmitting data to an LLM, strip the **18 HIPAA Safe Harbor Identifiers** (names, dates except year, phone numbers, email addresses, SSNs, medical record numbers).
   * Use an internal de-identification service (e.g., Microsoft Presidio or AWS Comprehend Medical) coupled with a secure tokenization vault (HashiCorp Vault). Replace identifiable fields with surrogate cryptographic tokens (`PATIENT_TOKEN_A41B`). Contact details are re-hydrated only at final delivery dispatch inside the enterprise secure perimeter.
3. **Prohibition of Cleartext PHI Across Insecure Channels:**
   * Unencrypted SMS and standard SMTP email are inherently insecure.
   * Under HIPAA’s **Minimum Necessary Rule**, outreach messages must never reference clinical diagnoses, medications, or test results.
   * All notifications must be content-neutral, directing the patient to authenticate into an encrypted patient portal (e.g., *"You have a new care update from your care team. Please log in to your secure portal at https://portal.clinic.org to review"*).
4. **End-to-End Encryption in Transit & at Rest:**
   * Enforce TLS 1.3 with strict modern cipher suites for all network communications.
   * Persist payloads, logs, and DLQ entries using AES-256 encryption with customer-managed KMS keys.
5. **Immutable Audit Trails (WORM Storage):**
   * Log all intake decisions, access timestamps, user IDs, and routing actions into Write-Once-Read-Many (WORM) storage (e.g., AWS S3 Object Lock) to satisfy HIPAA §164.312(b) audit control standards.

