---
name: intake-pipeline-operations
description: >-
  Operational workflow and developer capability guide for the AI Agent Lead & Patient Intake Pipeline.
  Use when running the ingestion engine, executing the 3-step agent loop, starting the FastAPI
  dashboard server, testing Groq/Gemini LLM calls, or delivering validated payloads to Mock CMS.
---

# Intake Pipeline Operations & Developer Workflows

This skill provides step-by-step developer workflows for developing, executing, testing, and debugging the **AI Agent for Automated Lead & Patient Intake, Enrichment, and Outreach**.

---

## 1. Environment & Server Management

### Starting the FastAPI Mock CMS & Dashboard
The project includes a FastAPI backend that hosts both the Mock CMS delivery REST endpoints and the real-time project management dashboard.

```powershell
# Run the server on port 8000
python server.py
```
- **Dashboard URL**: `http://127.0.0.1:8000/`
- **Interactive Swagger Docs**: `http://127.0.0.1:8000/docs`
- **ReDoc Documentation**: `http://127.0.0.1:8000/redoc`
- **Health Check**: `http://127.0.0.1:8000/health`

### Verifying Port Availability
If port 8000 is occupied or needs restarting:
```powershell
netstat -ano | findstr :8000
# Kill process if needed:
Stop-Process -Id <PID> -Force
```

---

## 2. Pipeline Execution Workflows

### Running Full End-to-End Ingestion & Processing
Executes Stage 1 (Ingest & Normalize) -> Stage 2 (3-Step AI Agent) -> Stage 3 (Resilient CMS Delivery):
```powershell
python main.py
```

### Key Execution Artifacts Produced
- `outputs/sample_end_to_end_results.json`: Full JSON record array containing ingested data, step 1/2/3 traces, and delivery status.
- `outputs/pipeline_execution.log`: Full execution logs with timing, HTTP status, and agent thoughts.
- `outputs/dlq_records.json`: Dead letter queue containing invalid or failed records for audit.

---

## 3. LLM Configuration & Model Management

The pipeline supports dynamic provider selection in `.env`:

| `LLM_PROVIDER` | Description | Requirements |
|---|---|---|
| `auto` (Default) | Automatically picks Groq if key exists, then Gemini, else Heuristic | `GROQ_API_KEY` or `GEMINI_API_KEY` |
| `groq` | High-speed cloud inference via Groq | `GROQ_API_KEY`, `GROQ_MODEL=openai/gpt-oss-120b` |
| `gemini` | Google Gemini API | `GEMINI_API_KEY`, `GEMINI_MODEL=gemini-2.5-flash` |
| `ollama` | Local offline LLM execution | `OLLAMA_BASE_URL=http://localhost:11434` |
| `heuristic_fallback` | Zero-dependency, deterministic rule-based engine | No API keys needed |

### Testing LLM Client Independently
```powershell
python -c "from src.llm_client import LLMClient; c = LLMClient(); print('Provider:', c.provider, 'Model:', c.groq_model); print(c.generate_json('System prompt', 'Return JSON: {\"status\": \"ok\"}'))"
```

---

## 4. 3-Step Agent State Machine Workflow

When extending or modifying the agent logic in `src/agent.py`:

1. **Step 1: Context Analyzer & Quality Gate (`_step1_analyze_and_qualify`)**
   - Evaluates completeness score (0.0 to 1.0).
   - Assigns priority triage: `HOT`, `WARM`, `COLD`, `INCOMPLETE` (Leads) or `EMERGENCY_ESCALATION`, `CHRONIC_CARE_PRIORITY`, `ROUTINE_FOLLOWUP`, `INCOMPLETE_RECORD` (Patients).
2. **Step 2: Action & Policy Router (`_step2_route_action`)**
   - Maps classification to appropriate channel (`email`, `linkedin_dm`, `sms`, `phone_call`, `clinical_escalation_queue`).
   - Assigns communication voice/tone and sets `escalate_flag`.
3. **Step 3: Personalized Message Generator & Self-Critique Guardrail (`_step3_generate_and_critique`)**
   - Synthesizes personalized draft message.
   - Executes compliance self-critique (enforces HIPAA, no medical advice, no spam claims, peer consultative tone).
   - Refines draft if critique notes violations and sets `guardrail_passed`.

---

## 5. Adding New Data Ingestion Sources

To add a new data provider (e.g. CRM, CSV, webhook):
1. In `src/schemas.py`, add source literal to `UnifiedRecord.source`.
2. In `src/ingest.py`, add parser method returning `List[UnifiedRecord]` and appending rejected inputs to `IngestionEngine.dlq`.
3. Call the new method inside `IngestionEngine.ingest_all()`.

---

## 6. Resilience & Fault Tolerance Testing

The downstream delivery engine (`src/deliver.py`) utilizes `tenacity` exponential backoff retries:
- **Retry Trigger**: HTTP 5xx responses or network timeouts.
- **Backoff Schedule**: Exponential backoff (`wait_exponential(multiplier=1, min=1, max=10)`).
- **Transient Failure Simulation**: Set `SIMULATE_TRANSIENT_FAILURE=true` in `.env` to simulate a 503 on the 3rd record to demonstrate live auto-recovery in logs.
