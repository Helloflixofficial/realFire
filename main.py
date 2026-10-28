"""
End-to-End Orchestrator for AI Agent Lead & Patient Intake Pipeline.
Runs Stage 1 (Ingest & Normalize) -> Stage 2 (3-Step AI Agent) -> Stage 3 (CMS Delivery).
Outputs full traces to outputs/sample_end_to_end_results.json and logs to outputs/pipeline_execution.log.
"""

from __future__ import annotations
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.agent import IntakeAgent
from src.deliver import DeliveryEngine
from src.ingest import IngestionEngine
from src.mock_cms import clear_cms_store
from src.schemas import UnifiedRecord

# Load environment configuration
load_dotenv()

# Ensure UTF-8 output encoding on Windows terminals to avoid charmap encoding errors
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Initialize Rich console with safe encoding
console = Console(highlight=False)

# Configure logging
LOG_DIR = Path("outputs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "pipeline_execution.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("intake_pipeline.main")


def print_banner() -> None:
    """Displays terminal header."""
    banner_text = (
        "[bold cyan]AI Agent for Automated Lead & Patient Intake, Enrichment, and Outreach[/bold cyan]\n"
        "[dim]3-Stage Pipeline: Ingest/Normalize -> 3-Step Agent Loop -> Resilient CMS Delivery[/dim]"
    )
    console.print(Panel(banner_text, border_style="cyan", expand=False))



def main() -> None:
    print_banner()
    start_time = time.time()

    # Clear previous CMS store for clean evaluation run
    clear_cms_store()

    # Configuration
    fhir_count = int(os.getenv("FHIR_PATIENT_COUNT", "15"))
    csv_path = Path("data/mock_leads.csv")
    simulate_transient_failure = os.getenv("SIMULATE_TRANSIENT_FAILURE", "true").lower() == "true"

    console.print("\n[bold yellow]>>> STAGE 1: INGESTION & UNIFICATION GATES[/bold yellow]")
    ingest_engine = IngestionEngine(dlq_output_path="outputs/dead_letter_queue.json")

    # Ingest Source A: LinkedIn Leads CSV
    leads = ingest_engine.parse_linkedin_csv(csv_path)

    # Ingest Source B: SMART Health IT FHIR R4
    patients = ingest_engine.fetch_fhir_patients(
        count=fhir_count, inject_malformed_test_record=True
    )

    # Persist DLQ
    dlq_count = ingest_engine.flush_dead_letter_queue()

    total_valid_records: List[UnifiedRecord] = leads + patients
    console.print(
        f"[green][OK] Stage 1 Complete:[/green] Ingested [bold]{len(leads)}[/bold] B2B Leads, "
        f"[bold]{len(patients)}[/bold] FHIR Patients. "
        f"[bold red]{dlq_count} records isolated into Dead Letter Queue[/bold red]."
    )

    console.print("\n[bold yellow]>>> STAGE 2 & 3: MULTI-STEP AGENT REASONING & CMS DELIVERY[/bold yellow]")
    agent = IntakeAgent()
    deliver_engine = DeliveryEngine(simulate_transient_failure=simulate_transient_failure)

    end_to_end_results: List[Dict[str, Any]] = []

    # Display processing table
    results_table = Table(title="Live Agent Pipeline Execution Trace", show_header=True, header_style="bold magenta")
    results_table.add_column("ID", style="dim", width=14)
    results_table.add_column("Recipient", width=18)
    results_table.add_column("Domain", width=12)
    results_table.add_column("Step 1 Triage", width=22)
    results_table.add_column("Step 2 Routing", width=24)
    results_table.add_column("Step 3 Guardrail", width=16)
    results_table.add_column("CMS Status", width=12)

    with console.status("[bold green]Executing agent reasoning and delivery loop...") as status:
        for idx, record in enumerate(total_valid_records, start=1):
            status.update(f"[bold cyan]Processing [{idx}/{len(total_valid_records)}]: {record.name} ({record.id})...")

            # Stage 2: 3-step agent reasoning loop
            trace = agent.process_record(record)

            # Stage 3: Resilient delivery to mock CMS
            payload, receipt = deliver_engine.deliver_record(record, trace)

            # Build comprehensive end-to-end report record
            full_record_result = {
                "record_id": record.id,
                "source": record.source,
                "recipient_name": record.name,
                "input_context": record.context,
                "priority_signal": record.priority_signal,
                "agent_reasoning": {
                    "step1_qualification": trace.step1_qualification.model_dump(),
                    "step2_action_plan": trace.step2_action_plan.model_dump(),
                    "step3_message_result": trace.step3_message_result.model_dump(),
                    "reasoning_summary": trace.reasoning_summary,
                },
                "final_message": trace.step3_message_result.final_message,
                "cms_receipt": receipt.model_dump(),
            }
            end_to_end_results.append(full_record_result)

            # Add to console display table
            domain_label = "B2B Lead" if record.source == "linkedin_csv" else "Patient"
            guardrail_label = "[green]PASSED[/green]" if trace.step3_message_result.guardrail_passed else "[yellow]REFINED[/yellow]"
            results_table.add_row(
                record.id,
                record.name[:18],
                domain_label,
                trace.step1_qualification.classification,
                f"{trace.step2_action_plan.recommended_channel} (esc={trace.step2_action_plan.escalate_flag})",
                guardrail_label,
                f"[bold green]{receipt.status.upper()}[/bold green]",
            )

    console.print(results_table)

    # Save outputs
    output_sample_path = Path("outputs/sample_end_to_end_results.json")
    with open(output_sample_path, "w", encoding="utf-8") as f:
        json.dump(end_to_end_results, f, indent=2)

    elapsed = time.time() - start_time

    # Final summary statistics
    summary_panel = (
        f"[bold green]Pipeline Execution Completed in {elapsed:.2f}s[/bold green]\n\n"
        f"- Total Sources Ingested: [bold]{len(total_valid_records) + dlq_count}[/bold]\n"
        f"- Valid Records Processed: [bold]{len(total_valid_records)}[/bold]\n"
        f"- Dead Letter Queue (Isolated Malformed Records): [bold red]{dlq_count}[/bold red] ([underline]outputs/dead_letter_queue.json[/underline])\n"
        f"- Mock CMS Stored Deliveries: [bold]{len(end_to_end_results)}[/bold] ([underline]outputs/cms_delivered_records.json[/underline])\n"
        f"- Full E2E Traces Saved: [bold]{len(end_to_end_results)}[/bold] ([underline]outputs/sample_end_to_end_results.json[/underline])\n"
        f"- Complete Execution Log: [underline]outputs/pipeline_execution.log[/underline]\n\n"
        f"[bold cyan]>>> WEB APPLICATION & CMS SERVER[/bold cyan]\n"
        f"- Interactive Web Dashboard: [bold underline]http://127.0.0.1:8000[/bold underline]\n"
        f"- Swagger REST API Explorer: [bold underline]http://127.0.0.1:8000/docs[/bold underline]\n"
        f"  (Run [bold yellow]python server.py[/bold yellow] or pass [bold yellow]--serve[/bold yellow] to start the web server)"
    )
    console.print(Panel(summary_panel, title="Pipeline Execution Summary", border_style="green"))

    if "--serve" in sys.argv:
        import uvicorn
        console.print("\n[bold cyan]Starting Web Dashboard & Mock CMS Server on http://127.0.0.1:8000...[/bold cyan]")
        uvicorn.run("src.mock_cms:app", host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    main()

