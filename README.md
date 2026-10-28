# AI Agent for Automated Lead & Patient Intake, Enrichment, and Outreach

> **Production-grade, end-to-end Python pipeline unifying B2B sales leads and healthcare clinical records into an autonomous 3-step AI agent reasoning loop with strict contract validation, guardrails, and resilient downstream delivery.**

---

## 1. Executive Summary & Architecture Overview

Modern enterprise automation teams frequently bridge customer acquisition workflows (e.g., LinkedIn Sales Navigator prospects) and clinical care coordination (e.g., EMR/EHR patient intake). While their domain rules and compliance constraints differ radically, their operational topology is isomorphic:
1. **Raw ingestion** from heterogeneous sources.
2. **Harmonization** into a canonical internal schema.
3. **Multi-step autonomous reasoning** to qualify, route, draft, and enforce safety guardrails.
4. **Resilient dispatch** into downstream operational systems (CMS / CRM) with full auditability.

```
+-------------------------------------------------------------------------------------------------------+
|                                    STAGE 1: INGESTION & UNIFICATION                                   |
|                                                                                                       |
|  +-------------------------+     +-------------------------------+     +---------------------------+  |
|  |  Source A: LinkedIn CSV |     | Source B: SMART FHIR R4 API   |     | Validation & Triage Gate  |  |
|  |  (Sales Navigator Data) |     | (Patient, Condition, Appts)   |     | (Pydantic v2 Contract)    |  |
|  +------------+------------+     +---------------+---------------+     +-------------+-------------+  |
|               |                                  |                                   |                |
|               +-----------------+----------------+                                   |                |
|                                 |                                                    |                |
|                                 v                                                    v                |
|                   +---------------------------+                      +-------------------------------+|
|                   | UnifiedRecord Canonical   |                      | Dead Letter Queue (DLQ)       ||
|                   | Contract (src/schemas.py) |                      | (outputs/dead_letter_queue)   ||
|                   +-------------+-------------+                      +-------------------------------+|
+---------------------------------|---------------------------------------------------------------------+
                                  |
                                  v
+-------------------------------------------------------------------------------------------------------+
|                                  STAGE 2: MULTI-STEP AI AGENT LOOP                                    |
|                                                                                                       |
|  +------------------------------------+  +----------------------------------+  +-------------------+  |
|  | Node 1: Context Analyzer & Gate    |  | Node 2: Action & Policy Router   |  | Node 3: Generator |  |
|  | - Channel reachability audit       |->| - Optimal channel selection      |->|   & Guardrail     |  |
|  | - Seniority / clinical urgency     |  | - Voice & tone calibration       |  | - Draft outreach  |  |
|  | - Output: Step1Analysis            |  | - Escalation flag determination  |  | - HIPAA PHI critic|  |
|  +------------------------------------+  | - Output: Step2Action            |  | - Draft refinement|  |
|                                          +----------------------------------+  +---------+---------+  |
+------------------------------------------------------------------------------------------|------------+
                                                                                           |
                                                                                           v
+-------------------------------------------------------------------------------------------------------+
|                                STAGE 3: DOWNSTREAM DELIVERY & FAULT RECOVERY                          |
|                                                                                                       |
|  +------------------------------------+  +----------------------------------+  +-------------------+  |
|  | DownstreamCMSPayload Construction  |  | Tenacity Exponential Backoff     |  | Mock CMS Receiver |  |
|  | - UUID delivery_id & UTC timestamp |->| - Retry on transient 503 / error |->| (FastAPI Endpoint)|  |
|  | - Attached AgentReasoningTrace     |  | - Exponential wait (1s -> 4s)    |  | - Disk JSON store |  |
|  | - Strict Pydantic contract         |  | - Visible retry warning logs     |  | - Audit receipt   |  |
|  +------------------------------------+  +----------------------------------+  +-------------------+  |
+-------------------------------------------------------------------------------------------------------+
```

---

