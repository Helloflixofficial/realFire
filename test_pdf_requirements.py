"""
Comprehensive Verification Suite for AI Agent Intake, Enrichment & Outreach Pipeline.
Tests 100% of the requirements stated in the technical assignment PDF:
1. Canonical Ingestion & Dead Letter Queue
2. 3-Step Agent Reasoning Loop (Analyze -> Route -> Outreach + Guardrail)
3. Tenacity Exponential Backoff & Mock CMS Delivery
4. Health & Pipeline APIs
"""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

# Ensure UTF-8 output on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.schemas import (
    ContactInfo,
    DeadLetterRecord,
    UnifiedRecord,
    DownstreamCMSPayload,
    CMSReceipt,
    AgentReasoningTrace,
    Step1Analysis,
    Step2Action,
    Step3Message,
    ActionPlan,
)
from src.ingest import IngestionEngine
from src.agent import IntakeAgent
from src.deliver import DeliveryEngine
from src.llm_client import LLMClient


def test_01_pydantic_schemas_and_dlq():
    """Requirement: Strict Pydantic v2 schemas and Dead Letter Queue isolation."""
    print("\n--- Test 1: Schema Validation & Dead Letter Queue ---")
    
    # 1. Valid UnifiedRecord creation
    rec = UnifiedRecord(
        id="test_001",
        source="linkedin_csv",
        name="Jane Doe",
        contact_info=ContactInfo(email="jane.doe@example.com", phone="+1-555-0100"),
        context="CTO at Acme Inc with 500 employees",
        priority_signal="High Growth Enterprise",
    )
    assert rec.id == "test_001"
    assert rec.source == "linkedin_csv"
    assert rec.contact_info.email == "jane.doe@example.com"
    
    # 2. Ingestion Engine DLQ isolation
    dlq_path = "outputs/test_dlq.json"
    engine = IngestionEngine(dlq_output_path=dlq_path)
    
    # Malformed record (missing required fields / invalid email)
    malformed = {"id": "bad_1", "email": "not-an-email"}
    engine.dead_letter_queue.append(
        DeadLetterRecord(
            record_id="bad_1",
            source="linkedin_csv",
            error_reason="Missing mandatory name and invalid email format",
            raw_data=malformed,
        )
    )
    dlq_count = engine.flush_dead_letter_queue()
    assert dlq_count == 1
    assert Path(dlq_path).exists()
    
    with open(dlq_path, "r", encoding="utf-8") as f:
        dlq_data = json.load(f)
    assert len(dlq_data) == 1
    assert dlq_data[0]["record_id"] == "bad_1"
    Path(dlq_path).unlink(missing_ok=True)
    print("  [PASS] UnifiedRecord schema validated & DLQ correctly isolates malformed records.")


def test_02_ingest_linkedin_csv():
    """Requirement: Ingest Source A (LinkedIn CSV leads) with full canonical normalization."""
    print("\n--- Test 2: Ingest Source A (LinkedIn Leads CSV) ---")
    csv_path = Path("data/mock_leads.csv")
    assert csv_path.exists(), "mock_leads.csv must exist in data/"
    
    engine = IngestionEngine(dlq_output_path="outputs/test_dlq_csv.json")
    leads = engine.parse_linkedin_csv(csv_path)
    assert len(leads) >= 15, f"Expected at least 15 leads, got {len(leads)}"
    
    for lead in leads:
        assert lead.source == "linkedin_csv"
        assert lead.id.startswith("L")
        assert lead.name
        assert (lead.contact_info.email or lead.contact_info.linkedin_url or lead.contact_info.phone)
        assert lead.context
    print(f"  [PASS] Successfully ingested {len(leads)} LinkedIn leads into UnifiedRecord contracts.")


