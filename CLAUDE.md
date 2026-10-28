# CLAUDE.md - AI Coding Assistant Reference

This file provides quick context, architecture overview, and command recipes for Claude Code and related agentic coding assistants.

---

## ⚡ Quick Reference Commands

### Running the Services
```powershell
# Launch FastAPI Mock CMS & Dashboard (Port 8000)
python server.py

# Execute 3-Stage End-to-End Pipeline
python main.py

# Fast LLM Connectivity Test
python -c "from src.llm_client import LLMClient; c = LLMClient(); print('Provider:', c.provider, 'Model:', c.groq_model); print(c.generate_json('System', 'Return JSON: {\"status\": \"ok\"}'))"
```

### Server Endpoints & URLs
- **Web Dashboard**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Swagger Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Health Check**: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- **CMS Delivery Endpoint**: `POST /api/v1/cms/records`
- **Pipeline Results API**: `GET /api/v1/pipeline/results`
- **Dead Letter Queue API**: `GET /api/v1/pipeline/dlq`

---

## 🏗️ Architecture & Pipeline Overview

```
Raw Data (CSV / FHIR) ──▶ Stage 1: Ingest & Normalize (src/ingest.py)
                                  │
                                  ▼ UnifiedRecord
                          Stage 2: 3-Step AI Agent (src/agent.py)
                            Step 1: Context & Completeness Analyzer
                            Step 2: Action & Channel Policy Router
                            Step 3: Outreach Synthesis & Guardrail Critique
                                  │
                                  ▼ DownstreamCMSPayload + AgentReasoningTrace
                          Stage 3: Resilient Delivery (src/deliver.py)
                                  │
                                  ▼ HTTP POST with Tenacity Exponential Backoff
                          Mock CMS Hub & Live Dashboard (src/mock_cms.py)
```

---

## ⚙️ Environment Variables (`.env`)

```env
# LLM Provider: "auto", "groq", "gemini", "ollama", or "heuristic_fallback"
LLM_PROVIDER=auto
GROQ_API_KEY=gsk_...
GROQ_MODEL=openai/gpt-oss-120b
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash

# CMS Delivery & Webhooks
MOCK_CMS_HOST=127.0.0.1
MOCK_CMS_PORT=8000
WEBHOOK_SITE_URL=

# Fault Tolerance Demonstration
SIMULATE_TRANSIENT_FAILURE=false
FHIR_PATIENT_COUNT=15
```

---

## 📐 Code Style & Conventions

- **Python Version**: Python 3.10+ with modern typing (`typing.Optional`, `typing.List`, `typing.Dict`, `typing.Literal`).
- **Data Contracts**: Pydantic v2 schemas exclusively defined in `src/schemas.py`.
- **Fault Tolerance**: Use `tenacity.retry` for external network calls with exponential backoff on HTTP 5xx.
- **Failover**: `src/llm_client.py` implements self-healing candidate model cycling (`openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.8-27b`) and falls back to deterministic heuristic rules if remote APIs fail.
- **File Encodings**: Always use `encoding="utf-8"` when reading or writing files.
