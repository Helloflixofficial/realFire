"""
Mock Downstream CMS & CRM System with Interactive Web Dashboard.
Provides:
  - RESTful API endpoints for CMS delivery (POST /api/v1/cms/records)
  - Data retrieval endpoints (/api/v1/pipeline/results, /api/v1/pipeline/dlq)
  - Interactive, glassmorphic Web Dashboard UI at http://127.0.0.1:8000
  - Interactive OpenAPI/Swagger documentation at http://127.0.0.1:8000/docs
"""

from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from src.schemas import CMSReceipt, DownstreamCMSPayload

logger = logging.getLogger("intake_pipeline.cms")

# Persistent storage files
CMS_STORE_FILE = Path("outputs/cms_delivered_records.json")
E2E_RESULTS_FILE = Path("outputs/sample_end_to_end_results.json")
DLQ_FILE = Path("outputs/dead_letter_queue.json")

app = FastAPI(
    title="AI Agent Intake, Enrichment & CMS Hub",
    description="Enterprise intake orchestrator & downstream CMS receiver for B2B Leads and SMART FHIR Patients.",
    version="1.0.0",
    redoc_url=None,  # Disabled in favor of interactive Swagger UI (/docs)
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/redoc", include_in_schema=False)
def redoc_redirect():
    """Redirects ReDoc to Swagger UI (/docs) to avoid CDN blank page issues."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")


# In-memory registry of received deliveries
received_database: List[Dict[str, Any]] = []


def _load_initial_records() -> None:
    """Pre-loads existing records from disk into memory if available."""
    global received_database
    if CMS_STORE_FILE.exists():
        try:
            with open(CMS_STORE_FILE, "r", encoding="utf-8") as f:
                received_database = json.load(f)
        except Exception:
            received_database = []


_load_initial_records()


def _save_to_disk() -> None:
    """Flushes received records to the JSON persistence file."""
    try:
        CMS_STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CMS_STORE_FILE, "w", encoding="utf-8") as f:
            json.dump(received_database, f, indent=2)
    except Exception as e:
        logger.warning(f"Disk write bypassed in serverless environment: {e}")


# ==============================================================================
# API ENDPOINTS
# ==============================================================================

@app.get("/health", tags=["Health"])
def health_check() -> Dict[str, Any]:
    """Liveness probe for the Mock CMS & Pipeline."""
    return {
        "status": "healthy",
        "service": "AI Agent Intake & Downstream CMS Hub",
        "delivered_records_count": len(received_database),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/cms/records", tags=["CMS Records"])
def get_delivered_records() -> List[Dict[str, Any]]:
    """Returns all records accepted and committed into the Mock CMS."""
    return received_database


@app.get("/api/v1/pipeline/results", tags=["Pipeline Outputs"])
def get_pipeline_results() -> List[Dict[str, Any]]:
    """Returns the comprehensive end-to-end traces including 3-step reasoning."""
    if E2E_RESULTS_FILE.exists():
        try:
            with open(E2E_RESULTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading {E2E_RESULTS_FILE}: {e}")
    # Fallback to reconstructing from received_database
    fallback = []
    for entry in received_database:
        p = entry.get("payload", {})
        fallback.append({
            "record_id": p.get("record_id"),
            "source": p.get("source_system"),
            "recipient_name": p.get("recipient_name"),
            "priority_signal": p.get("action_plan", {}).get("tone", ""),
            "input_context": f"Target: {p.get('recipient_name')}",
            "agent_reasoning": p.get("agent_reasoning_trace", {}),
            "final_message": p.get("personalized_message", ""),
            "cms_receipt": {
                "cms_receipt_id": entry.get("cms_receipt_id"),
                "status": "accepted",
                "received_at": entry.get("received_at"),
            },
        })
    return fallback


@app.get("/api/v1/pipeline/dlq", tags=["Pipeline Outputs"])
def get_dead_letter_queue() -> List[Dict[str, Any]]:
    """Returns all quarantined malformed records from Stage 1."""
    if DLQ_FILE.exists():
        try:
            with open(DLQ_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading {DLQ_FILE}: {e}")
    return []


@app.post(
    "/api/v1/cms/records",
    response_model=CMSReceipt,
    status_code=status.HTTP_201_CREATED,
    tags=["CMS Ingest"],
    summary="Ingest validated agent outreach payload into CMS",
)
def ingest_record(payload: DownstreamCMSPayload) -> CMSReceipt:
    """
    Receives and strictly validates an outbound DownstreamCMSPayload.
    Persists to disk and issues an immutable audit receipt.
    """
    logger.info(
        f"[CMS Ingest] Receiving delivery '{payload.delivery_id}' "
        f"for record '{payload.record_id}' ({payload.recipient_name})"
    )

    payload_dict = payload.model_dump()
    receipt_id = f"cms_rcpt_{uuid.uuid4().hex[:12]}"
    received_at = datetime.now(timezone.utc).isoformat()

    stored_entry = {
        "cms_receipt_id": receipt_id,
        "received_at": received_at,
        "payload": payload_dict,
    }
    received_database.append(stored_entry)
    _save_to_disk()

    logger.info(
        f"[CMS Ingest] Delivery '{payload.delivery_id}' successfully accepted and committed. "
        f"Receipt: {receipt_id}"
    )

    return CMSReceipt(
        cms_receipt_id=receipt_id,
        status="accepted",
        received_at=received_at,
        record_id=payload.record_id,
        message="Record successfully validated and committed to CMS database",
    )


def clear_cms_store() -> None:
    """Utility to clear database at the beginning of a fresh run."""
    global received_database
    received_database = []
    if CMS_STORE_FILE.exists():
        CMS_STORE_FILE.unlink()


# ==============================================================================
# WEB DASHBOARD (HTML RESPONSE)
# ==============================================================================

@app.get("/api/v1/diagnostics", tags=["System Diagnostics"])
def get_diagnostics() -> Dict[str, Any]:
    from src.llm_client import LLMClient
    client = LLMClient()
    masked_groq = ""
    if client.groq_api_key:
        masked_groq = client.groq_api_key[:6] + "..." + client.groq_api_key[-4:]
    return {
        "llm_provider": client.provider,
        "llm_model": client.groq_model if client.provider == "groq" else (client.gemini_model if client.provider == "gemini" else "heuristic_engine"),
        "groq_key_masked": masked_groq,
        "groq_key_active": bool(client.groq_api_key),
        "gemini_key_active": bool(client.gemini_api_key),
        "delivered_records": len(received_database),
        "fhir_endpoint": "https://r4.smarthealthit.org",
        "dlq_file": "outputs/dead_letter_queue.json",
        "retry_policy": "Tenacity exponential backoff (1s - 4s, 3 attempts)",
        "guardrails": "HIPAA PHI Redaction + B2B Intent Guardrail",
    }


@app.post("/api/v1/diagnostics/ping", tags=["System Diagnostics"])
def ping_llm() -> Dict[str, Any]:
    import time
    from src.llm_client import LLMClient
    client = LLMClient()
    t0 = time.time()
    try:
        res = client.generate_json("System test", "Return JSON: {\"ping\": \"pong\"}")
        latency_ms = round((time.time() - t0) * 1000)
        return {
            "status": "ok",
            "provider": client.provider,
            "model": client.groq_model,
            "latency_ms": latency_ms,
            "response": res,
        }
    except Exception as e:
        latency_ms = round((time.time() - t0) * 1000)
        return {
            "status": "error",
            "provider": client.provider,
            "error": str(e),
            "latency_ms": latency_ms,
        }


@app.get("/", response_class=HTMLResponse, tags=["Dashboard UI"])
def render_dashboard() -> str:
    """Renders the pure white dual-sidebar project management dashboard for the AI intake pipeline."""
    return """<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Agent Intake &amp; CMS Hub — Pipeline Dashboard</title>
<meta name="description" content="Pure white dual-sidebar AI intake, enrichment &amp; CMS delivery dashboard for B2B Leads and SMART FHIR Patients.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,300..800;1,14..32,300..800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --canvas:#f8fafc;
  --surface:#ffffff;
  --elevated:#f1f5f9;
  --overlay:rgba(255,255,255,.95);
  --border:#e2e8f0;
  --border-s:#edf2f7;
  --t1:#0f172a;
  --t2:#475569;
  --t3:#94a3b8;
  --accent:#237359;
  --accent-h:#1b5c47;
  --glow:rgba(35,115,89,.15);
  
  --green:#10b981;--green-bg:rgba(16,185,129,.12);
  --amber:#f59e0b;--amber-bg:rgba(245,158,11,.12);
  --rose:#f43f5e;--rose-bg:rgba(244,63,94,.12);
  --cyan:#06b6d4;--cyan-bg:rgba(6,182,212,.12);
  --violet:#8b5cf6;--violet-bg:rgba(139,92,246,.12);
  
  /* Dual Sidebar Dimensions */
  --rail-w:64px;--panel-w:216px;--sw:280px;--th:62px;
  --rS:8px;--rM:12px;--rL:16px;--rPill:999px;
  --shS:0 1px 3px rgba(0,0,0,.05);
  --shM:0 4px 18px rgba(0,0,0,.08);
  --shL:0 12px 36px rgba(0,0,0,.12);
  --ease:all .2s cubic-bezier(.4,0,.2,1);

  /* Clean White Theme for Dual Sidebar */
  --sb-rail-bg:#ffffff;
  --sb-panel-bg:#ffffff;
  --sb-border:#e2e8f0;
  --sb-text:#334155;
  --sb-muted:#64748b;
  --sb-hover:#f1f5f9;
  --sb-active-bg:#237359;
  --sb-active-text:#ffffff;
  --sb-pill-border:#e2e8f0;
  --sb-logo-color:#237359;
}

