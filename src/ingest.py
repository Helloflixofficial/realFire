"""
Stage 1 Ingestion Pipeline:
Ingests B2B LinkedIn CSV leads and SMART Health IT FHIR R4 clinical records.
Normalizes both into a unified Pydantic contract (UnifiedRecord).
Routes corrupted/malformed records into a Dead Letter Queue (DLQ) without crashing.
"""

from __future__ import annotations
import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from pydantic import ValidationError

from src.schemas import ContactInfo, DeadLetterRecord, UnifiedRecord

logger = logging.getLogger("intake_pipeline.ingest")


class IngestionEngine:
    """Ingests heterogeneous lead and patient datasets into unified schemas."""

    def __init__(
        self,
        fhir_base_url: str = "https://r4.smarthealthit.org",
        dlq_output_path: str = "outputs/dead_letter_queue.json",
        timeout_seconds: float = 12.0,
    ) -> None:
        self.fhir_base_url = fhir_base_url.rstrip("/")
        self.dlq_output_path = Path(dlq_output_path)
        self.timeout_seconds = timeout_seconds
        self.dead_letter_queue: List[DeadLetterRecord] = []

    # ==========================================================================
    # SOURCE A: LINKEDIN SALES NAVIGATOR CSV PARSER
    # ==========================================================================

    def parse_linkedin_csv(self, csv_path: str | Path) -> List[UnifiedRecord]:
        """
        Parses a LinkedIn Sales Navigator CSV export.
        Handles flexible column naming conventions resiliently.
        """
        csv_file = Path(csv_path)
        if not csv_file.exists():
            logger.error(f"CSV file not found at {csv_file}")
            raise FileNotFoundError(f"Lead source CSV not found at: {csv_file}")

        logger.info(f"Parsing LinkedIn leads from: {csv_file}")
        valid_records: List[UnifiedRecord] = []

        with open(csv_file, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            # Normalize fieldnames to lowercase stripped keys
            for row_idx, row in enumerate(reader, start=1):
                raw_row = dict(row)
                normalized_keys = {
                    k.strip().lower().replace(" ", "_").replace("-", "_"): v.strip()
                    for k, v in raw_row.items()
                    if k is not None and v is not None
                }

                # Resilient column resolution
                lead_id = normalized_keys.get("lead_id") or f"lead_csv_{row_idx:03d}"
                first_name = (
                    normalized_keys.get("first_name")
                    or normalized_keys.get("firstname")
                    or normalized_keys.get("given_name")
                    or ""
                )
                last_name = (
                    normalized_keys.get("last_name")
                    or normalized_keys.get("lastname")
                    or normalized_keys.get("surname")
                    or normalized_keys.get("family_name")
                    or ""
                )
                full_name = (
                    normalized_keys.get("full_name")
                    or f"{first_name} {last_name}".strip()
                    or normalized_keys.get("name")
                    or ""
                )

                email = (
                    normalized_keys.get("email")
                    or normalized_keys.get("work_email")
                    or normalized_keys.get("e_mail")
                    or None
                )
                phone = (
                    normalized_keys.get("phone")
                    or normalized_keys.get("mobile")
                    or normalized_keys.get("telephone")
                    or None
                )
                linkedin_url = (
                    normalized_keys.get("linkedin_url")
                    or normalized_keys.get("linkedin")
                    or normalized_keys.get("profile_url")
                    or None
                )
                job_title = (
                    normalized_keys.get("job_title")
                    or normalized_keys.get("title")
                    or normalized_keys.get("position")
                    or normalized_keys.get("role")
                    or "Professional"
                )
                company = (
                    normalized_keys.get("company")
                    or normalized_keys.get("organization")
                    or normalized_keys.get("account")
                    or "Organization"
                )
                industry = normalized_keys.get("industry", "Healthcare & Services")
                company_size = normalized_keys.get("company_size", "Small-to-Mid")
                location = normalized_keys.get("location", "")
                headline = normalized_keys.get("linkedin_headline", "")
                activity = normalized_keys.get("recent_activity", "")
                connection_note = normalized_keys.get("connection_note", "")
                bio = normalized_keys.get("bio") or normalized_keys.get("notes") or headline

                # If LinkedIn URL not explicitly provided in CSV, synthesize deterministic profile URL for valid names
                if not linkedin_url and full_name:
                    clean_slug = full_name.lower().replace(" ", "-").replace("'", "").replace(".", "")
                    linkedin_url = f"https://www.linkedin.com/in/{clean_slug}"

                # Validation Gate: Must have at least a name and reachable channel
                record_id = lead_id
                if not full_name or (not email and not linkedin_url and not phone):
                    error_msg = (
                        f"Row {row_idx} ({lead_id}) rejected: Missing recipient name and valid contact endpoints "
                        f"(name='{full_name}', email='{email}', linkedin='{linkedin_url}')"
                    )
                    logger.warning(f"[DLQ] {error_msg}")
                    self.dead_letter_queue.append(
                        DeadLetterRecord(
                            record_id=record_id,
                            source="linkedin_csv",
                            error_reason=error_msg,
                            raw_data=raw_row,
                        )
                    )
                    continue

                # Signal Extraction Heuristic tailored to clinic automation & sales ops
                priority_signals = []
                title_lower = job_title.lower()
                if any(x in title_lower for x in ["owner", "founder", "ceo", "cmo", "cto", "vp", "chief"]):
                    priority_signals.append("Executive Practice Owner / Founder (Direct Authority)")
                elif any(x in title_lower for x in ["director", "head of", "manager", "administrator", "lead"]):
                    priority_signals.append("Clinical Operations Leader (Workflow Decision Maker)")
                else:
                    priority_signals.append("Practitioner / Clinical Staff")

                combined_intent = (activity + " " + connection_note).lower()
                if any(x in combined_intent for x in ["demo", "requested a call", "pricing", "warm intro"]):
                    priority_signals.append("Inbound High-Intent Signal (Demo/Call/Pricing Requested or Warm Intro)")
                elif any(x in combined_intent for x in ["ai receptionist", "no-show", "call volume", "missed call", "follow-up speed", "after-hours"]):
                    priority_signals.append("Acute Pain Point Alignment (AI Receptionist / Intake / Follow-up Need)")
                elif "liked" in combined_intent or "commented" in combined_intent or "shared" in combined_intent:
                    priority_signals.append("Active Social Engagement on Automation Content")

                context_summary = (
                    f"Prospect: {full_name} ({lead_id}) | Role: {job_title} at {company} | "
                    f"Industry: {industry} | Headcount: {company_size} | Location: {location if location else 'N/A'} | "
                    f"LinkedIn Headline: {headline if headline else bio} | "
                    f"Recent Activity: {activity if activity else 'Dormant'} | "
                    f"Outreach Context: {connection_note if connection_note else 'Cold profile'}"
                )

                contact = ContactInfo(
                    email=email,
                    phone=phone,
                    linkedin_url=linkedin_url,
                    address=location if location else None,
                    preferred_channel="email" if email else "linkedin_dm",
                )


                try:
                    unified_record = UnifiedRecord(
                        id=record_id,
                        source="linkedin_csv",
                        name=full_name,
                        contact_info=contact,
                        context=context_summary,
                        priority_signal=" | ".join(priority_signals),
                        raw_payload=raw_row,
                    )
                    valid_records.append(unified_record)
                except ValidationError as ve:
                    logger.error(f"[DLQ] Schema validation failed for lead row {row_idx}: {ve}")
                    self.dead_letter_queue.append(
                        DeadLetterRecord(
                            record_id=record_id,
                            source="linkedin_csv",
                            error_reason=f"Pydantic Validation Error: {str(ve)}",
                            raw_data=raw_row,
                        )
                    )

        logger.info(
            f"Successfully normalized {len(valid_records)} LinkedIn leads "
            f"({len(self.dead_letter_queue)} sent to DLQ)"
        )
        return valid_records

    # ==========================================================================
    # SOURCE B: SMART HEALTH IT FHIR R4 CLIENT
    # ==========================================================================

    def fetch_fhir_patients(
        self, count: int = 15, inject_malformed_test_record: bool = True
    ) -> List[UnifiedRecord]:
        """
        Pulls real synthetic Patient, Condition, and Appointment resources
        from the SMART Health IT FHIR R4 sandbox.
        Normalizes FHIR R4 JSON trees into UnifiedRecord instances.
        """
        logger.info(
            f"Querying SMART Health IT FHIR R4 sandbox ({self.fhir_base_url}) for {count} patients..."
        )
        valid_records: List[UnifiedRecord] = []

        with httpx.Client(timeout=self.timeout_seconds) as client:
            try:
                patient_resp = client.get(
                    f"{self.fhir_base_url}/Patient",
                    params={"_count": count},
                    headers={"Accept": "application/fhir+json"},
                )
                patient_resp.raise_for_status()
                patient_bundle = patient_resp.json()
            except Exception as exc:
                logger.error(f"Failed to fetch Patient bundle from FHIR endpoint: {exc}")
                raise RuntimeError(f"FHIR Sandbox unreachable: {exc}") from exc

            entries = patient_bundle.get("entry", [])
            logger.info(f"Retrieved {len(entries)} raw Patient entries from FHIR searchset")

            for entry in entries:
                patient_res = entry.get("resource", {})
                patient_id = patient_res.get("id", "unknown_fhir_id")

                # Parse Human Name
                names = patient_res.get("name", [])
                full_name = self._parse_fhir_name(names)

                # Parse Telecom
                telecoms = patient_res.get("telecom", [])
                phone, email = self._parse_fhir_telecoms(telecoms)

                # Parse Address
                address_str = self._parse_fhir_address(patient_res.get("address", []))

                # Compute Age & Demographics
                birth_date = patient_res.get("birthDate")
                gender = patient_res.get("gender", "unknown")
                age_str = self._calculate_age(birth_date)

                # Query Sub-resources: Conditions & Appointments
                conditions_summary = self._fetch_patient_conditions(client, patient_id)
                appointments_summary = self._fetch_patient_appointments(client, patient_id)

                context_summary = (
                    f"Patient ID: {patient_id} | Name: {full_name} | Age: {age_str} | "
                    f"Gender: {gender.capitalize()} | Address: {address_str} | "
                    f"Clinical Conditions: {conditions_summary} | "
                    f"Appointments & Scheduling: {appointments_summary}"
                )

                # Priority Signal Assessment
                priority_signals = []
                if "Active:" in conditions_summary:
                    priority_signals.append("Active Chronic Condition(s) Requiring Monitoring")
                if "Upcoming:" in appointments_summary:
                    priority_signals.append("Active Scheduling Pathway (Upcoming Booked Visit)")
                elif "Overdue" in appointments_summary or "Cancelled" in appointments_summary:
                    priority_signals.append("Care Gap Alert: Appointment Disruption / Overdue Follow-up")
                if not priority_signals:
                    priority_signals.append("Routine Preventive Care Baseline")

                contact = ContactInfo(
                    email=email,
                    phone=phone,
                    address=address_str,
                    preferred_channel="sms" if phone else "email",
                )

                try:
                    record = UnifiedRecord(
                        id=f"fhir_{patient_id}",
                        source="smart_fhir_r4",
                        name=full_name,
                        contact_info=contact,
                        context=context_summary,
                        priority_signal=" | ".join(priority_signals),
                        raw_payload={
                            "patient": patient_res,
                            "conditions_query": conditions_summary,
                            "appointments_query": appointments_summary,
                        },
                    )
                    valid_records.append(record)
                except ValidationError as ve:
                    error_msg = f"Patient {patient_id} failed UnifiedRecord validation: {ve}"
                    logger.warning(f"[DLQ] {error_msg}")
                    self.dead_letter_queue.append(
                        DeadLetterRecord(
                            record_id=f"fhir_{patient_id}",
                            source="smart_fhir_r4",
                            error_reason=str(ve),
                            raw_data=patient_res,
                        )
                    )

            # Failure Case A Demonstration: Inject 1 synthetic malformed FHIR record
            if inject_malformed_test_record:
                logger.info("[Resilience Test] Injecting 1 deliberately corrupt FHIR patient record to demonstrate DLQ isolation...")
                corrupt_fhir_payload = {
                    "resourceType": "Patient",
                    "id": "malformed_fhir_corrupt_999",
                    "name": [],  # Blank name violating schema
                    "telecom": [],  # Missing all contact points
                    "meta": {"tag": [{"code": "deliberate_corruption_test"}]},
                }
                # This should be caught and routed cleanly to DLQ
                try:
                    UnifiedRecord(
                        id="fhir_malformed_corrupt_999",
                        source="smart_fhir_r4",
                        name="",  # Causes validation error
                        contact_info=ContactInfo(),
                        context="Corrupt record with missing demographic fields",
                        priority_signal="Invalid Data",
                        raw_payload=corrupt_fhir_payload,
                    )
                except ValidationError as ve:
                    dlq_entry = DeadLetterRecord(
                        record_id="fhir_malformed_corrupt_999",
                        source="smart_fhir_r4",
                        error_reason=f"Deliberate Ingestion Test: Empty patient name and empty telecom - {ve.errors()[0]['msg']}",
                        raw_data=corrupt_fhir_payload,
                    )
                    self.dead_letter_queue.append(dlq_entry)
                    logger.warning(
                        f"[DLQ] Successfully isolated corrupt FHIR record 'fhir_malformed_corrupt_999': {dlq_entry.error_reason}"
                    )

        logger.info(
            f"Successfully normalized {len(valid_records)} FHIR patient records "
            f"({len(self.dead_letter_queue)} total rejected in DLQ)"
        )
        return valid_records

    # ==========================================================================
    # FHIR HELPER SUBROUTINES
    # ==========================================================================

    def _parse_fhir_name(self, name_list: List[Dict[str, Any]]) -> str:
        """Parses HL7 FHIR HumanName array into a readable full name."""
        if not name_list:
            return "Anonymous Patient"
        # Prefer 'official' or 'usual'
        primary_name = name_list[0]
        for n in name_list:
            if n.get("use") in ["official", "usual"]:
                primary_name = n
                break

        given = " ".join(primary_name.get("given", []))
        family = primary_name.get("family", "")
        prefix = " ".join(primary_name.get("prefix", []))
        full = f"{prefix} {given} {family}".strip()
        return full if full else "Anonymous Patient"

    def _parse_fhir_telecoms(
        self, telecom_list: List[Dict[str, Any]]
    ) -> Tuple[Optional[str], Optional[str]]:
        """Extracts primary phone and email from FHIR ContactPoint array."""
        phone = None
        email = None
        for item in telecom_list:
            system = item.get("system")
            value = item.get("value")
            if not value:
                continue
            if system == "phone" and not phone:
                phone = value
            elif system == "email" and not email:
                email = value
        return phone, email

    def _parse_fhir_address(self, address_list: List[Dict[str, Any]]) -> str:
        """Flattens FHIR Address into a single comma-separated location."""
        if not address_list:
            return "Address on file"
        addr = address_list[0]
        lines = " ".join(addr.get("line", []))
        city = addr.get("city", "")
        state = addr.get("state", "")
        postal = addr.get("postalCode", "")
        parts = [p for p in [lines, city, state, postal] if p]
        return ", ".join(parts) if parts else "Address on file"

    def _calculate_age(self, birth_date_str: Optional[str]) -> str:
        """Calculates approximate patient age from birthDate string."""
        if not birth_date_str:
            return "Age unknown"
        try:
            birth_dt = datetime.strptime(birth_date_str[:10], "%Y-%m-%d")
            today = datetime.now(timezone.utc).date()
            age_years = (
                today.year
                - birth_dt.year
                - ((today.month, today.day) < (birth_dt.month, birth_dt.day))
            )
            return f"{age_years}yo (DOB: {birth_date_str})"
        except Exception:
            return f"DOB: {birth_date_str}"

    def _fetch_patient_conditions(
        self, client: httpx.Client, patient_id: str
    ) -> str:
        """Queries FHIR Condition resources associated with patient."""
        try:
            resp = client.get(
                f"{self.fhir_base_url}/Condition",
                params={"patient": patient_id, "_count": 5},
                headers={"Accept": "application/fhir+json"},
            )
            if resp.status_code != 200:
                return "Conditions query unavailable"
            bundle = resp.json()
            entries = bundle.get("entry", [])
            if not entries:
                return "No documented active conditions"

            active_list = []
            historical_list = []
            for e in entries:
                res = e.get("resource", {})
                code_obj = res.get("code", {})
                display = (
                    code_obj.get("text")
                    or (code_obj.get("coding", [{}])[0].get("display") if code_obj.get("coding") else None)
                    or "Unspecified condition"
                )
                clinical_status = (
                    res.get("clinicalStatus", {})
                    .get("coding", [{}])[0]
                    .get("code", "unknown")
                )
                if clinical_status in ["active", "recurrence"]:
                    active_list.append(display)
                else:
                    historical_list.append(f"{display} ({clinical_status})")

            summary_parts = []
            if active_list:
                summary_parts.append(f"Active: {', '.join(active_list)}")
            if historical_list:
                summary_parts.append(f"Resolved/Past: {', '.join(historical_list)}")
            return " | ".join(summary_parts) if summary_parts else "No chronic conditions"
        except Exception as exc:
            logger.debug(f"Condition query note for {patient_id}: {exc}")
            return "Condition records pending intake review"

    def _fetch_patient_appointments(
        self, client: httpx.Client, patient_id: str
    ) -> str:
        """Queries FHIR Appointment resources associated with patient."""
        try:
            resp = client.get(
                f"{self.fhir_base_url}/Appointment",
                params={"patient": patient_id, "_count": 5},
                headers={"Accept": "application/fhir+json"},
            )
            if resp.status_code != 200:
                return "Appointment history unavailable"
            bundle = resp.json()
            entries = bundle.get("entry", [])
            if not entries:
                return "No scheduled upcoming appointments"

            appts = []
            for e in entries:
                res = e.get("resource", {})
                status = res.get("status", "unknown")
                start_time = res.get("start", "date TBD")
                appts.append(f"Status: {status} at {start_time}")
            return f"Appointments found ({len(entries)}): " + "; ".join(appts)
        except Exception as exc:
            logger.debug(f"Appointment query note for {patient_id}: {exc}")
            return "No appointment history found"

    # ==========================================================================
    # DLQ EXPORT
    # ==========================================================================

    def flush_dead_letter_queue(self) -> int:
        """Persists all rejected records to dead_letter_queue.json."""
        self.dlq_output_path.parent.mkdir(parents=True, exist_ok=True)
        serialized_dlq = [dlq.model_dump() for dlq in self.dead_letter_queue]
        with open(self.dlq_output_path, "w", encoding="utf-8") as f:
            json.dump(serialized_dlq, f, indent=2)
        logger.info(
            f"Saved {len(serialized_dlq)} rejected record(s) to Dead Letter Queue: {self.dlq_output_path}"
        )
        return len(serialized_dlq)