## 2. Quickstart & 1-Command Execution

This project is built to run out-of-the-box on Python 3.10+ without requiring any paid API subscriptions or credit cards.

### Step 1: Clone & Setup Virtual Environment
```bash
# Clone repository or navigate to workspace
git clone <your-repo-url>
cd "Project Submit"

# Create and activate virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install lightweight dependencies
pip install -r requirements.txt
```

### Step 2: Configure Environment (Optional)
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
> **Zero-Configuration Mode:** If you do not provide any API keys, the system **automatically runs in deterministic heuristic fallback mode**, executing the exact same 3-step state machine, reasoning traces, guardrail critiques, and CMS deliveries.
>
> **To use Live LLMs:** Simply drop in your free-tier key into `.env`:
> - **Groq:** `GROQ_API_KEY=gsk_...` (uses `llama-3.3-70b-versatile` or `llama-3.1-8b-instant`)
> - **Google Gemini:** `GEMINI_API_KEY=AIzaSy...` (uses `gemini-2.5-flash`)
> - **Ollama:** Set `LLM_PROVIDER=ollama` (uses local offline model `llama3.2`)

### Step 3: Run the Complete Pipeline
```bash
python main.py
```

The orchestrator will:
1. Ingest `data/mock_leads.csv` and pull live synthetic patients from `https://r4.smarthealthit.org`.
2. Normalize records and quarantine corrupt rows into `outputs/dead_letter_queue.json`.
3. Run each record through the 3-step Agent loop.
4. Deliver to the Mock CMS with Tenacity retry backoff (including simulated HTTP 503 recovery on record #3).
5. Output full audit records to `outputs/sample_end_to_end_results.json` and logs to `outputs/pipeline_execution.log`.

### Step 4: Open the Live Web Application & Dashboard

Launch the interactive web server:
```bash
# Option A: Run dedicated server launcher
python server.py

# Option B: Run pipeline and launch server in 1 command
python main.py --serve
```

Then open your browser to:
- **Web Dashboard:** [http://127.0.0.1:8000](http://127.0.0.1:8000)
  - Interactive glassmorphic dashboard visualizing all 33 delivered records.
  - Live filter pills (B2B Leads, Patients, HOT leads, High Urgency cases, DLQ).
  - Search bar across names, clinics, conditions, and channels.
  - Interactive **"Inspect Trace"** modal showing Step 1 Qualification, Step 2 Routing, Step 3 Guardrail Critique & Personalized Message, and CMS Receipts.
- **Interactive OpenAPI / Swagger Documentation:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc Documentation:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)


---

## 3. Project Directory Structure

```
├── .env.example                      # Configuration template (Groq, Gemini, Ollama, CMS, Webhook)
├── requirements.txt                  # Pinned dependencies (pydantic, httpx, tenacity, fastapi, rich)
├── README.md                         # Architecture documentation & Executive Write-Up
├── main.py                           # End-to-end orchestrator & rich console reporting
├── data/
│   └── mock_leads.csv                # 10 realistic B2B prospects + 1 corrupt test row
├── src/
│   ├── __init__.py                   # Package initialization
│   ├── schemas.py                    # Strict Pydantic v2 contracts (Stages 1, 2, and 3)
│   ├── ingest.py                     # Resilient CSV parser + live SMART FHIR R4 client + DLQ router
│   ├── llm_client.py                 # Multi-provider adapter (Groq, Gemini, Ollama, Heuristic Fallback)
│   ├── agent.py                      # 3-step Agent state machine (Analyzer -> Router -> Guardrail Critic)
│   ├── mock_cms.py                   # FastAPI CMS receiver (POST /api/v1/cms/records) & persistence
│   └── deliver.py                    # Tenacity retry client + transient 503 test + webhook.site dual-push
└── outputs/                          # Generated automatically upon execution
    ├── sample_end_to_end_results.json# 25+ comprehensive traces (Input -> Agent Steps -> Message -> Receipt)
    ├── cms_delivered_records.json    # Records persisted in the downstream mock CMS
    ├── dead_letter_queue.json        # Isolated malformed records with exact error reasons
    └── pipeline_execution.log        # Full verbose execution log with color and timestamps
```

---

## 4. Pipeline Stages: In-Depth Technical Specification

### STAGE 1: Ingestion & Normalization (`src/ingest.py`)
Normalizes disparate schemas into a single canonical Pydantic model `UnifiedRecord`:

```python
class UnifiedRecord(BaseModel):
    id: str                                            # Unique canonical identifier
    source: Literal["linkedin_csv", "smart_fhir_r4"]   # Provenance
    name: str                                          # Recipient full name (validated non-blank)
    contact_info: ContactInfo                          # Normalized email, phone, linkedin_url, address
    context: str                                       # Structured summary (B2B bio/role OR clinical conditions/visits)
    priority_signal: str                               # High-value extracted heuristics
    raw_payload: Dict[str, Any]                        # Full unmodified source payload for audit lineage
```

- **Source A (LinkedIn Sales Navigator CSV):**
  - Uses resilient column aliasing supporting `first_name`/`First Name`, `job_title`/`Title`, `email`/`Work Email`, etc.
  - Generates 10 realistic B2B prospects (VP Engineering, CTO, Head of Growth, RevOps, CMO) plus 1 corrupt row.
- **Source B (SMART Health IT FHIR R4 Sandbox):**
  - Queries `GET https://r4.smarthealthit.org/Patient?_count=15`.
  - Performs secondary sub-queries per patient: `GET /Condition?patient={id}&_count=5` and `GET /Appointment?patient={id}&_count=5`.
  - Parses complex HL7 structures: `HumanName`, `ContactPoint` telecoms, active vs. resolved condition codings, and appointment statuses into clinical summaries.

### STAGE 2: Multi-Step AI Agent Loop (`src/agent.py`)
Rather than a naive single prompt, each record traverses a sequential state machine:

1. **Step 1 — Context Analyzer & Data Quality Gate (`Step1Analysis`):**
   - Assesses contact channel reachability and computes a data completeness score (0.0 to 1.0).
   - Evaluates seniority, tech focus, or clinical chronicity.
   - Assigns triage classification: `HOT`, `WARM`, `COLD`, `HIGH_CLINICAL_URGENCY`, `ROUTINE_CARE`, or `DATA_INCOMPLETE`.
   - Logs structured `qualification_rationale`.

2. **Step 2 — Action & Policy Router (`Step2Action`):**
   - Evaluates Step 1 outputs against operational policies.
   - Determines `recommended_channel`: `email`, `linkedin_dm`, `sms`, `phone_call`, `clinical_escalation_queue`, or `manual_enrichment_queue`.
   - Calibrates `tone`: `consultative_executive`, `empathetic_clinical`, `urgent_care_coordination`, `professional_concise`.
   - Sets `escalate_flag`: `True` for high clinical risk, C-suite prospects, or incomplete data.
   - Logs structured `routing_rationale`.

3. **Step 3 — Message Generator & Guardrail Critic (`Step3Message`):**
   - Generates tailored outreach draft.
   - **Self-Critique & Compliance Guardrail:**
     - **Healthcare Rule:** Strictly prohibits exposing specific clinical diagnoses or condition names (e.g. Diabetes, Osteoporosis, Mental Health) in cleartext over SMS/Email. Directs patient securely to their authenticated portal or clinic direct line.
     - **B2B Rule:** Prevents aggressive claims, aligns with prospect role.
   - If an issue is flagged, the agent applies self-correction to refine the draft before final emission.
   - Assembles the complete `AgentReasoningTrace`.

### STAGE 3: Resilient Downstream CMS Delivery (`src/deliver.py` & `src/mock_cms.py`)
- Emits a strictly validated `DownstreamCMSPayload` containing metadata, reasoning traces, and action plans.
- Mock CMS receives payloads at `POST /api/v1/cms/records`, stores them in `outputs/cms_delivered_records.json`, and returns an immutable `CMSReceipt`.
- Supports dual-push to `WEBHOOK_SITE_URL` if configured.

---

## 5. Non-Negotiable Resilience & Failure Demonstrations

### Failure Case A: Corrupted / Malformed Ingestion Data
- **Trigger:**
  1. Row 11 in `data/mock_leads.csv` lacks recipient name and all contact information.
  2. Injected synthetic corrupt FHIR record with empty name array and empty telecoms.
- **Handling:** Pydantic validation cleanly intercepts the anomalies without crashing the pipeline. Both rows are isolated and written to `outputs/dead_letter_queue.json` with explicit diagnostics:
  ```json
  {
    "record_id": "lead_csv_011",
    "source": "linkedin_csv",
    "error_reason": "Row 11 rejected: Missing recipient name and valid contact endpoints (name='', email='None', linkedin='None')",
    "timestamp_utc": "2026-10-28T11:09:28.161513+00:00"
  }
  ```

### Failure Case B: Transient Downstream 503 Outage & Exponential Retries
- **Trigger:** Record #3 (`lead_csv_003`) triggers a simulated HTTP 503 Service Unavailable on attempt 1.
- **Handling:** Governed by `tenacity` exponential backoff (`stop_after_attempt(3)`, `wait_exponential(multiplier=1, min=1, max=4)`):
  ```
  2026-10-28 16:39:43,010 [WARNING] [intake_pipeline.deliver] [FAILURE DEMO - Case B] Simulating transient HTTP 503 Service Unavailable from downstream CMS on record 'lead_csv_003' (Attempt 1/3)!
  2026-10-28 16:39:43,010 [WARNING] [intake_pipeline.deliver] [RESILIENCE RETRY] CMS delivery attempt #1 failed. Retrying with exponential backoff (Next delay: 1.0s)...
  2026-10-28 16:39:44,010 [INFO] [intake_pipeline.deliver] [RESILIENCE SUCCESS] Retry succeeded for record 'lead_csv_003' after transient recovery on attempt 2!
  ```

---

## 6. Executive Write-Up

### Part 1: Architecture Decisions & Why

1. **Canonical Schema Contract (`UnifiedRecord`):**
   *Why:* Ingesting heterogeneous schemas directly into an AI reasoning prompt leads to prompt bloat, high latency, hallucinated keys, and fragile downstream integrations. By standardizing diverse inputs into a typed Pydantic v2 canonical model upfront, we enforce strict schema boundaries at the ingestion perimeter and decouple source system changes from agent logic.
2. **Deconstructed 3-Step State Machine vs. Single Prompt-and-Done:**
   *Why:* A single massive prompt attempting qualification, routing, drafting, and policy enforcement frequently suffers from "attention diffusion" and output drift. Decomposing the agent into three focused stages (Data Gate -> Policy Router -> Critic-Guarded Generator) guarantees that each operational decision is isolated, auditable, and testable independently.
3. **Automated Guardrail Critic Node:**
   *Why:* Direct LLM text generation is dangerous in regulated environments. Placing an automated self-critique pass directly after generation ensures that sensitive PHI (e.g. diagnoses) is caught and scrubbed before leaving the application boundary.
4. **Decoupled Delivery with DLQ & Tenacity:**
   *Why:* Real-world networks experience transient outages. A synchronous pipeline without retry policies or dead letter queues leads to silent data loss and cascading worker failures. Isolating bad data in a DLQ and retrying transient downstream errors guarantees high data integrity.

---

### Part 2: Handling Scale (10,000+ Leads & Patients Per Day)

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

1. **Asynchronous Message Streaming (Kafka / AWS SQS):**
   - Ingestion jobs publish raw payloads to a partitioned Kafka topic (`intake.raw.events`).
   - Consumer worker pools (e.g., Celery, Temporal, or AWS ECS Fargate tasks) process records concurrently across partitions with horizontal auto-scaling based on queue depth.
2. **Bulk Data APIs (HL7 FHIR `$export`):**
   - Individual REST queries (`GET /Patient/{id}`) hit HTTP connection bottlenecks. At scale, use the FHIR standard **`$export` operation** to stream compressed NDJSON files directly into AWS S3, parsing them via memory-mapped streams.
3. **LLM Cost & Latency Optimization:**
   - **Semantic Caching:** Deploy a Redis-backed semantic cache (e.g., GPTCache). Common profiles (e.g. standard B2B SDR inquiries or routine annual checkup notices) hit cache with <10ms response time and $0 LLM token cost.
   - **Token-Bucket Rate Limiting:** Enforce distributed rate limiters across LLM API keys to prevent HTTP 429 throttling.
   - **Batch API Offloading:** For non-urgent records (routine care and cold leads), dispatch bulk requests using provider Batch APIs (e.g., Groq Batch or OpenAI Batch) for a 50% discount and dedicated throughput.
4. **Idempotency & Deduplication:**
   - Attach deterministic UUIDv5 hashes derived from `(source_system, source_record_id, event_timestamp)` to ensure exactly-once processing across retries.

---

### Part 3: Real PHI & HIPAA Compliance Considerations

If this pipeline were deployed in a clinical environment handling Protected Health Information (PHI), the following security and regulatory controls are legally non-negotiable under HIPAA:

1. **Business Associate Agreements (BAAs) & Zero-Data-Retention LLMs:**
   - Never send raw patient data to standard public LLM endpoints (e.g. consumer ChatGPT or free cloud tiers).
   - Execute formal **BAAs** with HIPAA-compliant enterprise LLM providers (e.g., AWS Bedrock, Azure OpenAI, or Google Cloud Vertex AI HIPAA editions).
   - Enforce **Zero Data Retention (ZDR)** configurations ensuring prompts and completions are never logged or used for model retraining.
2. **Client-Side De-Identification & PHI Masking Vault:**
   - Prior to sending any text to an LLM, strip the **18 HIPAA Safe Harbor Identifiers** (names, geographic subdivisions smaller than state, dates except year, phone numbers, email addresses, SSNs, medical record numbers).
   - Use an internal tokenization vault (e.g., HashiCorp Vault or Presidio) to substitute names with surrogate tokens (`PATIENT_TOKEN_A41B`). Only re-hydrate recipient contact details at the final dispatch phase inside the secure enterprise boundary.
3. **Prohibition of Cleartext PHI in Outbound Channels:**
   - Unencrypted SMS and standard SMTP email are fundamentally insecure protocols.
   - Under HIPAA’s Minimum Necessary Rule, SMS and email messages must **never** reference clinical diagnoses, medications, or test results (e.g., avoid "Your blood glucose results indicate diabetes").
   - Outreach must direct the patient to an authenticated, encrypted patient portal (e.g., "You have a new care update from your care team. Please log in to your secure portal at https://portal.clinic.org to review").
4. **Encryption in Transit & at Rest:**
   - Enforce TLS 1.3 with modern cipher suites for all network communications.
   - Encrypt all persisted payloads, logs, and DLQ entries with AES-256 using customer-managed KMS keys.
5. **Immutable Audit Trails (WORM Storage):**
   - Log all intake decisions, access timestamps, user IDs, and routing actions into Write-Once-Read-Many (WORM) storage (e.g., AWS S3 Object Lock) to satisfy HIPAA §164.312(b) audit control standards.

---

## 7. Verification & Sample Test Run

Execute `python main.py` to inspect the generated outputs:
- **Sample Run Results:** `outputs/sample_end_to_end_results.json`
- **Mock CMS Persisted Records:** `outputs/cms_delivered_records.json`
- **Dead Letter Queue:** `outputs/dead_letter_queue.json`
- **Execution Log:** `outputs/pipeline_execution.log`