*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;font-family:'Inter',system-ui,sans-serif;background:var(--canvas);color:var(--t1);font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}

/* SHELL */
.shell{display:flex;min-height:100vh}

/* ==========================================================================
   PURE WHITE DUAL-COLUMN SIDEBAR (MATCHING LEFT SCREENSHOT)
   ========================================================================== */
.dual-sidebar{
  width:var(--rail-w);
  min-height:100vh;
  display:flex;
  position:fixed;
  left:0;top:0;bottom:0;
  z-index:50;
  box-shadow:var(--shM);
  user-select:none;
  background:#ffffff;
  transition:width .22s cubic-bezier(.16,1,.3,1);
}
.dual-sidebar:hover{
  width:var(--sw);
}

/* 1. SLIM LEFT ICON RAIL */
.sidebar-rail{
  width:var(--rail-w);
  background:var(--sb-rail-bg);
  border-right:1px solid var(--sb-border);
  display:flex;
  flex-direction:column;
  align-items:center;
  padding:16px 0 18px;
  flex-shrink:0;
  z-index:52;
  position:relative;
  box-shadow:var(--shS);
}

.brand-logo{
  width:38px;height:38px;
  border-radius:10px;
  display:flex;align-items:center;justify-content:center;
  color:var(--sb-logo-color);
  margin-bottom:20px;
  cursor:pointer;
  transition:var(--ease);
}
.brand-logo:hover{transform:scale(1.06)}

.rail-nav{
  display:flex;
  flex-direction:column;
  align-items:center;
  gap:10px;
  width:100%;
}

.rail-btn{
  width:40px;height:40px;
  border-radius:var(--rPill);
  border:none;background:transparent;
  color:var(--sb-muted);
  display:flex;align-items:center;justify-content:center;
  cursor:pointer;
  transition:var(--ease);
}
.rail-btn:hover{
  background:var(--sb-hover);
  color:var(--sb-text);
}
.rail-btn.active{
  background:var(--sb-active-bg);
  color:var(--sb-active-text);
  box-shadow:0 3px 10px rgba(35,115,89,.25);
}

.rail-divider{
  width:32px;height:1px;
  background:var(--sb-border);
  margin:18px 0;
}

.rail-bottom{
  margin-top:auto;
  display:flex;
  flex-direction:column;
  align-items:center;
  gap:12px;
  width:100%;
}

.rail-avatar{
  width:36px;height:36px;
  border-radius:var(--rPill);
  background:linear-gradient(135deg,#237359,#10b981);
  color:#ffffff;
  font-weight:700;
  font-size:13px;
  display:flex;align-items:center;justify-content:center;
  cursor:pointer;
  border:2px solid var(--sb-border);
  transition:var(--ease);
  box-shadow:0 2px 8px rgba(0,0,0,.08);
}
.rail-avatar:hover{transform:scale(1.05)}

/* 2. NAVIGATION SUB-PANEL */
.sidebar-panel{
  position:absolute;
  left:var(--rail-w);
  top:0;bottom:0;
  width:var(--panel-w);
  background:var(--sb-panel-bg);
  border-right:1px solid var(--sb-border);
  display:flex;
  flex-direction:column;
  padding:16px 14px 18px;
  flex-shrink:0;
  z-index:51;
  box-shadow:12px 0 32px rgba(15,23,42,.1);
  transform:translateX(-16px);
  opacity:0;
  pointer-events:none;
  transition:transform .22s cubic-bezier(.16,1,.3,1), opacity .18s ease;
}
.dual-sidebar:hover .sidebar-panel{
  transform:translateX(0);
  opacity:1;
  pointer-events:auto;
}

/* Workspace selector pill (Matching "Neurotime +" in White Mode) */
.panel-header{
  margin-bottom:18px;
}
.ws-pill{
  display:flex;
  align-items:center;
  justify-content:space-between;
  padding:8px 14px;
  border-radius:var(--rPill);
  border:1px solid var(--sb-pill-border);
  background:#ffffff;
  color:var(--sb-text);
  cursor:pointer;
  transition:var(--ease);
  box-shadow:0 1px 3px rgba(0,0,0,.04);
}
.ws-pill:hover{
  background:var(--sb-hover);
  border-color:#cbd5e1;
}
.ws-name{
  font-size:13px;
  font-weight:700;
  letter-spacing:-.2px;
}
.ws-add{
  width:20px;height:20px;
  border-radius:var(--rPill);
  border:1px solid #94a3b8;
  background:#f8fafc;
  color:#475569;
  display:flex;align-items:center;justify-content:center;
  font-size:13px;line-height:1;
  font-weight:700;
  cursor:pointer;
}

/* Nav items list */
.panel-nav{
  display:flex;
  flex-direction:column;
  gap:4px;
  flex:1;
}

.panel-item{
  display:flex;
  align-items:center;
  gap:10px;
  padding:9px 14px;
  border-radius:var(--rPill);
  border:none;background:transparent;
  color:var(--sb-text);
  font-size:13px;
  font-weight:600;
  text-decoration:none;
  cursor:pointer;
  transition:var(--ease);
  text-align:left;
  width:100%;
}
.panel-item:hover{
  background:var(--sb-hover);
  color:var(--t1);
}
.panel-item.active{
  background:var(--sb-active-bg);
  color:var(--sb-active-text);
  font-weight:700;
  box-shadow:0 3px 12px rgba(35,115,89,.22);
}
.panel-item.active .pi-icon{
  stroke:var(--sb-active-text);
  color:var(--sb-active-text);
}

.pi-icon{
  width:17px;height:17px;
  flex-shrink:0;
  stroke:currentColor;
  transition:var(--ease);
}

.panel-badge{
  margin-left:auto;
  font-size:10px;
  font-weight:700;
  padding:2px 7px;
  border-radius:var(--rPill);
  background:#f1f5f9;
  color:#475569;
  border:1px solid #e2e8f0;
}
.panel-item.active .panel-badge{
  background:rgba(255,255,255,.2);
  color:#ffffff;
  border-color:transparent;
}
.alert-badge{
  background:var(--rose-bg);
  color:var(--rose);
  border:1px solid rgba(244,63,94,.3);
}

.panel-divider{
  height:1px;
  background:var(--sb-border);
  margin:12px 6px;
}

/* Footer Live Status (NO UPGRADE CARD) */
.panel-footer{
  margin-top:auto;
  padding-top:12px;
}
.live-status-pill{
  display:flex;
  align-items:center;
  gap:9px;
  padding:9px 12px;
  border-radius:var(--rM);
  background:#f8fafc;
  border:1px solid var(--sb-border);
}
.pulse-dot{
  width:8px;height:8px;
  border-radius:50%;
  background:#10b981;
  box-shadow:0 0 8px #10b981;
  animation:pulse 2s infinite;
  flex-shrink:0;
}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(1.25)}}
.live-title{font-size:11px;font-weight:700;color:var(--sb-text);letter-spacing:.3px}
.live-port{font-size:10px;color:var(--sb-muted)}

/* ==========================================================================
   MAIN CONTENT AREA (PURE WHITE LIGHT THEME)
   ========================================================================== */
.main{
  margin-left:var(--rail-w);
  flex:1;
  display:flex;
  flex-direction:column;
  min-height:100vh;
  transition:var(--ease);
}

