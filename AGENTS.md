# AGENTS.md - Developer & Agent Instructions

This document provides architectural standards, invariants, and operational guidelines for autonomous AI agents and engineers working in this repository.

---

## 1. Project Overview & Architecture

This repository contains a production-grade, 3-stage agentic data pipeline in Python 3.10+:
**"AI Agent for Automated Lead & Patient Intake, Enrichment, and Outreach"**

```
+-------------------------------------------------------------------------------+
| STAGE 1: Data Ingestion & Canonical Normalization                            |
| - LinkedIn Lead CSV Parser + FHIR R4 Smart Patient API Ingestion               |
| - Strict Pydantic v2 validation; Malformed records -> Dead Letter Queue (DLQ) |
+---------------------------------------+---------------------------------------+
                                        | UnifiedRecord
                                        v
+-------------------------------------------------------------------------------+
| STAGE 2: Autonomous 3-Step AI Agent Loop & State Machine                      |
| - Step 1: Context Analyzer & Completeness Quality Gate                        |
| - Step 2: Policy & Action Router (Channel, Tone, Escalation Flag)             |
| - Step 3: Outreach Synthesis + HIPAA/B2B Guardrail Self-Critique Gate         |
| - Multi-provider LLM Client: Groq -> Gemini -> Ollama -> Deterministic Fallback|
+---------------------------------------+---------------------------------------+
                                        | DownstreamCMSPayload + AgentReasoningTrace
                                        v
+-------------------------------------------------------------------------------+
| STAGE 3: Downstream Delivery & Observability                                  |
| - Mock CMS & CRM Ingestion Service (FastAPI REST Server)                      |
| - Tenacity Exponential Backoff Retry on 5xx Errors / Network Drops            |
| - Real-time Project Management Dashboard (Dark/Light Mode, KPI Analytics)     |
+-------------------------------------------------------------------------------+
```

---

## 2. Directory Structure & Key Files

```
├── .env                  # Active runtime environment configuration
├── .env.example          # Clean configuration template
├── server.py             # FastAPI Server Entrypoint (Mock CMS & Dashboard)
├── main.py               # End-to-End Orchestrator (Ingest -> Agent -> Deliver)
├── data/                 # Raw seed datasets (leads.csv, fhir_sample.json)
├── outputs/              # Pipeline artifacts (results json, logs, dlq)
├── skills/               # Developer workflows, SKILL.md, AGENTS.md, CLAUDE.md
└── src/
    ├── __init__.py
    ├── schemas.py        # Strict Pydantic v2 contracts for all 3 stages
    ├── ingest.py         # Stage 1: Ingestion engine & normalizers
    ├── llm_client.py     # Multi-provider LLM interface with fallback
    ├── agent.py          # Stage 2: 3-step autonomous state machine
    ├── deliver.py        # Stage 3: Resilient HTTP delivery engine
    └── mock_cms.py       # FastAPI mock CMS receiver & dashboard UI
```

---

## 3. Core Development Invariants

1. **Zero Placeholders**: Do NOT introduce `TODO`, `pass`, placeholder mock responses, or hardcoded fake returns. All logic must be complete and executable.
2. **Strict Schema Boundaries**: All data moving across stages must strictly deserialize into schemas in `src/schemas.py`. Never pass untyped arbitrary dictionaries across pipeline stages.
3. **Graceful Multi-tier Degradation**:
   - `LLMClient` must never throw unhandled exceptions that halt the entire pipeline.
   - If Groq fails or rate limits, fallback to alternative models (`openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.8-27b`).
   - If all remote API calls fail or no keys are configured, fallback cleanly to `heuristic_fallback` so test suites and offline evaluations complete deterministically.
4. **Encoding & Windows Safety**:
   - Always open files with explicit `encoding="utf-8"`.
   - Never embed unescaped UTF-16 surrogate pairs (`\uD83D\uDCBC`) into Python strings or HTML payloads (use real Unicode or UTF-8).
   - Maintain UTF-8 terminal output safety via `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`.

---

## 4. Key Developer Commands

```powershell
# 1. Start Mock CMS & Dashboard Server
python server.py

# 2. Run the Full End-to-End Pipeline
python main.py

# 3. Test LLM Connection (Groq / Gemini)
python -c "from src.llm_client import LLMClient; c = LLMClient(); print(c.provider, c.groq_model); print(c.generate_json('System', 'Return JSON: {\"ok\": true}'))"

# 4. Check Server Health
python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"
```

---

## 5. Coding Standards & Conventions

- **Typing**: Use standard Python 3.10+ type hints (`Optional[T]`, `List[T]`, `Dict[str, Any]`, `Literal[...]`).
- **Validation**: Pydantic v2 models use `@field_validator` (not legacy `@validator`).
- **Logging**: Use `logging.getLogger("intake_pipeline.<module>")` with descriptive contextual details. Avoid bare `print()` calls in core library modules (`src/`).