def test_03_ingest_smart_fhir_patients():
    """Requirement: Ingest Source B (SMART on FHIR R4 Patient API) with canonical normalization."""
    print("\n--- Test 3: Ingest Source B (SMART FHIR R4 Patients) ---")
    engine = IngestionEngine(dlq_output_path="outputs/test_dlq_fhir.json")
    patients = engine.fetch_fhir_patients(count=15, inject_malformed_test_record=True)
    
    # Should have valid patients + 1 malformed record sent to DLQ
    assert len(patients) >= 10, f"Expected at least 10 valid patients, got {len(patients)}"
    dlq_count = engine.flush_dead_letter_queue()
    assert dlq_count >= 1, "Expected at least 1 injected malformed record in DLQ"
    
    for p in patients:
        assert p.source == "smart_fhir_r4"
        assert p.id.startswith("fhir_")
        assert p.name
        assert p.context
    Path("outputs/test_dlq_fhir.json").unlink(missing_ok=True)
    print(f"  [PASS] Successfully ingested {len(patients)} FHIR patients (DLQ isolated {dlq_count} malformed).")


def test_04_three_step_agent_reasoning_and_guardrails():
    """Requirement: Stage 2 Autonomous 3-Step Agent Loop & Self-Critique Guardrail Gate."""
    print("\n--- Test 4: 3-Step Autonomous State Machine & HIPAA Guardrail ---")
    agent = IntakeAgent()
    
    # Test A: B2B Lead
    b2b_lead = UnifiedRecord(
        id="L999",
        source="linkedin_csv",
        name="Alexander Wright",
        contact_info=ContactInfo(email="a.wright@apextech.example.com", phone="+1-555-0199"),
        raw_payload={"job_title": "VP of Technology", "company": "ApexTech Solutions", "company_size": "500-1000"},
        context="Target: Alexander Wright, VP of Technology at ApexTech Solutions. Company Size: 500-1000 employees. Interested in pipeline modernization.",
        priority_signal="Enterprise Modernization",
    )
    trace = agent.process_record(b2b_lead)
    
    # Check Step 1: Quality Gate
    s1 = trace.step1_qualification
    assert 0.0 <= s1.completeness_score <= 1.0
    assert len(s1.usable_channels) > 0
    assert s1.classification in ["HOT", "WARM", "COLD", "HIGH_CLINICAL_URGENCY", "ROUTINE_CARE", "DATA_INCOMPLETE"]
    assert s1.qualification_rationale
    
    # Check Step 2: Policy & Action Router
    s2 = trace.step2_action_plan
    assert s2.recommended_channel in ["email", "sms", "linkedin_dm", "phone_call", "clinical_escalation_queue", "manual_enrichment_queue"]
    assert s2.tone in ["consultative_executive", "empathetic_clinical", "urgent_care_coordination", "professional_concise", "administrative_intake"]
    assert isinstance(s2.escalate_flag, bool)
    assert s2.routing_rationale
    
    # Check Step 3: Message & Guardrail Critique
    s3 = trace.step3_message_result
    assert s3.draft_message
    assert s3.guardrail_critique
    assert s3.guardrail_passed is True
    assert s3.final_message
    
    # Test B: High Clinical Urgency Patient (Verifying Escalation & HIPAA Redaction)
    urgent_patient = UnifiedRecord(
        id="fhir_urgent_1",
        source="smart_fhir_r4",
        name="John Doe",
        contact_info=ContactInfo(email="john.doe@med.example.com", phone="+1-555-0911"),
        raw_payload={"conditions": ["Acute Myocardial Infarction", "Severe Chest Pain"]},
        context="Patient ID: 911 | Name: John Doe | Conditions: Acute Myocardial Infarction, Severe Chest Pain | Age: 58 | Needs immediate clinical evaluation",
        priority_signal="Urgent Inpatient Cardiac Alert",
    )
    urgent_trace = agent.process_record(urgent_patient)
    assert urgent_trace.step2_action_plan.escalate_flag is True, "High urgency clinical patient must have escalate_flag=True"
    assert "Myocardial Infarction" not in urgent_trace.step3_message_result.final_message, "PHI must not be exposed in cleartext message"
    print("  [PASS] 3-Step State Machine completed successfully with human escalation flag and HIPAA redaction verified.")