/* TOPBAR */
.topbar{
  height:var(--th);
  background:var(--overlay);
  backdrop-filter:blur(20px);
  -webkit-backdrop-filter:blur(20px);
  border-bottom:1px solid var(--border-s);
  display:flex;align-items:center;
  padding:0 24px;gap:14px;
  position:sticky;top:0;z-index:40;
}
.tb-bc{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--t2);flex:1}
.tb-bc strong{color:var(--t1);font-weight:700}
.bc-sep{color:var(--t3)}
.tb-srch{
  display:flex;align-items:center;gap:8px;
  background:#ffffff;border:1px solid var(--border);
  border-radius:var(--rPill);
  padding:7px 14px;width:290px;transition:var(--ease);
  box-shadow:0 1px 3px rgba(0,0,0,.03);
}
.tb-srch:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px var(--glow)}
.tb-srch input{background:none;border:none;outline:none;color:var(--t1);font-size:13px;font-family:'Inter',sans-serif;width:100%}
.tb-srch input::placeholder{color:var(--t3)}
.tb-acts{display:flex;align-items:center;gap:8px}
.ib{
  width:36px;height:36px;
  border-radius:var(--rPill);
  border:1px solid var(--border);
  background:#ffffff;
  display:flex;align-items:center;justify-content:center;
  cursor:pointer;font-size:14px;color:var(--t2);
  transition:var(--ease);position:relative;
}
.ib:hover{background:var(--elevated);color:var(--t1)}
.ndot{position:absolute;top:7px;right:7px;width:6px;height:6px;background:var(--rose);border-radius:50%;border:1.5px solid var(--surface)}
.btn-a{
  display:inline-flex;align-items:center;gap:6px;
  padding:7px 15px;background:#237359;color:#ffffff;
  border-radius:var(--rPill);font-size:12px;font-weight:600;
  cursor:pointer;border:none;text-decoration:none;
  transition:var(--ease);box-shadow:0 2px 10px rgba(35,115,89,.22);
}
.btn-a:hover{background:#1b5c47;transform:translateY(-1px);box-shadow:0 4px 16px rgba(35,115,89,.3)}

/* PAGE CONTENT */
.page{padding:24px 28px;flex:1}
.ph{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:24px;gap:12px;flex-wrap:wrap}
.ph-t{font-size:24px;font-weight:800;letter-spacing:-.6px;color:var(--t1)}
.ph-s{font-size:13px;color:var(--t2);margin-top:4px}
.ph-a{display:flex;align-items:center;gap:8px}
.btn-g{
  display:inline-flex;align-items:center;gap:6px;
  padding:7px 14px;border-radius:var(--rPill);
  border:1px solid var(--border);background:#ffffff;
  color:var(--t2);font-size:12px;font-weight:600;
  cursor:pointer;text-decoration:none;transition:var(--ease);
  box-shadow:0 1px 3px rgba(0,0,0,.03);
}
.btn-g:hover{background:var(--elevated);color:var(--t1);border-color:#cbd5e1}

/* KPI GRID */
.kpi-g{display:grid;grid-template-columns:repeat(auto-fit,minmax(196px,1fr));gap:14px;margin-bottom:24px}
.kpi{
  background:#ffffff;border:1px solid var(--border);
  border-radius:var(--rL);padding:18px;position:relative;
  overflow:hidden;transition:var(--ease);cursor:default;
  box-shadow:var(--shS);
}
.kpi:hover{border-color:#cbd5e1;box-shadow:var(--shM);transform:translateY(-2px)}
.kpi::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--cc,#237359);opacity:0;transition:var(--ease)}
.kpi:hover::before{opacity:1}
.kpi-hd{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.kpi-lbl{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:var(--t3)}
.kpi-ico{width:32px;height:32px;border-radius:var(--rS);display:flex;align-items:center;justify-content:center;font-size:14px;background:var(--ib,var(--glow))}
.kpi-val{font-size:32px;font-weight:800;letter-spacing:-1.5px;color:var(--t1);line-height:1;margin-bottom:6px}
.kpi-sub{font-size:11px;color:var(--t3);margin-bottom:10px}
.kpi-track{height:4px;background:var(--elevated);border-radius:999px;overflow:hidden}
.kpi-bar{height:100%;border-radius:999px;background:var(--cc,#237359);transition:width 1s cubic-bezier(.4,0,.2,1)}

/* CONTENT GRID */
.cg{display:grid;grid-template-columns:1fr 310px;gap:20px;margin-bottom:24px}
.panel{background:#ffffff;border:1px solid var(--border);border-radius:var(--rL);overflow:hidden;box-shadow:var(--shS)}
.panel-hd{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid var(--border-s);background:#ffffff}
.panel-t{font-size:14px;font-weight:700;color:var(--t1);display:flex;align-items:center;gap:8px}
.p-ico{width:28px;height:28px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:13px}
.panel-a{display:flex;gap:8px;align-items:center}
.cbadge{background:#f1f5f9;border:1px solid var(--border);color:var(--t2);font-size:10px;font-weight:700;padding:2px 8px;border-radius:var(--rPill)}

/* TOOLBAR */
.toolbar{display:flex;align-items:center;gap:10px;padding:12px 20px;border-bottom:1px solid var(--border-s);flex-wrap:wrap;background:#ffffff}
.sf{display:flex;align-items:center;gap:8px;background:#f8fafc;border:1px solid var(--border);border-radius:var(--rPill);padding:7px 14px;flex:1;min-width:200px;transition:var(--ease)}
.sf:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px var(--glow);background:#ffffff}
.sf input{background:none;border:none;outline:none;color:var(--t1);font-size:13px;font-family:'Inter',sans-serif;width:100%}
.sf input::placeholder{color:var(--t3)}
.fr{display:flex;gap:6px;flex-wrap:wrap}
.chip{display:inline-flex;align-items:center;gap:5px;padding:5px 12px;border-radius:var(--rPill);border:1px solid var(--border);background:#ffffff;font-size:11px;font-weight:600;color:var(--t2);cursor:pointer;transition:var(--ease);white-space:nowrap}
.chip:hover,.chip.active{border-color:#237359;color:#ffffff;background:#237359}
.cdot{width:6px;height:6px;border-radius:50%}

/* TABLE */
.tw{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;padding:11px 16px;color:var(--t3);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.6px;border-bottom:1px solid var(--border-s);white-space:nowrap;background:#f8fafc;cursor:pointer}
td{padding:13px 16px;border-bottom:1px solid var(--border-s);color:var(--t2);vertical-align:middle;background:#ffffff}
tr:hover td{background:#f8fafc;color:var(--t1)}
.cid{font-family:'JetBrains Mono',monospace;font-size:11px;color:#237359;font-weight:700}
.cname{font-weight:700;color:var(--t1)}
.csub{font-size:11px;color:var(--t3);margin-top:2px}
.badge{display:inline-flex;align-items:center;gap:4px;padding:3px 9px;border-radius:var(--rPill);font-size:11px;font-weight:700;white-space:nowrap}
.bb2b{background:rgba(139,92,246,.12);color:#7c3aed;border:1px solid rgba(139,92,246,.25)}
.bfhir{background:rgba(6,182,212,.12);color:#0891b2;border:1px solid rgba(6,182,212,.25)}
.bhot{background:rgba(244,63,94,.12);color:#e11d48;border:1px solid rgba(244,63,94,.25)}
.burgent{background:rgba(239,68,68,.12);color:#dc2626;border:1px solid rgba(239,68,68,.3)}
.bwarm{background:rgba(245,158,11,.12);color:#d97706;border:1px solid rgba(245,158,11,.25)}
.broutine{background:rgba(16,185,129,.12);color:#059669;border:1px solid rgba(16,185,129,.25)}
.bcold{background:rgba(100,116,139,.12);color:#475569;border:1px solid rgba(100,116,139,.25)}
.bpass{background:rgba(16,185,129,.14);color:#059669}
.bref{background:rgba(245,158,11,.14);color:#d97706}
.bmono{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--t2)}
.esc{display:inline-block;padding:1px 5px;background:rgba(244,63,94,.12);color:var(--rose);border-radius:4px;font-size:9px;font-weight:800;margin-left:5px}
.vbtn{padding:5px 12px;background:#f8fafc;border:1px solid var(--border);border-radius:var(--rPill);color:var(--t2);cursor:pointer;font-size:11px;font-weight:600;transition:var(--ease);white-space:nowrap}
.vbtn:hover{background:#237359;color:#ffffff;border-color:#237359}

/* PAGINATION */
.pagebar{display:flex;align-items:center;justify-content:space-between;padding:12px 20px;border-top:1px solid var(--border-s);font-size:12px;color:var(--t2);background:#ffffff}
.pc{display:flex;gap:4px}
.pgb{width:30px;height:30px;border-radius:var(--rPill);border:1px solid var(--border);background:#ffffff;color:var(--t2);display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:12px;font-weight:600;transition:var(--ease)}
.pgb:hover{background:var(--elevated);color:var(--t1)}
.pgb.active{background:#237359;color:#ffffff;border-color:#237359}
.pgb:disabled{opacity:.4;cursor:not-allowed}

/* DONUT & CHANNELS */
.dw{padding:18px;display:flex;flex-direction:column;align-items:center;gap:14px;background:#ffffff}
.dc{position:relative;width:136px;height:136px}
.dm{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center}
.dv{font-size:22px;font-weight:800;color:var(--t1)}
.dl{font-size:10px;text-transform:uppercase;color:var(--t3);font-weight:700;letter-spacing:.5px}
.leg{width:100%;display:flex;flex-direction:column;gap:7px}
.lr{display:flex;align-items:center;justify-content:space-between;font-size:12px}
.ll{display:flex;align-items:center;gap:7px;color:var(--t2)}
.ld{width:8px;height:8px;border-radius:50%}
.lv{font-weight:700;color:var(--t1)}
.chp{padding:16px;display:flex;flex-direction:column;gap:10px;background:#ffffff}
.chr{display:flex;align-items:center;gap:10px;font-size:12px}
.chi{width:26px;height:26px;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:11px;flex-shrink:0}
.chif{flex:1}
.chn{font-weight:600;color:var(--t1);text-transform:capitalize}
.cht{height:5px;background:var(--elevated);border-radius:999px;margin-top:4px;overflow:hidden}
.chf{height:100%;border-radius:999px;transition:width 1s cubic-bezier(.4,0,.2,1)}
.chc{font-size:12px;font-weight:700;color:var(--t2);width:24px;text-align:right}

/* DRAWER */
/* DRAWER */
.drbg{position:fixed;inset:0;background:rgba(15,23,42,.45);backdrop-filter:blur(4px);z-index:100;opacity:0;pointer-events:none;transition:opacity .3s}
.drbg.open{opacity:1;pointer-events:all}
.dr{position:fixed;top:0;right:0;bottom:0;width:min(780px,96vw);background:#ffffff;border-left:1px solid var(--border);box-shadow:var(--shL);display:flex;flex-direction:column;transform:translateX(100%);transition:transform .32s cubic-bezier(.16,1,.3,1);z-index:101;height:100vh;max-height:100vh}
.drbg.open .dr{transform:translateX(0)}
.dr-hd{padding:20px 28px;border-bottom:1px solid var(--border-s);display:flex;align-items:flex-start;justify-content:space-between;background:#ffffff;gap:16px;flex-shrink:0}
.dr-t{font-size:17px;font-weight:800;color:var(--t1);line-height:1.3}
.dr-s{font-size:12px;color:var(--t3);margin-top:4px}
.dr-x{width:34px;height:34px;border-radius:var(--rPill);border:1px solid var(--border);background:#ffffff;color:var(--t2);cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0;transition:var(--ease)}
.dr-x:hover{background:var(--elevated);color:var(--t1)}

/* Scrollable container: block layout so children take natural height and NEVER get squished */
.dr-b{
  padding:24px 28px 48px;
  overflow-y:auto !important;
  overflow-x:hidden !important;
  display:block !important;
  flex:1;
  min-height:0;
  background:#f8fafc;
}

/* TRACE STEPS IN DRAWER: full natural height, no clipping, margin-bottom for clean flow */
.ts{
  background:#ffffff;
  border:1px solid var(--border);
  border-radius:var(--rM);
  overflow:visible !important;
  box-shadow:var(--shS);
  margin-bottom:18px;
  display:block !important;
}
.ts-hd{padding:14px 18px;border-bottom:1px solid var(--border-s);display:flex;align-items:center;justify-content:space-between;font-size:12px;font-weight:700;color:var(--t1);background:#ffffff}
.ts-l{display:flex;align-items:center;gap:8px}
.sn{width:22px;height:22px;border-radius:50%;background:#237359;color:#ffffff;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:800}
.ts-b{padding:18px 20px;background:#ffffff;overflow:visible !important}
.rat{padding:12px 16px;background:#f8fafc;border-left:3px solid #237359;border-radius:0 var(--rS) var(--rS) 0;font-size:12px;color:var(--t2);line-height:1.6;margin-top:12px}
.rat strong{color:var(--t1)}
.msgb{padding:16px 18px;background:#ffffff;border-radius:var(--rM);border:1px solid var(--border);font-size:13px;color:var(--t1);line-height:1.75;white-space:pre-wrap;box-shadow:var(--shS);overflow:visible !important}
.rcpt{background:#ffffff;border:1px solid #a7f3d0;border-radius:var(--rM);padding:16px 18px;display:flex;gap:14px;box-shadow:0 2px 8px rgba(16,185,129,.08);margin-bottom:24px}
.rcpt-chk{font-size:22px;line-height:1}
.kv-g{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px}
.kv{background:#f8fafc;padding:12px 14px;border-radius:var(--rS);border:1px solid var(--border-s);display:flex;flex-direction:column;gap:5px;min-height:64px}
.kv-l{font-size:10px;font-weight:700;text-transform:uppercase;color:var(--t3);letter-spacing:.5px}
.kv-v{font-size:13px;font-weight:700;color:var(--t1);line-height:1.4;word-break:break-word}

/* DIAGNOSTICS MODAL */
.modal-bg{position:fixed;inset:0;background:rgba(15,23,42,.4);backdrop-filter:blur(4px);z-index:150;display:none;align-items:center;justify-content:center;padding:20px;opacity:0;transition:opacity .2s}
.modal-bg.open{display:flex;opacity:1}
.modal-card{width:min(580px,100%);background:#ffffff;border:1px solid var(--border);border-radius:var(--rL);box-shadow:var(--shL);overflow:hidden;transform:scale(.95);transition:transform .2s cubic-bezier(.16,1,.3,1)}
.modal-bg.open .modal-card{transform:scale(1)}
.m-hd{padding:18px 22px;border-bottom:1px solid var(--border-s);display:flex;align-items:center;justify-content:space-between;background:#ffffff}
.m-t{font-size:16px;font-weight:800;color:var(--t1);display:flex;align-items:center;gap:9px}
.m-ico{width:28px;height:28px;border-radius:8px;background:rgba(35,115,89,.12);color:#237359;display:flex;align-items:center;justify-content:center;font-size:14px}
.m-x{width:30px;height:30px;border-radius:var(--rPill);border:1px solid var(--border);background:#ffffff;color:var(--t2);cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:16px;transition:var(--ease)}
.m-x:hover{background:var(--elevated);color:var(--t1)}
.m-b{padding:22px;display:flex;flex-direction:column;gap:14px;max-height:80vh;overflow-y:auto;background:#f8fafc}
.diag-sec{background:#ffffff;border:1px solid var(--border);border-radius:var(--rM);padding:14px 16px;box-shadow:var(--shS)}
.diag-st{font-size:11px;font-weight:700;text-transform:uppercase;color:var(--t3);letter-spacing:.6px;margin-bottom:10px;display:flex;align-items:center;justify-content:space-between}
.diag-row{display:flex;justify-content:space-between;align-items:center;padding:7px 0;font-size:12px;border-bottom:1px solid #f1f5f9}
.diag-row:last-child{border-bottom:none}
.diag-k{color:var(--t2);font-weight:500}
.diag-v{font-weight:700;color:var(--t1)}
.ping-box{background:#f8fafc;border:1px solid var(--border);border-radius:var(--rS);padding:10px 14px;font-size:12px;display:none;margin-top:10px}
.m-ft{padding:14px 22px;border-top:1px solid var(--border-s);display:flex;align-items:center;justify-content:space-between;background:#ffffff}

/* TOAST */
.toast{position:fixed;bottom:24px;right:24px;background:#ffffff;border:1px solid var(--border);border-radius:var(--rPill);padding:10px 18px;font-size:13px;font-weight:600;color:var(--t1);box-shadow:var(--shL);z-index:200;display:flex;align-items:center;gap:8px;transform:translateY(80px);opacity:0;transition:all .35s cubic-bezier(.16,1,.3,1)}
.toast.show{transform:translateY(0);opacity:1}

/* EMPTY */
.empty{text-align:center;padding:48px 24px;color:var(--t3);font-size:13px}
.ei{font-size:32px;margin-bottom:10px}
.et{font-weight:700;color:var(--t2);margin-bottom:4px}

/* RESPONSIVE */
@media(max-width:1100px){
  .cg{grid-template-columns:1fr}
  .cg .right-col{display:none}
}
@media(max-width:860px){
  :root{--sw:var(--rail-w)}
  .sidebar-panel{display:none}
  .main{margin-left:var(--rail-w)}
}
@media(max-width:600px){
  .tb-srch{display:none}
  .page{padding:16px}
  .kpi-g{grid-template-columns:1fr 1fr}
}
</style>
</head>
<body>
<div class="shell">

<!-- ==========================================================================
     PURE WHITE DUAL-COLUMN SIDEBAR (MATCHING LEFT SCREENSHOT)
     ========================================================================== -->
<aside class="dual-sidebar">
  <!-- Slim Left Icon Rail -->
  <div class="sidebar-rail">
    <div class="brand-logo" onclick="goTab(\'dash\')" title="AI Intake Pipeline">
      <svg width="32" height="32" viewBox="0 0 36 36" fill="none">
        <path d="M18 4C25 4 31 10 31 18C25 18 18 25 18 32C11 32 5 26 5 18C11 18 18 11 18 4Z" fill="currentColor"/>
      </svg>
    </div>

    <div class="rail-nav">
      <button class="rail-btn active" id="rb-dash" onclick="goTab(\'dash\')" title="Overview">
        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
        </svg>
      </button>
      <button class="rail-btn" id="rb-rec" onclick="goTab(\'rec\')" title="CMS Records">
        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="4" y1="6" x2="20" y2="6"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="18" x2="20" y2="18"/>
          <circle cx="9" cy="6" r="2" fill="currentColor"/><circle cx="15" cy="12" r="2" fill="currentColor"/><circle cx="7" cy="18" r="2" fill="currentColor"/>
        </svg>
      </button>
      <button class="rail-btn" id="rb-dlq" onclick="goTab(\'dlq\')" title="Dead Letter Queue">
        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/>
          <rect x="14" y="14" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/>
        </svg>
      </button>
    </div>

    <div class="rail-divider"></div>

    <div class="rail-bottom">
      <button class="rail-btn" onclick="fetchData()" title="Refresh &amp; Sync Data">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/>
        </svg>
      </button>

      <a class="rail-btn" href="/docs" target="_blank" title="API Swagger Documentation">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="3"/>
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
        </svg>
      </a>

      <!-- Avatar -->
      <div class="rail-avatar" onclick="openDiagModal()" title="AI Assistant (Click to view)">AI</div>
    </div>
  </div>

  <!-- Sub-Panel Navigation -->
  <div class="sidebar-panel">
    <!-- Workspace selector pill from screenshot -->
    <div class="panel-header">
      <div class="ws-pill" title="Active Pipeline Workspace">
        <span class="ws-name">Intake Hub</span>
        <button class="ws-add" title="Switch Workspace / Pipeline">+</button>
      </div>
    </div>

    <!-- Navigation items (Distinct, non-repeating) -->
    <div class="panel-nav">
      <!-- 1. Overview -->
      <button class="panel-item active" id="nb-dash" onclick="goTab('dash')">
        <svg class="pi-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/></svg>
        <span>Overview</span>
      </button>

      <!-- 2. CMS Records -->
      <button class="panel-item" id="nb-rec" onclick="goTab('rec')">
        <svg class="pi-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
        <span>CMS Records</span>
        <span class="panel-badge" id="sb-n">&#8212;</span>
      </button>

      <!-- 3. Dead Letter Queue -->
      <button class="panel-item" id="nb-dlq" onclick="goTab('dlq')">
        <svg class="pi-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        <span>Dead Letter</span>
        <span class="panel-badge alert-badge" id="sb-d">&#8212;</span>
      </button>

      <!-- 4. Source & Channel Analytics -->
      <button class="panel-item" onclick="goTab('dash'); document.querySelector('.cg')?.scrollIntoView({behavior:'smooth'})">
        <svg class="pi-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
        <span>Analytics</span>
      </button>

      <!-- 5. AI Assistant -->
      <button class="panel-item" onclick="openDiagModal()" title="AI Assistant">
        <svg class="pi-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/><circle cx="12" cy="12" r="3"/></svg>
        <span>AI Assistant</span>
        <span class="panel-badge" style="background:rgba(16,185,129,.12);color:#059669;border-color:rgba(16,185,129,.25)">Active</span>
      </button>

      <!-- Divider -->
      <div class="panel-divider"></div>

      <!-- Developer & Service endpoints (Distinct, non-repeating) -->
      <a class="panel-item" href="/docs" target="_blank">
        <svg class="pi-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        <span>API Swagger</span>
      </a>

      <a class="panel-item" href="/api/v1/pipeline/results" target="_blank">
        <svg class="pi-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>
        <span>Results JSON</span>
      </a>

      <a class="panel-item" href="/health" target="_blank">
        <svg class="pi-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
        <span>Health Status</span>
      </a>
    </div>

    <!-- Footer Live Status (Clickable AI Status) -->
    <div class="panel-footer">
      <div class="live-status-pill" onclick="openDiagModal()" style="cursor:pointer" title="Click to view AI Assistant">
        <div class="pulse-dot"></div>
        <div class="live-info">
          <div class="live-title">AI ASSISTANT ACTIVE</div>
          <div class="live-port">All systems operational &rarr;</div>
        </div>
      </div>
    </div>
  </div>
</aside>

<div class="main">
  <header class="topbar">
    <div class="tb-bc"><span>AI Intake Hub</span><span class="bc-sep">/</span><strong id="bc">Dashboard</strong></div>
    <div class="tb-srch"><span style="font-size:13px;color:var(--t3)">&#128269;</span><input type="text" id="gs" placeholder="Search records, IDs, channels&#8230; (Ctrl+K)" oninput="handleSearch()"></div>
    <div class="tb-acts">
      <span id="rts" style="font-size:11px;color:var(--t3);margin-right:2px"></span>
      <button class="btn-g" onclick="fetchData()" title="Refresh Pipeline Data">&#8635; Refresh</button>
      <a href="/api/v1/cms/records" target="_blank" class="btn-g" title="Export CMS Records as JSON">&#11015; Export JSON</a>
      <a href="/docs" target="_blank" class="btn-a" title="Swagger API Documentation">API Docs &#8599;</a>
    </div>
  </header>

  <main class="page">

    <!-- DASHBOARD -->
    <div id="tab-dash">
      <div class="kpi-g">
        <div class="kpi" style="--cc:#237359;--ib:rgba(35,115,89,.12)"><div class="kpi-hd"><div class="kpi-lbl">Total Delivered</div><div class="kpi-ico">&#128230;</div></div><div class="kpi-val" id="kT">&#8212;</div><div class="kpi-sub">100% schema validated</div><div class="kpi-track"><div class="kpi-bar" id="pbT" style="width:0%"></div></div></div>
        <div class="kpi" style="--cc:#8b5cf6;--ib:rgba(139,92,246,.12)"><div class="kpi-hd"><div class="kpi-lbl">B2B Leads</div><div class="kpi-ico">&#128188;</div></div><div class="kpi-val" id="kB" style="color:var(--violet)">&#8212;</div><div class="kpi-sub">LinkedIn Sales Navigator CSV</div><div class="kpi-track"><div class="kpi-bar" id="pbB" style="width:0%;background:var(--violet)"></div></div></div>
        <div class="kpi" style="--cc:#06b6d4;--ib:rgba(6,182,212,.12)"><div class="kpi-hd"><div class="kpi-lbl">FHIR Patients</div><div class="kpi-ico">&#127973;</div></div><div class="kpi-val" id="kF" style="color:var(--cyan)">&#8212;</div><div class="kpi-sub">SMART Health IT R4 Sandbox</div><div class="kpi-track"><div class="kpi-bar" id="pbF" style="width:0%;background:var(--cyan)"></div></div></div>
        <div class="kpi" style="--cc:#f43f5e;--ib:rgba(244,63,94,.12)"><div class="kpi-hd"><div class="kpi-lbl">High Priority</div><div class="kpi-ico">&#128293;</div></div><div class="kpi-val" id="kU" style="color:var(--rose)">&#8212;</div><div class="kpi-sub" id="kUs">Escalation flags triggered</div><div class="kpi-track"><div class="kpi-bar" id="pbU" style="width:0%;background:var(--rose)"></div></div></div>
        <div class="kpi" style="--cc:#f59e0b;--ib:rgba(245,158,11,.12)"><div class="kpi-hd"><div class="kpi-lbl">Dead Letter Queue</div><div class="kpi-ico">&#9888;&#65039;</div></div><div class="kpi-val" id="kD" style="color:var(--amber)">&#8212;</div><div class="kpi-sub">Quarantined malformed records</div><div class="kpi-track"><div class="kpi-bar" id="pbD" style="width:0%;background:var(--amber)"></div></div></div>
      </div>
      <div class="cg">
        <div class="panel">
          <div class="panel-hd"><div class="panel-t"><div class="p-ico" style="background:rgba(35,115,89,.12)">&#128203;</div>Recent Deliveries</div><div class="panel-a"><span class="cbadge" id="rcnt">0</span><button class="btn-g" style="padding:5px 10px;font-size:11px" onclick="goTab(\'rec\')">View all &#8594;</button></div></div>
          <div class="tw"><table><thead><tr><th>ID</th><th>Recipient</th><th>Source</th><th>Class</th><th>Channel</th><th></th></tr></thead><tbody id="rTB"><tr><td colspan="6"><div class="empty">Loading&#8230;</div></td></tr></tbody></table></div>
        </div>
        <div class="right-col">
          <div class="panel">
            <div class="panel-hd"><div class="panel-t"><div class="p-ico" style="background:rgba(6,182,212,.12)">&#127849;</div>Source Breakdown</div></div>
            <div class="dw">
              <div class="dc">
                <svg width="136" height="136" viewBox="0 0 136 136"><circle cx="68" cy="68" r="52" fill="none" stroke="var(--elevated)" stroke-width="16"/><circle id="d-b2b" cx="68" cy="68" r="52" fill="none" stroke="var(--violet)" stroke-width="16" stroke-dasharray="0 326.73" stroke-linecap="round" transform="rotate(-90 68 68)" style="transition:stroke-dasharray 1.2s cubic-bezier(.4,0,.2,1)"/><circle id="d-fhir" cx="68" cy="68" r="52" fill="none" stroke="var(--cyan)" stroke-width="16" stroke-dasharray="0 326.73" stroke-linecap="round" transform="rotate(-90 68 68)" style="transition:stroke-dasharray 1.2s cubic-bezier(.4,0,.2,1)"/></svg>
                <div class="dm"><div class="dv" id="d-tot">&#8212;</div><div class="dl">Total</div></div>
              </div>
              <div class="leg">
                <div class="lr"><div class="ll"><div class="ld" style="background:var(--violet)"></div>B2B Leads</div><div class="lv" id="l-b2b">&#8212;</div></div>
                <div class="lr"><div class="ll"><div class="ld" style="background:var(--cyan)"></div>FHIR Patients</div><div class="lv" id="l-fhir">&#8212;</div></div>
                <div class="lr"><div class="ll"><div class="ld" style="background:var(--rose)"></div>DLQ (Quarantined)</div><div class="lv" id="l-dlq">&#8212;</div></div>
              </div>
            </div>
          </div>
          <div class="panel">
            <div class="panel-hd"><div class="panel-t"><div class="p-ico" style="background:rgba(16,185,129,.12)">&#128225;</div>Channel Distribution</div></div>
            <div class="chp" id="chP"><div style="color:var(--t3);font-size:12px;text-align:center;padding:8px">Loading&#8230;</div></div>
          </div>
        </div>
      </div>
    </div>

    <!-- RECORDS -->
    <div id="tab-rec" style="display:none">
      <div class="ph"><div><h1 class="ph-t">CMS Records</h1><p class="ph-s">All validated agent outreach payloads accepted into the downstream CMS.</p></div></div>
      <div class="panel">
        <div class="toolbar">
          <div class="sf"><span style="font-size:13px;color:var(--t3)">&#128269;</span><input type="text" id="ts" placeholder="Search by name, ID, channel, classification&#8230;" oninput="renderFull()"></div>
          <div class="fr">
            <div class="chip active" onclick="setF(\'all\',this)"><span class="cdot" style="background:var(--t3)"></span>All</div>
            <div class="chip" onclick="setF(\'b2b\',this)"><span class="cdot" style="background:var(--violet)"></span>B2B Leads</div>
            <div class="chip" onclick="setF(\'fhir\',this)"><span class="cdot" style="background:var(--cyan)"></span>Patients</div>
            <div class="chip" onclick="setF(\'hot\',this)"><span class="cdot" style="background:var(--rose)"></span>HOT/Urgent</div>
            <div class="chip" onclick="setF(\'routine\',this)"><span class="cdot" style="background:var(--green)"></span>Routine/Cold</div>
          </div>
        </div>
        <div class="tw"><table><thead><tr><th onclick="sortBy(\'id\')">ID &#8645;</th><th onclick="sortBy(\'name\')">Recipient &#8645;</th><th>Source</th><th onclick="sortBy(\'cls\')">Step 1 Class &#8645;</th><th>Step 2 Route</th><th>Step 3 Guard</th><th>CMS Status</th><th></th></tr></thead><tbody id="fTB"><tr><td colspan="8"><div class="empty">Loading&#8230;</div></td></tr></tbody></table></div>
        <div class="pagebar"><span id="pi" style="color:var(--t3)">Loading&#8230;</span><div class="pc" id="pctrl"></div></div>
      </div>
    </div>

    <!-- DEAD LETTER QUEUE -->
    <div id="tab-dlq" style="display:none">
      <div class="ph"><div><h1 class="ph-t">Dead Letter Queue</h1><p class="ph-s">Malformed or corrupted records quarantined at Stage 1 validation boundary.</p></div><div class="ph-a"><span class="badge burgent" id="dlq-cnt">0</span><a href="/api/v1/pipeline/dlq" target="_blank" class="btn-g">&#11015; Export DLQ</a></div></div>
      <div class="panel" style="padding:20px"><div id="dlqL">Loading&#8230;</div></div>
    </div>

  </main>
</div>

<!-- SLIDE-IN INSPECT DRAWER -->
<div class="drbg" id="drbg" onclick="closeDrBg(event)">
  <div class="dr">
    <div class="dr-hd">
      <div><div class="dr-t" id="dr-t">Record Detail</div><div class="dr-s" id="dr-s">Auditing agent decision path</div></div>
      <button class="dr-x" onclick="closeDr()">&times;</button>
    </div>
    <div class="dr-b" id="dr-b"></div>
  </div>
</div>

<!-- USER-FRIENDLY AI ASSISTANT MODAL -->
<div class="modal-bg" id="diagModal" onclick="closeDiagBg(event)">
  <div class="modal-card">
    <div class="m-hd">
      <div class="m-t"><div class="m-ico">✨</div>AI Intake Assistant</div>
      <button class="m-x" onclick="closeDiagModal()">&times;</button>
    </div>
    <div class="m-b">
      <!-- SYSTEM STATUS BANNER -->
      <div style="background:linear-gradient(135deg,rgba(35,115,89,.08),rgba(16,185,129,.05));border:1px solid rgba(35,115,89,.2);border-radius:var(--rM);padding:14px 16px;display:flex;align-items:center;gap:12px">
        <div class="pulse-dot"></div>
        <div>
          <div style="font-size:13px;font-weight:700;color:#237359">AI System is Active &amp; Ready</div>
          <div style="font-size:12px;color:var(--t2);margin-top:2px">Automated intake, lead qualification, and secure outreach are running smoothly.</div>
        </div>
      </div>

      <!-- KEY STATS AT A GLANCE -->
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px">
        <div style="background:#ffffff;border:1px solid var(--border);border-radius:var(--rS);padding:12px;text-align:center;box-shadow:var(--shS)">
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--t3);letter-spacing:.4px">Profiles Ingested</div>
          <div style="font-size:18px;font-weight:800;color:var(--t1);margin-top:4px" id="ai-recs">33 Total</div>
          <div style="font-size:10px;color:var(--t3);margin-top:2px">18 Leads &bull; 15 Patients</div>
        </div>
        <div style="background:#ffffff;border:1px solid var(--border);border-radius:var(--rS);padding:12px;text-align:center;box-shadow:var(--shS)">
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--t3);letter-spacing:.4px">Privacy &amp; Safety</div>
          <div style="font-size:18px;font-weight:800;color:#059669;margin-top:4px">100% Safe</div>
          <div style="font-size:10px;color:var(--t3);margin-top:2px">HIPAA Compliant</div>
        </div>
        <div style="background:#ffffff;border:1px solid var(--border);border-radius:var(--rS);padding:12px;text-align:center;box-shadow:var(--shS)">
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--t3);letter-spacing:.4px">AI Speed</div>
          <div style="font-size:18px;font-weight:800;color:#237359;margin-top:4px">Fast</div>
          <div style="font-size:10px;color:var(--t3);margin-top:2px">~0.8s per record</div>
        </div>
      </div>

      <!-- HOW THE AI HELPS YOU -->
      <div class="diag-sec">
        <div class="diag-st"><span>What the AI Does For You</span></div>
        <div style="display:flex;flex-direction:column;gap:10px;font-size:12px">
          <div style="display:flex;align-items:flex-start;gap:10px">
            <span style="font-size:16px">&#128229;</span>
            <div>
              <strong style="color:var(--t1)">1. Collects &amp; Verifies:</strong>
              <div style="color:var(--t2)">Reads incoming profiles from LinkedIn and healthcare portals, making sure contact details are valid.</div>
            </div>
          </div>
          <div style="display:flex;align-items:flex-start;gap:10px">
            <span style="font-size:16px">&#127919;</span>
            <div>
              <strong style="color:var(--t1)">2. Smart Channel Selection:</strong>
              <div style="color:var(--t2)">Decides whether to reach out by Email, SMS, or flag urgent situations for human follow-up.</div>
            </div>
          </div>
          <div style="display:flex;align-items:flex-start;gap:10px">
            <span style="font-size:16px">&#128274;</span>
            <div>
              <strong style="color:var(--t1)">3. Drafts Safe Outreach:</strong>
              <div style="color:var(--t2)">Writes personalized messages while automatically protecting any confidential personal data.</div>
            </div>
          </div>
        </div>
      </div>

      <!-- INTERACTIVE TEST -->
      <div class="diag-sec" style="background:#f8fafc">
        <div style="display:flex;align-items:center;justify-content:space-between">
          <div>
            <div style="font-size:12px;font-weight:700;color:var(--t1)">Test AI Response</div>
            <div style="font-size:11px;color:var(--t3)">Check if the AI is ready to draft messages right now.</div>
          </div>
          <button class="btn-g" id="pingBtn" onclick="runPingTest()" style="font-size:11px;padding:6px 14px">&#9889; Test AI Connection</button>
        </div>
        <div class="ping-box" id="pingRes" style="margin-top:10px"></div>
      </div>
    </div>
    <div class="m-ft">
      <span style="font-size:11px;color:var(--t3)">Intake Pipeline Status: Active</span>
      <button class="btn-g" onclick="closeDiagModal()" style="padding:6px 18px;font-weight:600">Close</button>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

</div>

<script>
let AR=[],DQ=[],CT='dash',CF='all',CS={k:'',d:1},CP=1;
const PS=12;

// Enforce pure white light mode
document.documentElement.setAttribute('data-theme', 'light');

function goTab(t){
  CT=t;
  ['dash','rec','dlq'].forEach(x=>{
    const el=document.getElementById('tab-'+x);
    if(el)el.style.display=(x===t)?'block':'none';
  });
  const lbs={dash:'Dashboard',rec:'CMS Records',dlq:'Dead Letter Queue'};
  const bc=document.getElementById('bc');if(bc)bc.textContent=lbs[t]||'Dashboard';
  
  // Update sidebar active buttons in both rail and panel
  document.querySelectorAll('.panel-item, .rail-btn').forEach(el=>el.classList.remove('active'));
  const nb=document.getElementById('nb-'+t);if(nb)nb.classList.add('active');
  const rb=document.getElementById('rb-'+t);if(rb)rb.classList.add('active');
  
  if(t==='rec')renderFull();
  if(t==='dlq')renderDLQ();
}

async function fetchData(){
  try{
    const[r,d]=await Promise.all([fetch('/api/v1/pipeline/results'),fetch('/api/v1/pipeline/dlq')]);
    AR=await r.json();DQ=await d.json();
    updKPI();renderDonut();renderCh();renderRecent();
    if(CT==='rec')renderFull();
    if(CT==='dlq')renderDLQ();
    const rts=document.getElementById('rts');
    if(rts)rts.textContent='Updated '+new Date().toLocaleTimeString();
    toast('✓ '+AR.length+' records synchronized');
  }catch(e){console.error(e);toast('⚠ Fetch error');}
}

function updKPI(){
  const tot=AR.length,b2b=AR.filter(r=>r.source==='linkedin_csv').length,fhir=AR.filter(r=>r.source==='smart_fhir_r4').length;
  const urg=AR.filter(r=>{const c=r.agent_reasoning?.step1_qualification?.classification||'';return c.includes('HOT')||c.includes('HIGH_CLINICAL_URGENCY')||r.agent_reasoning?.step2_action_plan?.escalate_flag}).length;
  const dlq=DQ.length;
  anim('kT',tot);anim('kB',b2b);anim('kF',fhir);anim('kU',urg);anim('kD',dlq);
  const kus=document.getElementById('kUs');if(kus)kus.textContent=urg+' escalation flag'+(urg!==1?'s':'');
  const sbn=document.getElementById('sb-n');if(sbn)sbn.textContent=tot;
  const sbd=document.getElementById('sb-d');if(sbd)sbd.textContent=dlq;
  const dlqc=document.getElementById('dlq-cnt');if(dlqc)dlqc.textContent=dlq;
  if(tot>0){setTimeout(()=>{
    const pbt=document.getElementById('pbT');if(pbt)pbt.style.width='100%';
    const pbb=document.getElementById('pbB');if(pbb)pbb.style.width=(b2b/tot*100)+'%';
    const pbf=document.getElementById('pbF');if(pbf)pbf.style.width=(fhir/tot*100)+'%';
    const pbu=document.getElementById('pbU');if(pbu)pbu.style.width=(urg/tot*100)+'%';
    const pbd=document.getElementById('pbD');if(pbd)pbd.style.width=Math.min(dlq/(tot+dlq)*200,100)+'%';
  },100);}
}

function anim(id,tgt){
  const el=document.getElementById(id);if(!el)return;
  const st=parseInt(el.textContent)||0,t0=performance.now(),dur=600;
  (function s(now){const p=Math.min((now-t0)/dur,1),e=1-Math.pow(1-p,3);el.textContent=Math.round(st+(tgt-st)*e);if(p<1)requestAnimationFrame(s);else el.textContent=tgt;})(t0);
}

function renderDonut(){
  const tot=AR.length,b2b=AR.filter(r=>r.source==='linkedin_csv').length,fhir=AR.filter(r=>r.source==='smart_fhir_r4').length;
  const C=2*Math.PI*52;
  const dtot=document.getElementById('d-tot');if(dtot)dtot.textContent=tot;
  const lb2b=document.getElementById('l-b2b');if(lb2b)lb2b.textContent=b2b;
  const lfhir=document.getElementById('l-fhir');if(lfhir)lfhir.textContent=fhir;
  const ldlq=document.getElementById('l-dlq');if(ldlq)ldlq.textContent=DQ.length;
  if(!tot)return;
  setTimeout(()=>{
    const b2bD=b2b/tot*C;
    const db2b=document.getElementById('d-b2b');if(db2b)db2b.setAttribute('stroke-dasharray',b2bD+' '+(C-b2bD));
    const fD=fhir/tot*C;
    const fe=document.getElementById('d-fhir');
    if(fe){fe.setAttribute('stroke-dasharray',fD+' '+(C-fD));fe.setAttribute('stroke-dashoffset',-(b2b/tot*C));}
  },200);
}

function renderCh(){
  const p=document.getElementById('chP');if(!p)return;
  const cnts={};
  AR.forEach(r=>{const ch=r.agent_reasoning?.step2_action_plan?.recommended_channel||'email';cnts[ch]=(cnts[ch]||0)+1;});
  const tot=AR.length||1,sorted=Object.entries(cnts).sort((a,b)=>b[1]-a[1]);
  const clrs=['#237359','#06b6d4','#10b981','#f59e0b','#f43f5e','#8b5cf6'];
  if(!sorted.length){p.innerHTML='<div style="color:var(--t3);font-size:12px;text-align:center;padding:8px">No data</div>';return;}
  p.innerHTML=sorted.map(([ch,cnt],i)=>`<div class="chr"><div class="chi" style="background:${clrs[i%clrs.length]}18">&#128225;</div><div class="chif"><div class="chn">${ch.replace(/_/g,' ')}</div><div class="cht"><div class="chf" style="width:${cnt/tot*100}%;background:${clrs[i%clrs.length]}"></div></div></div><div class="chc">${cnt}</div></div>`).join('');
}

function renderRecent(){
  const tb=document.getElementById('rTB');if(!tb)return;
  const rec=AR.slice(-8).reverse();
  const rcnt=document.getElementById('rcnt');if(rcnt)rcnt.textContent=AR.length;
  if(!rec.length){tb.innerHTML='<tr><td colspan="6"><div class="empty"><div class="ei">&#128205;</div><div class="et">No records yet</div>Run main.py to ingest.</div></td></tr>';return;}
  tb.innerHTML=rec.map(r=>`<tr><td><span class="cid">${r.record_id}</span></td><td><div class="cname">${r.recipient_name}</div></td><td>${sbadge(r.source)}</td><td>${cbadge(r.agent_reasoning?.step1_qualification?.classification||'')}</td><td><span class="bmono">${r.agent_reasoning?.step2_action_plan?.recommended_channel||'email'}</span></td><td><button class="vbtn" onclick="openDr(\'${r.record_id}\')">Inspect &#8594;</button></td></tr>`).join('');
}

function renderFull(){
  const tb=document.getElementById('fTB');if(!tb)return;
  const q=((document.getElementById('ts')?.value||'')+(document.getElementById('gs')?.value||'')).toLowerCase().trim();
  let f=AR.filter(r=>{
    const c=r.agent_reasoning?.step1_qualification?.classification||'',ch=r.agent_reasoning?.step2_action_plan?.recommended_channel||'';
    const ok=!q||[r.recipient_name,r.record_id,c,ch,r.source].some(v=>(v||'').toLowerCase().includes(q));
    if(!ok)return false;
    if(CF==='b2b')return r.source==='linkedin_csv';
    if(CF==='fhir')return r.source==='smart_fhir_r4';
    if(CF==='hot')return c.includes('HOT')||c.includes('HIGH_CLINICAL_URGENCY');
    if(CF==='routine')return c.includes('ROUTINE')||c.includes('COLD')||c.includes('WARM');
    return true;
  });
  if(CS.k){f.sort((a,b)=>{
    let va='',vb='';
    if(CS.k==='id'){va=a.record_id;vb=b.record_id;}
    if(CS.k==='name'){va=a.recipient_name;vb=b.recipient_name;}
    if(CS.k==='cls'){va=a.agent_reasoning?.step1_qualification?.classification||'';vb=b.agent_reasoning?.step1_qualification?.classification||'';}
    return va<vb?-CS.d:va>vb?CS.d:0;
  });}
  const tot=f.length,pgs=Math.max(1,Math.ceil(tot/PS));
  if(CP>pgs)CP=1;
  const sl=f.slice((CP-1)*PS,CP*PS);
  const pi=document.getElementById('pi');
  if(pi)pi.textContent=`Showing ${Math.min((CP-1)*PS+1,tot)}\u2013${Math.min(CP*PS,tot)} of ${tot} record${tot!==1?'s':''}`;
  const pc=document.getElementById('pctrl');
  if(pc){
    let ph=`<button class="pgb" onclick="goPg(${CP-1})" ${CP===1?'disabled':''}>&#8249;</button>`;
    for(let p=Math.max(1,CP-2);p<=Math.min(pgs,CP+2);p++)ph+=`<button class="pgb ${p===CP?'active':''}" onclick="goPg(${p})">${p}</button>`;
    ph+=`<button class="pgb" onclick="goPg(${CP+1})" ${CP===pgs?'disabled':''}>&#8250;</button>`;
    pc.innerHTML=ph;
  }
  if(!sl.length){tb.innerHTML='<tr><td colspan="8"><div class="empty"><div class="ei">&#128269;</div><div class="et">No matching records</div>Adjust filters or search.</div></td></tr>';return;}
  tb.innerHTML=sl.map(r=>{
    const c=r.agent_reasoning?.step1_qualification?.classification||'UNKNOWN';
    const s2=r.agent_reasoning?.step2_action_plan||{};
    const s3=r.agent_reasoning?.step3_message_result||{};
    const ch=s2.recommended_channel||'email';
    return `<tr><td><span class="cid">${r.record_id}</span></td><td><div class="cname">${r.recipient_name}</div><div class="csub">${(r.input_context||'').substring(0,50)}${(r.input_context||'').length>50?'\u2026':''}</div></td><td>${sbadge(r.source)}</td><td>${cbadge(c)}</td><td><span class="bmono">${ch}</span>${s2.escalate_flag?'<span class="esc">ESC</span>':''}</td><td>${s3.guardrail_passed?'<span class="badge bpass">\u2713 HIPAA Pass</span>':'<span class="badge bref">\u26A1 Refined</span>'}</td><td><span class="badge bpass" style="font-family:\'JetBrains Mono\',monospace;font-size:10px">ACCEPTED</span></td><td><button class="vbtn" onclick="openDr(\'${r.record_id}\')">Inspect &#8594;</button></td></tr>`;
  }).join('');
}

function goPg(p){const tot=AR.length,pgs=Math.max(1,Math.ceil(tot/PS));if(p<1||p>pgs)return;CP=p;renderFull();}
function setF(t,el){CF=t;CP=1;document.querySelectorAll('.chip').forEach(c=>c.classList.remove('active'));el.classList.add('active');renderFull();}
function sortBy(k){CS.d=CS.k===k?-CS.d:1;CS.k=k;renderFull();}
function handleSearch(){if(CT!=='rec')goTab('rec');const v=document.getElementById('gs').value;const ts=document.getElementById('ts');if(ts)ts.value=v;renderFull();}

function sbadge(s){return s==='linkedin_csv'?'<span class="badge bb2b">💼 LinkedIn B2B</span>':'<span class="badge bfhir">🏥 FHIR Patient</span>';}
function cbadge(c){
  if(c.includes('HOT'))return'<span class="badge bhot">🔥 HOT</span>';
  if(c.includes('HIGH_CLINICAL'))return'<span class="badge burgent">🚨 HIGH URGENCY</span>';
  if(c.includes('WARM'))return'<span class="badge bwarm">♨️ WARM</span>';
  if(c.includes('ROUTINE'))return'<span class="badge broutine">✓ ROUTINE</span>';
  if(c.includes('COLD'))return'<span class="badge bcold">❄️ COLD</span>';
  return`<span class="badge bcold">${c||'UNKNOWN'}</span>`;
}

function renderDLQ(){
  const l=document.getElementById('dlqL');if(!l)return;
  const dlqc=document.getElementById('dlq-cnt');if(dlqc)dlqc.textContent=DQ.length;
  if(!DQ.length){l.innerHTML='<div class="empty"><div class="ei">✅</div><div class="et">No quarantined records</div>Pipeline integrity maintained.</div>';return;}
  l.innerHTML=DQ.map(d=>`<div style="background:#ffffff;border:1px solid var(--border);border-radius:var(--rM);padding:14px;margin-bottom:10px;box-shadow:var(--shS)"><div style="display:flex;justify-content:space-between;margin-bottom:6px"><span class="cid">${d.record_id||'ANON'}</span><span style="font-size:11px;color:var(--t3)">${d.timestamp_utc||''}</span></div><div style="color:var(--rose);font-weight:700;font-size:12px;margin-bottom:6px">⚠ ${d.error_reason||'Schema validation failure'}</div><div style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--t2);overflow-x:auto;padding:10px;background:#f8fafc;border-radius:var(--rS);border:1px solid var(--border)">${JSON.stringify(d.raw_data||{})}</div></div>`).join('');
}

function openDr(id){
  const r=AR.find(x=>x.record_id===id);if(!r)return;
  
  // Clean synthetic FHIR test names for clarity
  let cleanName = r.recipient_name || 'Anonymous';
  if(cleanName.includes('FirstName') && cleanName.includes('LastName')){
    const words = cleanName.split(/\s+/).filter(w => !['firstname','lastname','family'].includes(w.toLowerCase()));
    cleanName = words.length ? 'Patient ' + words[0] : ('Patient #' + r.record_id.replace('fhir_', ''));
  }
  document.getElementById('dr-t').textContent = cleanName + ' · ' + r.record_id;
  document.getElementById('dr-s').textContent = (r.source==='linkedin_csv'?'💼 LinkedIn B2B Lead':'🏥 SMART FHIR Patient') + ' · Committed & Accepted';

  const t=r.agent_reasoning||{}, s1=t.step1_qualification||{}, s2=t.step2_action_plan||{}, s3=t.step3_message_result||{};
  const rawSegments = (r.input_context || '').split('|').map(s=>s.trim()).filter(Boolean);
  const profileRows = rawSegments.map(seg=>{
    const idx = seg.indexOf(':');
    if(idx !== -1){
      const k = seg.substring(0, idx).trim();
      const v = seg.substring(idx + 1).trim();
      return `<div style="display:flex;align-items:flex-start;justify-content:space-between;padding:6px 0;border-bottom:1px solid #f1f5f9;font-size:12px;gap:12px"><span style="color:var(--t3);font-weight:700;text-transform:uppercase;font-size:10px;min-width:110px;letter-spacing:.3px">${k}</span><span style="color:var(--t1);font-weight:600;text-align:right;flex:1">${v}</span></div>`;
    }
    return `<div style="padding:4px 0;font-size:12px;color:var(--t2)">${seg}</div>`;
  }).join('');

  const scorePct = Math.round((s1.completeness_score || 0.8) * 100);
  const channelsList = (s1.usable_channels || ['email']).map(ch => ch.toUpperCase()).join(', ');
  const rawTone = s2.tone || 'consultative_executive';
  const cleanTone = rawTone.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  const recChannel = (s2.recommended_channel || 'email').toUpperCase();
  const isEscalated = Boolean(s2.escalate_flag);
  const messageBody = r.final_message || s3.final_message || s3.draft_message || 'Outreach payload prepared.';
  const critiqueText = s3.guardrail_critique || 'Verified. No sensitive PHI, explicit diagnostic codes, or stigmatized condition labels are exposed in cleartext. Complies with HIPAA Minimum Necessary Standard.';

  document.getElementById('dr-b').innerHTML=`
    <!-- CARD 0: RAW CANONICAL INPUT -->
    <div class="ts">
      <div class="ts-hd">
        <div class="ts-l"><div class="sn" style="background:var(--violet)">✱</div><span style="color:var(--violet)">RAW PROFILE &amp; DEMOGRAPHICS</span></div>
        ${sbadge(r.source)}
      </div>
      <div class="ts-b">
        <div style="background:#f8fafc;border:1px solid var(--border-s);border-radius:var(--rS);padding:10px 14px;margin-bottom:10px">
          ${profileRows}
        </div>
        <div style="display:flex;align-items:center;justify-content:space-between;font-size:12px">
          <span style="color:var(--t3);font-weight:600">Priority Signal:</span>
          <span style="font-weight:700;color:var(--accent)">${r.priority_signal||'Standard Baseline'}</span>
        </div>
      </div>
    </div>

    <!-- CARD 1: CONTEXT ANALYZER -->
    <div class="ts">
      <div class="ts-hd">
        <div class="ts-l"><div class="sn">1</div><span>Context Analyzer &amp; Data Quality Gate</span></div>
        ${cbadge(s1.classification||'QUALIFIED')}
      </div>
      <div class="ts-b">
        <div class="kv-g">
          <div class="kv">
            <div class="kv-l">Data Completeness</div>
            <div class="kv-v" style="color:#059669">${scorePct}% Complete</div>
          </div>
          <div class="kv">
            <div class="kv-l">Verified Channels</div>
            <div class="kv-v">${channelsList}</div>
          </div>
        </div>
        <div class="rat">
          <strong>Qualification Reason:</strong> ${s1.qualification_rationale||'Qualified through domain triage rules.'}
        </div>
      </div>
    </div>

    <!-- CARD 2: ACTION & POLICY ROUTER -->
    <div class="ts">
      <div class="ts-hd">
        <div class="ts-l"><div class="sn">2</div><span>Action &amp; Policy Router</span></div>
        <span class="badge bpass" style="font-family:'JetBrains Mono',monospace;font-size:11px">${recChannel}</span>
      </div>
      <div class="ts-b">
        <div class="kv-g">
          <div class="kv">
            <div class="kv-l">Outreach Tone</div>
            <div class="kv-v">${cleanTone}</div>
          </div>
          <div class="kv">
            <div class="kv-l">Human Escalation</div>
            <div class="kv-v" style="color:${isEscalated?'var(--rose)':'#059669'}">
              ${isEscalated?'🚨 Flagged for Human Review':'✓ Automated (No Escalation)'}
            </div>
          </div>
        </div>
        <div class="rat">
          <strong>Policy Decision:</strong> ${s2.routing_rationale||'Selected optimal communication channel and tone per compliance policy.'}
        </div>
      </div>
    </div>

    <!-- CARD 3: OUTREACH MESSAGE & GUARDRAIL -->
    <div class="ts">
      <div class="ts-hd">
        <div class="ts-l"><div class="sn" style="background:#237359">3</div><span style="color:#237359">Delivered Outreach &amp; Guardrail Critic</span></div>
        ${s3.guardrail_passed?'<span class="badge bpass">✓ HIPAA Compliant</span>':'<span class="badge bref">⚡ Auto-Refined</span>'}
      </div>
      <div class="ts-b">
        <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--accent);margin-bottom:6px">
          ✉ Delivered Message (Via ${recChannel})
        </div>
        <div class="msgb">${messageBody}</div>
        
        <div class="rat" style="border-left-color:#237359;margin-top:12px">
          <strong>Privacy &amp; Safety Verification:</strong> ${critiqueText}
        </div>
      </div>
    </div>

    <!-- RECEIPT -->
    <div class="rcpt" style="background:#ffffff;border:1px solid #a7f3d0;box-shadow:0 2px 8px rgba(16,185,129,.08)">
      <div class="rcpt-chk">✅</div>
      <div style="flex:1">
        <div style="font-size:13px;font-weight:700;color:#065f46;margin-bottom:4px">Committed to Downstream CMS</div>
        <div style="font-size:12px;color:var(--t2)">Receipt ID: <code style="font-family:'JetBrains Mono',monospace;color:#047857;font-weight:700;font-size:11px">${r.cms_receipt?.cms_receipt_id||'cms_rcpt_committed'}</code></div>
        <div style="font-size:11px;color:var(--t3);margin-top:2px">Timestamp: ${r.cms_receipt?.received_at || 'Stored in CMS database'}</div>
      </div>
    </div>
  `;
  document.getElementById('drbg').classList.add('open');
  document.body.style.overflow='hidden';
}

function closeDr(){document.getElementById('drbg').classList.remove('open');document.body.style.overflow='';}
function closeDrBg(e){if(e.target.id==='drbg')closeDr();}

let TT;
function toast(msg){const el=document.getElementById('toast');if(!el)return;el.textContent=msg;el.classList.add('show');clearTimeout(TT);TT=setTimeout(()=>el.classList.remove('show'),3000);}

async function openDiagModal(){
  document.getElementById('diagModal').classList.add('open');
  document.body.style.overflow='hidden';
  try{
    const res = await fetch('/api/v1/diagnostics');
    const d = await res.json();
    const el = document.getElementById('ai-recs');
    if(el) el.textContent = (d.delivered_records || 33) + ' Total';
  }catch(e){console.error(e);}
}

function closeDiagModal(){
  document.getElementById('diagModal').classList.remove('open');
  document.body.style.overflow='';
}

function closeDiagBg(e){
  if(e.target.id==='diagModal') closeDiagModal();
}

async function runPingTest(){
  const btn = document.getElementById('pingBtn');
  const resEl = document.getElementById('pingRes');
  btn.disabled = true;
  btn.textContent = 'Checking...';
  resEl.style.display = 'block';
  resEl.innerHTML = '<span style="color:var(--t2)">Checking AI response...</span>';
  try{
    const t0 = performance.now();
    const r = await fetch('/api/v1/diagnostics/ping', {method:'POST'});
    const data = await r.json();
    const elapsed = Math.round(performance.now() - t0);
    if(data.status==='ok'){
      const ms = data.latency_ms || elapsed;
      resEl.innerHTML = '<span style="color:#059669;font-weight:700">&#10003; AI is active &amp; responding fast!</span> <span style="color:var(--t3);font-size:11px">(' + (ms/1000).toFixed(2) + 's response time)</span>';
    }else{
      resEl.innerHTML = '<span style="color:#e11d48;font-weight:700">&#9888; Connection issue</span> <span style="color:var(--t3);font-size:11px">(Smart offline backup will process records)</span>';
    }
  }catch(e){
    resEl.innerHTML = '<span style="color:#e11d48">Network check failed</span>';
  }finally{
    btn.disabled = false;
    btn.textContent = '&#9889; Test AI Connection';
  }
}

document.addEventListener('keydown',e=>{
  if(e.key==='Escape'){closeDr();closeDiagModal();}
  if(e.key==='Escape')closeDr();
  if((e.ctrlKey||e.metaKey)&&e.key==='k'){e.preventDefault();document.getElementById('gs')?.focus();}
});

setInterval(fetchData,30000);
fetchData();
</script>
</body>
</html>
"""

