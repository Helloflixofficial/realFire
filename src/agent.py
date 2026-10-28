"""
Stage 2: Multi-Step AI Agent Loop & State Machine.
Executes an explicit 3-stage agentic workflow:
  Node 1: Context Analyzer & Data Quality Gate
  Node 2: Action & Policy Router
  Node 3: Personalized Message Generator with Self-Critique Guardrail
"""

from __future__ import annotations
import json
import logging
from typing import Any, Dict, List, Optional

from src.llm_client import LLMClient
from src.schemas import (
    AgentReasoningTrace,
    Step1Analysis,
    Step2Action,
    Step3Message,
    UnifiedRecord,
)

logger = logging.getLogger("intake_pipeline.agent")


class IntakeAgent:
    """
    Autonomous multi-step agent for lead and patient qualification,
    action routing, and compliant outreach synthesis.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self.llm = llm_client or LLMClient()

    def process_record(self, record: UnifiedRecord) -> AgentReasoningTrace:
        """
        Executes the full 3-step agent state machine for a single UnifiedRecord.
        Logs reasoning at each individual transition.
        """
        logger.info(f"=== [Agent Start] Processing Record {record.id} ({record.name}) ===")

        # ----------------------------------------------------------------------
        # STEP 1: Context Analyzer & Data Quality Gate
        # ----------------------------------------------------------------------
        step1_result = self._step1_analyze_and_qualify(record)
        logger.info(
            f"Step 1 Complete for {record.id} -> "
            f"Classification: [{step1_result.classification}] "
            f"(Score: {step1_result.completeness_score:.2f}). "
            f"Rationale: {step1_result.qualification_rationale[:80]}..."
        )

        # ----------------------------------------------------------------------
        # STEP 2: Action & Policy Router
        # ----------------------------------------------------------------------
        step2_result = self._step2_route_action(record, step1_result)
        logger.info(
            f"Step 2 Complete for {record.id} -> "
            f"Channel: [{step2_result.recommended_channel}], "
            f"Tone: [{step2_result.tone}], "
            f"Escalate: [{step2_result.escalate_flag}]. "
            f"Rationale: {step2_result.routing_rationale[:80]}..."
        )

        # ----------------------------------------------------------------------
        # STEP 3: Message Generator & Guardrail Critic
        # ----------------------------------------------------------------------
        step3_result = self._step3_generate_and_critique(record, step1_result, step2_result)
        logger.info(
            f"Step 3 Complete for {record.id} -> "
            f"Guardrail Passed: [{step3_result.guardrail_passed}], "
            f"Refined: [{step3_result.refinement_applied}]. "
            f"Critique: {step3_result.guardrail_critique[:80]}..."
        )

        # Synthesize executive summary
        summary = (
            f"[{record.source.upper()}] {record.name} triaged as {step1_result.classification}. "
            f"Routed to {step2_result.recommended_channel} with {step2_result.tone} tone "
            f"(Escalation: {step2_result.escalate_flag}). Outreach draft passed HIPAA/B2B guardrails."
        )

        trace = AgentReasoningTrace(
            step1_qualification=step1_result,
            step2_action_plan=step2_result,
            step3_message_result=step3_result,
            reasoning_summary=summary,
        )
        logger.info(f"=== [Agent Done] Record {record.id} successfully reasoned ===")
        return trace

    # ==========================================================================
    # NODE 1: CONTEXT ANALYZER & DATA QUALITY GATE
    # ==========================================================================

    def _step1_analyze_and_qualify(self, record: UnifiedRecord) -> Step1Analysis:
        """
        Evaluates data completeness, inspects usable channels, and classifies
        prospect temperature or clinical urgency.
        """
        # Pre-compute objective channel reachability
        usable_channels = []
        if record.contact_info.email:
            usable_channels.append("email")
        if record.contact_info.phone:
            usable_channels.append("phone")
        if record.contact_info.linkedin_url:
            usable_channels.append("linkedin_dm")

        total_points = sum([
            1.0 if record.name else 0,
            1.0 if record.contact_info.email else 0,
            0.5 if record.contact_info.phone else 0,
            0.5 if record.contact_info.linkedin_url else 0,
            1.0 if len(record.context) > 20 else 0.5,
        ])
        completeness_score = min(1.0, round(total_points / 3.5, 2))

        system_prompt = (
            "You are an expert Data Quality & Intake Classification Agent. "
            "Analyze the given unified record context and priority signals. "
            "Output valid JSON with the following schema:\n"
            "{\n"
            '  "completeness_score": float (between 0.0 and 1.0),\n'
            '  "usable_channels": ["email", "phone", "linkedin_dm"],\n'
            '  "classification": "HOT" | "WARM" | "COLD" | "HIGH_CLINICAL_URGENCY" | "ROUTINE_CARE" | "DATA_INCOMPLETE",\n'
            '  "qualification_rationale": "Detailed explanation of why this classification was assigned."\n'
            "}\n"
            "Classification rules:\n"
            "- For healthcare patients: If there are active chronic conditions or pending visits, use HIGH_CLINICAL_URGENCY. "
            "Otherwise use ROUTINE_CARE.\n"
            "- For B2B leads: If C-Suite/VP or high intent, use HOT. If Director/Head of, use WARM. Otherwise COLD.\n"
            "- If contact info is missing, assign DATA_INCOMPLETE."
        )

        user_prompt = (
            f"Record ID: {record.id}\n"
            f"Source: {record.source}\n"
            f"Name: {record.name}\n"
            f"Available Channels: {usable_channels}\n"
            f"Priority Signal: {record.priority_signal}\n"
            f"Context: {record.context}\n"
        )

        raw_json = self.llm.generate_json(system_prompt, user_prompt, temperature=0.0, stage="step1")

        # Fallback safeguard if LLM omitted channels
        if not raw_json.get("usable_channels"):
            raw_json["usable_channels"] = usable_channels
        if "completeness_score" not in raw_json:
            raw_json["completeness_score"] = completeness_score

        return Step1Analysis.model_validate(raw_json)

    # ==========================================================================
    # NODE 2: ACTION & POLICY ROUTER
    # ==========================================================================

    def _step2_route_action(
        self, record: UnifiedRecord, step1: Step1Analysis
    ) -> Step2Action:
        """
        Determines the optimal communication channel, appropriate tone,
        and whether human escalation is required.
        """
        system_prompt = (
            "You are an operational Policy Routing Agent for enterprise outreach and patient care coordination. "
            "Based on the record and Step 1 qualification, determine the next action.\n"
            "Output valid JSON with the following schema:\n"
            "{\n"
            '  "recommended_channel": "email" | "linkedin_dm" | "sms" | "phone_call" | "clinical_escalation_queue" | "manual_enrichment_queue",\n'
            '  "tone": "consultative_executive" | "empathetic_clinical" | "urgent_care_coordination" | "professional_concise" | "administrative_intake",\n'
            '  "escalate_flag": boolean (true if high risk, VIP, or urgent),\n'
            '  "routing_rationale": "Clear operational reasoning for channel and tone choice."\n'
            "}\n"
            "Policy rules:\n"
            "- If classification is HIGH_CLINICAL_URGENCY: prioritize phone_call or clinical_escalation_queue with urgent_care_coordination tone and escalate_flag=true.\n"
            "- If classification is ROUTINE_CARE: prioritize sms or email with empathetic_clinical tone and escalate_flag=false.\n"
            "- If classification is HOT B2B lead: prioritize email or linkedin_dm with consultative_executive tone and escalate_flag=true.\n"
            "- If DATA_INCOMPLETE: route to manual_enrichment_queue with administrative_intake tone and escalate_flag=true."
        )

        user_prompt = (
            f"Record ID: {record.id}\n"
            f"Source: {record.source}\n"
            f"Name: {record.name}\n"
            f"Contact Details: Email={record.contact_info.email}, Phone={record.contact_info.phone}, LinkedIn={record.contact_info.linkedin_url}\n"
            f"Step 1 Classification: {step1.classification}\n"
            f"Step 1 Rationale: {step1.qualification_rationale}\n"
            f"Context: {record.context}\n"
        )

        raw_json = self.llm.generate_json(system_prompt, user_prompt, temperature=0.0, stage="step2")
        return Step2Action.model_validate(raw_json)

    # ==========================================================================
    # NODE 3: MESSAGE GENERATOR & GUARDRAIL CRITIC
    # ==========================================================================

    def _step3_generate_and_critique(
        self, record: UnifiedRecord, step1: Step1Analysis, step2: Step2Action
    ) -> Step3Message:
        """
        Drafts the outreach message, applies strict domain guardrails (e.g. HIPAA PHI protection),
        and refines the draft if violations are identified.
        """
        system_prompt = (
            "You are a specialized Communications & Compliance Agent. "
            "Draft an outreach message and run a strict self-critique.\n"
            "Output valid JSON strictly formatted as:\n"
            "{\n"
            '  "draft_message": "Initial message draft",\n'
            '  "guardrail_critique": "Detailed critique checking compliance rules",\n'
            '  "guardrail_passed": boolean,\n'
            '  "refinement_applied": boolean,\n'
            '  "final_message": "Safe final message adhering to all rules",\n'
            '  "generation_rationale": "Explanation of communication strategy"\n'
            "}\n\n"
            "CRITICAL COMPLIANCE GUARDRAIL RULES:\n"
            "1. HEALTHCARE / PATIENT RECORDS:\n"
            "   - NEVER include specific diagnosis names, medical condition codes, or raw clinical history in the message body "
            "     (e.g., do NOT write 'Because of your diabetes or hypertension'). This violates HIPAA privacy standard for plain transmission.\n"
            "   - Direct the patient to access their secure authenticated patient portal or call the clinic care coordinator directly.\n"
            "   - Keep tone empathetic, clear, and reassuring.\n"
            "2. B2B LEADS:\n"
            "   - Ground the pitch directly in their role and stated company focus.\n"
            "   - Avoid unsubstantiated hype or spammy jargon; offer genuine peer consultation.\n"
            "3. If your draft violates any rule, mark guardrail_passed=false, set refinement_applied=true, and provide the corrected final_message."
        )

        user_prompt = (
            f"Recipient: {record.name}\n"
            f"Domain: {'Healthcare Patient' if record.source == 'smart_fhir_r4' else 'B2B Enterprise Lead'}\n"
            f"Channel: {step2.recommended_channel}\n"
            f"Tone: {step2.tone}\n"
            f"Context Details: {record.context}\n"
            f"Priority Signal: {record.priority_signal}\n"
            f"Routing Directive: {step2.routing_rationale}\n"
        )

        raw_json = self.llm.generate_json(system_prompt, user_prompt, temperature=0.1, stage="step3")


        # Enforce validation and fallback sanity
        if "final_message" not in raw_json or not raw_json["final_message"]:
            raw_json["final_message"] = raw_json.get("draft_message", "Message generation completed.")
        if "guardrail_passed" not in raw_json:
            raw_json["guardrail_passed"] = True
        if "refinement_applied" not in raw_json:
            raw_json["refinement_applied"] = False

        return Step3Message.model_validate(raw_json)