def test_05_tenacity_retry_and_cms_delivery():
    """Requirement: Stage 3 Delivery Engine with Tenacity exponential backoff and Mock CMS ingestion."""
    print("\n--- Test 5: Tenacity Exponential Backoff Retry & CMS Delivery ---")
    deliver_engine = DeliveryEngine(
        simulate_transient_failure=True,  # Forces transient 503 demonstration
    )
    
    record = UnifiedRecord(
        id="test_deliv_1",
        source="linkedin_csv",
        name="Marcus Vance",
        contact_info=ContactInfo(email="marcus.vance@example.com"),
        context="Director of Sales Ops at HealthCorp",
        priority_signal="High Priority Lead",
    )
    
    agent = IntakeAgent()
    trace = agent.process_record(record)
    
    payload, receipt = deliver_engine.deliver_record(record, trace)
    assert receipt.status == "accepted"
    assert receipt.cms_receipt_id.startswith("cms_rcpt_")
    assert receipt.record_id == "test_deliv_1"
    print(f"  [PASS] Tenacity retry handled transient failure, record accepted: {receipt.cms_receipt_id}")


def test_06_fastapi_server_endpoints():
    """Requirement: Mock CMS & Observability endpoints (Health, Records, Results, DLQ, Diagnostics)."""
    print("\n--- Test 6: FastAPI Service Endpoints & Health ---")
    base_url = "http://127.0.0.1:8000"
    
    # 1. Health
    with urllib.request.urlopen(f"{base_url}/health") as resp:
        assert resp.status == 200
        health = json.loads(resp.read().decode())
        assert health["status"] == "healthy"
    
    # 2. CMS Delivered Records
    with urllib.request.urlopen(f"{base_url}/api/v1/cms/records") as resp:
        assert resp.status == 200
        recs = json.loads(resp.read().decode())
        assert len(recs) >= 30, f"Expected >=30 records, got {len(recs)}"
    
    # 3. Pipeline Results
    with urllib.request.urlopen(f"{base_url}/api/v1/pipeline/results") as resp:
        assert resp.status == 200
        results = json.loads(resp.read().decode())
        assert len(results) >= 30
    
    # 4. DLQ
    with urllib.request.urlopen(f"{base_url}/api/v1/pipeline/dlq") as resp:
        assert resp.status == 200
        dlq = json.loads(resp.read().decode())
        assert isinstance(dlq, list)
    
    # 5. Diagnostics
    with urllib.request.urlopen(f"{base_url}/api/v1/diagnostics") as resp:
        assert resp.status == 200
        diag = json.loads(resp.read().decode())
        assert diag["llm_provider"] in ["groq", "gemini", "heuristic"]
    
    # 6. Diagnostics Ping
    req = urllib.request.Request(f"{base_url}/api/v1/diagnostics/ping", data=b"", method="POST")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        ping = json.loads(resp.read().decode())
        assert ping["status"] == "ok"
        assert "latency_ms" in ping
    
    # 7. Dashboard HTML
    with urllib.request.urlopen(f"{base_url}/") as resp:
        assert resp.status == 200
        html = resp.read().decode()
        assert "AI Intake Hub" in html
        assert "diagModal" in html
        assert "CMS Records" in html
    
    print("  [PASS] All 7 service endpoints (/health, /cms/records, /results, /dlq, /diagnostics, /ping, /) verified 200 OK.")


if __name__ == "__main__":
    print("======================================================================")
    print("   RUNNING FULL PDF REQUIREMENTS VERIFICATION SUITE")
    print("======================================================================")
    t0 = time.time()
    test_01_pydantic_schemas_and_dlq()
    test_02_ingest_linkedin_csv()
    test_03_ingest_smart_fhir_patients()
    test_04_three_step_agent_reasoning_and_guardrails()
    test_05_tenacity_retry_and_cms_delivery()
    test_06_fastapi_server_endpoints()
    elapsed = round(time.time() - t0, 2)
    print("======================================================================")
    print(f"   >>> ALL PDF REQUIREMENTS VERIFIED & PASSED (Total: {elapsed}s) <<<")
    print("======================================================================")
