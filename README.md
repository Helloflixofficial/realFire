# AI Agent for Automated Lead & Patient Intake, Enrichment, and Outreach

> **Production-grade, end-to-end Python pipeline unifying B2B sales leads and healthcare clinical records into an autonomous 3-step AI agent reasoning loop with strict contract validation, guardrails, and resilient downstream delivery.**

[![Live Web App](https://img.shields.io/badge/Live%20Demo-realfire.vercel.app-237359?style=for-the-badge&logo=vercel)](https://realfire.vercel.app)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2.0+-E92063?style=for-the-badge&logo=pydantic)](https://docs.pydantic.dev)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB?style=for-the-badge&logo=python)](https://python.org)

---

## 1. Executive Summary & Architecture Overview

Modern enterprise automation teams frequently bridge customer acquisition workflows (e.g., LinkedIn Sales Navigator prospects) and clinical care coordination (e.g., EMR/EHR patient intake). While their domain rules and compliance constraints differ radically, their operational topology is isomorphic:
1. **Raw ingestion** from heterogeneous sources.
2. **Harmonization** into a canonical internal schema (`UnifiedRecord`).
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
|  |                                    |  | - Output: Step2Action            |  | - Draft refinement|  |
|  +------------------------------------+  +----------------------------------+  +---------+---------+  |
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

## 2. Command Reference & Instructions

Here is the complete reference table for running, testing, and developing this application:

| Purpose | Command | Description |
|---|---|---|
| **Start Web Server & UI** | `python server.py` | Launches FastAPI server & Dashboard on `http://127.0.0.1:8000` |
| **Run Complete AI Pipeline** | `python main.py` | Ingests CSV & live FHIR $\rightarrow$ runs 3-step AI loop $\rightarrow$ delivers to CMS |
| **Pipeline + Server in 1 Command** | `python main.py --serve` | Runs the full pipeline first, then starts the web server |
| **Run Verification Test Suite** | `python test_pdf_requirements.py` | Verifies 100% of PDF technical assignment requirements in ~30s |
| **Test LLM API Connectivity** | `python -c "from src.llm_client import LLMClient; c = LLMClient(); print(c.provider, c.groq_model); print(c.generate_json('System', 'Return JSON: {\"status\": \"ok\"}'))"` | Pings active LLM provider (Groq / Gemini / Heuristic) |
| **Check Server Health API** | `python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"` | Liveness check on local port 8000 |

---

## 3. Step-by-Step Setup Guide

This project is built to run out-of-the-box on Python 3.10+ without requiring any paid API subscriptions or credit cards.

### Step 1: Clone & Setup Virtual Environment
```bash
# Clone repository
git clone https://github.com/Helloflixofficial/realFire.git
cd realFire

# Create and activate virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux / macOS:
source venv/bin/activate

# Install lightweight dependencies
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Your `.env` options:
```ini
# LLM Configuration
LLM_PROVIDER=auto
# Free Groq Key (Recommended: free tier, high TPS, no credit card needed)
GROQ_API_KEY=gsk_...
GROQ_MODEL=openai/gpt-oss-120b

# Optional: Google Gemini Key
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash

# CMS & Webhook Delivery
MOCK_CMS_HOST=127.0.0.1
MOCK_CMS_PORT=8000
WEBHOOK_SITE_URL=

# Pipeline Settings
SIMULATE_TRANSIENT_FAILURE=false
FHIR_PATIENT_COUNT=15
```

> **Zero-Configuration Offline Mode:** If you do not provide any API keys, the system **automatically runs in deterministic heuristic fallback mode**, executing the exact same 3-step state machine, reasoning traces, guardrail critiques, and CMS deliveries deterministically.

---

### Step 3: Run the AI Pipeline
```bash
python main.py
```

The orchestrator will:
1. Ingest `data/mock_leads.csv` and pull 15 live synthetic patients from `https://r4.smarthealthit.org`.
2. Normalize records and quarantine corrupt rows into `outputs/dead_letter_queue.json`.
3. Run each record through the 3-step Agent loop.
4. Deliver to the Mock CMS with Tenacity retry backoff (including simulated HTTP 503 recovery on record #3).
5. Output full audit records to `outputs/sample_end_to_end_results.json` and logs to `outputs/pipeline_execution.log`.

---

### Step 4: Launch the Web Dashboard
```bash
python server.py
```

Then open your browser to:
- **Interactive Web Dashboard:** [http://127.0.0.1:8000](http://127.0.0.1:8000)
  - Glassmorphic project management dashboard visualizing all delivered records.
  - Live filter pills (B2B Leads, Patients, HOT leads, High Urgency cases, DLQ).
  - Search bar across names, clinics, conditions, and channels.
  - Interactive **"Inspect Trace"** drawer displaying Step 1 Qualification, Step 2 Routing, Step 3 Guardrail Critique & Personalized Message, and CMS Receipts.
  - Interactive **"AI Assistant"** modal with live LLM connection ping tests.
- **Interactive OpenAPI / Swagger Documentation:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Live Cloud Deployment:** [https://realfire.vercel.app](https://realfire.vercel.app)

---

## 4. Project Directory Structure

```
├── .env                              # Active environment configuration
├── .env.example                      # Configuration template (Groq, Gemini, Ollama, CMS)
├── requirements.txt                  # Pinned dependencies (pydantic, httpx, tenacity, fastapi, rich)
├── README.md                         # Full instructions & technical documentation
├── WRITEUP.md                        # Standalone executive write-up (Scale, Architecture, HIPAA)
├── LOOM_WALKTHROUGH_SCRIPT.md        # Second-by-second 5-minute video walkthrough guide
├── main.py                           # End-to-end orchestrator & rich console reporting
├── server.py                         # Standalone FastAPI server launcher
├── test_pdf_requirements.py          # 100% automated requirements verification suite
├── vercel.json                       # Vercel serverless deployment configuration
├── api/
│   └── index.py                      # Vercel ASGI serverless handler with path normalizer
├── data/
│   └── mock_leads.csv                # 18 realistic B2B prospects + 1 corrupt test row
├── src/
│   ├── __init__.py                   # Package initialization
│   ├── schemas.py                    # Strict Pydantic v2 contracts (Stages 1, 2, and 3)
│   ├── ingest.py                     # Resilient CSV parser + live SMART FHIR R4 client + DLQ router
│   ├── llm_client.py                 # Multi-provider adapter (Groq, Gemini, Ollama, Heuristic Fallback)
│   ├── agent.py                      # 3-step Agent state machine (Analyzer -> Router -> Guardrail Critic)
│   ├── mock_cms.py                   # FastAPI CMS receiver (POST /api/v1/cms/records) & Dashboard UI
│   └── deliver.py                    # Tenacity retry client + transient 503 test + dual-push
└── outputs/                          # Generated automatically upon execution
    ├── sample_end_to_end_results.json# 33+ comprehensive traces (Input -> Agent Steps -> Message -> Receipt)
    ├── cms_delivered_records.json    # Records persisted in the downstream mock CMS
    ├── dead_letter_queue.json        # Isolated malformed records with exact error reasons
    └── pipeline_execution.log        # Full verbose execution log with color and timestamps
```

---

## 5. Pipeline Stages: In-Depth Technical Specification

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
  - Parses 18 realistic B2B prospects plus 1 corrupt row quarantined to DLQ.
- **Source B (SMART Health IT FHIR R4 Sandbox):**
  - Queries `GET https://r4.smarthealthit.org/Patient?_count=15`.
  - Performs secondary sub-queries per patient: `GET /Condition?patient={id}&_count=5` and `GET /Appointment?patient={id}&_count=5`.
  - Parses complex HL7 structures: `HumanName`, `ContactPoint` telecoms, active condition codings, and appointment statuses into clinical summaries.

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
     - **Healthcare Rule (HIPAA Minimum Necessary):** Strictly prohibits exposing specific clinical diagnoses or condition names (e.g. Diabetes, Osteoporosis, Mental Health) in cleartext over SMS/Email. Directs patient securely to their authenticated portal or clinic direct line.
     - **B2B Rule:** Prevents aggressive claims, aligns with prospect role.
   - If an issue is flagged, the agent applies self-correction to refine the draft before final emission.
   - Assembles the complete `AgentReasoningTrace`.

### STAGE 3: Resilient Downstream CMS Delivery (`src/deliver.py` & `src/mock_cms.py`)
- Emits a strictly validated `DownstreamCMSPayload` containing metadata, reasoning traces, and action plans.
- Mock CMS receives payloads at `POST /api/v1/cms/records`, stores them in `outputs/cms_delivered_records.json`, and returns an immutable `CMSReceipt`.
- Governed by `tenacity` exponential backoff retrying on HTTP 5xx errors or drops.

---

## 6. Non-Negotiable Resilience & Failure Demonstrations

### Failure Case A: Corrupted Ingestion Data Isolation (Dead Letter Queue)
- **Trigger:**
  1. Row 19 in `data/mock_leads.csv` lacks recipient name and all contact information.
  2. Injected synthetic corrupt FHIR record with empty name array and empty telecoms.
- **Handling:** Pydantic validation cleanly intercepts the anomalies without crashing the pipeline. Both rows are isolated and written to `outputs/dead_letter_queue.json` with explicit diagnostics:
  ```json
  {
    "record_id": "L019",
    "source": "linkedin_csv",
    "error_reason": "Missing recipient name and valid contact endpoints (name='', email='None', linkedin='None')",
    "timestamp_utc": "2026-10-29T18:55:00.000000+00:00"
  }
  ```

### Failure Case B: Transient Downstream 503 Outage & Exponential Retries
- **Trigger:** Record #3 (`L003`) triggers a simulated HTTP 503 Service Unavailable on attempt 1.
- **Handling:** Governed by `tenacity` exponential backoff (`stop_after_attempt(3)`, `wait_exponential(multiplier=1, min=1, max=4)`):
  ```
  [WARNING] [intake_pipeline.deliver] [FAILURE DEMO - Case B] Simulating transient HTTP 503 Service Unavailable on record 'L003' (Attempt 1/3)!
  [WARNING] [intake_pipeline.deliver] [RESILIENCE RETRY] CMS delivery attempt #1 failed. Retrying with exponential backoff (Next delay: 1.0s)...
  [INFO]    [intake_pipeline.deliver] [RESILIENCE SUCCESS] Retry succeeded for record 'L003' after transient recovery on attempt 2!
  ```

---

## 7. Executive Write-Up Summary

*(For the complete standalone submission document, see [`WRITEUP.md`](WRITEUP.md))*

### Architecture Decisions & Why
1. **Canonical Schema Contract (`UnifiedRecord`):** Decouples heterogeneous external data structures from internal agent logic, avoiding prompt bloat and hallucinated keys.
2. **Deconstructed 3-Step State Machine:** Solves "attention diffusion" in monolithic single-prompt systems. Each operational step (Gate $\rightarrow$ Route $\rightarrow$ Guardrail Critic) is isolated and auditable.
3. **Automated Guardrail Critic:** Enforces HIPAA Minimum Necessary compliance, ensuring clinical diagnoses are scrubbed before messages reach SMS or email dispatch.
4. **DLQ & Tenacity Retry:** Guarantees zero silent crashes and zero data loss.

### Handling Scale (10,000+ Records / Day)
- **Kafka / AWS SQS Streaming:** Decouple ingestion from worker execution pools (Celery / Temporal / ECS Fargate) with partition-based auto-scaling.
- **HL7 FHIR `$export` Standard:** Bulk NDJSON streaming directly into S3 instead of sequential REST queries.
- **Redis Semantic Caching:** Cache common B2B and routine clinical classification queries (>40% hit rate, <15ms response, $0 LLM token cost).
- **Batch API Offloading:** Route non-urgent records to asynchronous 24-hour Batch APIs for a 50% cost discount.

### Real PHI & HIPAA Compliance
- **BAAs & Zero Data Retention:** Enterprise agreements with HIPAA-eligible LLM providers (AWS Bedrock, Azure OpenAI) guaranteeing no prompt logging.
- **Safe Harbor De-Identification Vault:** Scrub the 18 HIPAA identifiers using surrogate cryptographic tokens (`PATIENT_TOKEN_A41B`) via HashiCorp Vault / Presidio before sending text to any model.
- **Content-Neutral Outreach:** Never include clinical diagnoses in unencrypted SMS/email. Direct patients to authenticate into secure portals.
- **WORM Audit Trails:** Persist intake decisions into Write-Once-Read-Many storage (e.g. AWS S3 Object Lock) per HIPAA §164.312(b).

---

## 8. Verification & Test Suite

Run the full automated test suite verifying all assignment constraints:
```bash
python test_pdf_requirements.py
```

Expected output:
```
======================================================================
   RUNNING FULL PDF REQUIREMENTS VERIFICATION SUITE
======================================================================
--- Test 1: Schema Validation & Dead Letter Queue ---
  [PASS] UnifiedRecord schema validated & DLQ correctly isolates malformed records.

--- Test 2: Ingest Source A (LinkedIn Leads CSV) ---
  [PASS] Successfully ingested 18 LinkedIn leads into UnifiedRecord contracts.

--- Test 3: Ingest Source B (SMART FHIR R4 Patients) ---
  [PASS] Successfully ingested 15 FHIR patients (DLQ isolated 1 malformed).

--- Test 4: 3-Step Autonomous State Machine & HIPAA Guardrail ---
  [PASS] 3-Step State Machine completed successfully with human escalation flag and HIPAA redaction verified.

--- Test 5: Tenacity Exponential Backoff Retry & CMS Delivery ---
  [PASS] Tenacity retry handled transient failure, record accepted: cms_rcpt_...

--- Test 6: FastAPI Service Endpoints & Health ---
  [PASS] All 7 service endpoints (/health, /cms/records, /results, /dlq, /diagnostics, /ping, /) verified 200 OK.
======================================================================
   >>> ALL PDF REQUIREMENTS VERIFIED & PASSED (Total: 30-35s) <<<
======================================================================
```
