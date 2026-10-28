# 5-Minute Loom Video Walkthrough Script

This script provides a turn-key, second-by-second guide for recording the optional (but highly scored) 5-minute Loom walkthrough requested in the technical assignment.

---

## ⏱️ Video Breakdown Summary (5:00 Total)

| Timestamp | Phase | What to Show on Screen | Key Talking Points |
|---|---|---|---|
| **0:00 - 0:45** | **1. Architecture & Overview** | Architecture diagram in `README.md` | Problem statement: unifying B2B leads & FHIR clinical data into an autonomous 3-step state machine with zero paid tools. |
| **0:45 - 1:30** | **2. Stage 1 Ingestion & DLQ** | VS Code terminal + `src/ingest.py` | Pulling LinkedIn CSV + live FHIR R4 sandbox (`https://r4.smarthealthit.org`). Show row 11 corruption and corrupt FHIR injection routed to Dead Letter Queue (`outputs/dead_letter_queue.json`). |
| **1:30 - 2:45** | **3. Stage 2 Agent State Machine** | Terminal running `python main.py` or `src/agent.py` | Explain the 3 discrete nodes: Step 1 Context & Quality Gate, Step 2 Policy Router (channel & tone), Step 3 Generator & HIPAA/B2B Guardrail Self-Critique. Point out active Groq model (`openai/gpt-oss-120b`). |
| **2:45 - 3:45** | **4. Stage 3 CMS Delivery & Resilience** | Terminal logs showing Tenacity retry | Point out Record #3 triggering simulated HTTP 503 and recovering automatically with Tenacity exponential backoff. Show `outputs/sample_end_to_end_results.json`. |
| **3:45 - 4:45** | **5. Live Dashboard & Observability** | Browser at `http://127.0.0.1:8000/` | Show dark/light mode toggle, filter chips (B2B Leads vs. Clinical Patients), KPI metrics, search, and click "Inspect Trace" on a patient record to show PHI redaction and reasoning audit. |
| **4:45 - 5:00** | **6. Wrap-Up & Deliverables** | Repo root / GitHub | Reiterate write-up sections: event-driven Kafka architecture at scale (10k+/day) and HIPAA Safe Harbor de-identification vault for real PHI. |

---

## 🎙️ Spoken Script & Step-by-Step Instructions

### [0:00 - 0:45] Intro & Architecture
> *"Hi everyone, today I'm demonstrating our production-grade agentic pipeline for automated lead and patient intake, enrichment, and outreach.*
>
> *In production, marketing systems and healthcare intake share the exact same structural topology: heterogeneous records arrive from external sources, an AI agent must reason across multiple steps to qualify and route them, and the resulting payload must land safely in a downstream CMS or CRM with strict contract enforcement.*
>
> *I designed this as an explicit three-stage pipeline: Stage 1 Ingests and Normalizes, Stage 2 executes an autonomous 3-step Agent Loop with an automated guardrail critique gate, and Stage 3 Delivers to a resilient Mock CMS with Tenacity exponential backoff."*

---

### [0:45 - 1:30] Stage 1: Ingestion & Dead Letter Queue (DLQ)
> *(Switch screen to `src/ingest.py` or terminal)*
>
> *"For Stage 1, we ingest from two structurally distinct sources:*
> 1. *Source A: A LinkedIn Sales Navigator CSV export.*
> 2. *Source B: The live SMART Health IT public FHIR R4 sandbox at `r4.smarthealthit.org`, pulling 15 synthetic Patient resources alongside related clinical Conditions and Appointments.*
>
> *Notice our strict Pydantic v2 validation perimeter. Instead of letting bad data crash the pipeline or hallucinate in downstream LLM prompts, malformed records—like a lead without contact information or a corrupted FHIR patient—are quarantined directly into our Dead Letter Queue file with full diagnostic lineage."*

---

### [1:30 - 2:45] Stage 2: Autonomous 3-Step Agent Loop
> *(Switch screen to terminal running `python main.py` or `src/agent.py`)*
>
> *"Rather than relying on a naive 'single prompt-and-done' call that suffers from attention drift, Stage 2 implements an explicit 3-node state machine:*
> - *Node 1 evaluates context completeness and scores priority triage.*
> - *Node 2 acts as a policy router—selecting the optimal channel, calibrating voice and tone, and determining executive or clinical escalation flags.*
> - *Node 3 generates the personalized outreach draft, followed immediately by an automated HIPAA and B2B self-critique gate. For clinical patients, it guarantees that sensitive diagnostic names are never leaked in cleartext over SMS or email, directing them securely to authenticated portals instead.*
>
> *For LLM inference, we use Groq's high-speed free tier running `openai/gpt-oss-120b`, with automatic fallback across candidate models and a deterministic heuristic engine for zero-cost offline evaluations."*

---

### [2:45 - 3:45] Stage 3: Resilient Delivery & Fault Tolerance
> *(Highlight the retry log in the terminal)*
>
> *"Stage 3 dispatches validated `DownstreamCMSPayload` objects to our FastAPI mock CMS receiver at `POST /api/v1/cms/records`.*
>
> *Here on record #3, you can see our deliberate fault tolerance test: the downstream service returns a transient HTTP 503 Service Unavailable. Our Tenacity retry handler intercepts the 5xx status code, triggers exponential backoff, and automatically recovers on the second attempt without dropping data.*
>
> *All end-to-end traces are committed to `outputs/sample_end_to_end_results.json` with immutable CMS receipts."*

---

### [3:45 - 4:45] Live Observability Dashboard
> *(Switch screen to browser at `http://127.0.0.1:8000/`)*
>
> *"To provide complete operational observability, we built an interactive dashboard:*
> - *Support for sleek Dark and Light mode.*
> - *Real-time KPI metrics showing lead triage breakdown, clinical urgency cases, and DLQ counts.*
> - *Instant search and domain filtering.*
> - *Clicking 'Inspect Trace' on any record slides open an audit drawer showing the complete step-by-step reasoning trace: Step 1 qualification rationale, Step 2 routing policy, Step 3 guardrail evaluation, and the final CMS delivery receipt."*

---

### [4:45 - 5:00] Conclusion & Scalability
> *(Switch screen to README.md)*
>
> *"Finally, Section 6 of the README details our executive write-up:*
> 1. *Scaling to 10,000+ daily records using a partitioned Kafka streaming architecture, FHIR `$export` bulk streaming, and Redis semantic caching.*
> 2. *Regulatory HIPAA controls for real PHI, including BAAs with zero-data-retention models, automated Safe Harbor tokenization vaults, and WORM storage audit trails.*
>
> *Thank you!"*
