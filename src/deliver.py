"""
Stage 3: Outbound Delivery Client & Resilience Engine.
Transforms processed records into DownstreamCMSPayload and dispatches to Mock CMS.
Includes Tenacity-powered exponential backoff retry logic, deliberate transient 503
demonstration, and optional webhook.site dual-push.
"""

from __future__ import annotations
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import httpx
from dotenv import load_dotenv
from tenacity import (
    RetryCallState,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.mock_cms import app as mock_cms_app
from src.schemas import (
    ActionPlan,
    AgentReasoningTrace,
    CMSReceipt,
    DownstreamCMSPayload,
    UnifiedRecord,
)

load_dotenv()

logger = logging.getLogger("intake_pipeline.deliver")


class TransientCMSError(Exception):
    """Raised when downstream CMS encounters a temporary network or 503 error."""
    pass


class DeliveryEngine:
    """Dispatches validated payloads to downstream CMS with resilience guarantees."""

    def __init__(
        self,
        cms_url: Optional[str] = None,
        webhook_site_url: Optional[str] = None,
        simulate_transient_failure: bool = True,
        use_direct_asgi: bool = True,
    ) -> None:
        cms_host = os.getenv("MOCK_CMS_HOST", "127.0.0.1")
        cms_port = os.getenv("MOCK_CMS_PORT", "8000")
        self.cms_url = cms_url or f"http://{cms_host}:{cms_port}/api/v1/cms/records"
        self.webhook_site_url = webhook_site_url or os.getenv("WEBHOOK_SITE_URL", "").strip()
        self.simulate_transient_failure = simulate_transient_failure
        self.use_direct_asgi = use_direct_asgi

        # State tracking for deliberate failure case B
        self._simulated_failure_triggered: Dict[str, int] = {}
        self.delivery_count = 0

    def build_payload(
        self, record: UnifiedRecord, trace: AgentReasoningTrace
    ) -> DownstreamCMSPayload:
        """Constructs the strict DownstreamCMSPayload contract."""
        delivery_id = f"dlv_{uuid.uuid4().hex}"
        timestamp_utc = datetime.now(timezone.utc).isoformat()

        action_plan = ActionPlan(
            channel=trace.step2_action_plan.recommended_channel,
            tone=trace.step2_action_plan.tone,
            escalate_flag=trace.step2_action_plan.escalate_flag,
        )

        return DownstreamCMSPayload(
            delivery_id=delivery_id,
            timestamp_utc=timestamp_utc,
            record_id=record.id,
            source_system=record.source,
            recipient_name=record.name,
            contact_details=record.contact_info,
            classification=trace.step1_qualification.classification,
            action_plan=action_plan,
            personalized_message=trace.step3_message_result.final_message,
            agent_reasoning_trace=trace,
            schema_version="1.0.0",
        )

    def deliver_record(
        self, record: UnifiedRecord, trace: AgentReasoningTrace
    ) -> Tuple[DownstreamCMSPayload, CMSReceipt]:
        """
        Orchestrates payload construction and resilient delivery to Mock CMS.
        """
        self.delivery_count += 1
        payload = self.build_payload(record, trace)

        logger.info(
            f"[Delivery Dispatch] Transmitting record '{record.id}' "
            f"to CMS (Target Channel: {payload.action_plan.channel})..."
        )

        # Resilient dispatch with Tenacity retry
        receipt = self._dispatch_with_retry(payload, is_test_record=(self.delivery_count == 3))

        # Optional: Dual-push to webhook.site if configured
        if self.webhook_site_url:
            self._dual_push_webhook(payload)

        return payload, receipt

    def _log_retry_attempt(self, retry_state: RetryCallState) -> None:
        """Logs custom user-visible retry messages."""
        logger.warning(
            f"[RESILIENCE RETRY] CMS delivery attempt #{retry_state.attempt_number} failed. "
            f"Retrying with exponential backoff (Next delay: {retry_state.next_action.sleep:.1f}s)..."
        )

    def _dispatch_with_retry(
        self, payload: DownstreamCMSPayload, is_test_record: bool = False
    ) -> CMSReceipt:
        """
        Wrapped dispatch function executed under tenacity retry policy.
        Demonstrates Failure Case B on test record.
        """
        @retry(
            retry=retry_if_exception_type(TransientCMSError),
            wait=wait_exponential(multiplier=1.0, min=1.0, max=4.0),
            stop=stop_after_attempt(3),
            before_sleep=self._log_retry_attempt,
            reraise=True,
        )
        def _attempt_delivery() -> CMSReceipt:
            # FAILURE CASE B DEMONSTRATION:
            # On the 3rd record (is_test_record=True), deliberately trigger a transient 503 error on attempt 1!
            if self.simulate_transient_failure and is_test_record:
                attempts = self._simulated_failure_triggered.get(payload.record_id, 0)
                if attempts == 0:
                    self._simulated_failure_triggered[payload.record_id] = 1
                    logger.warning(
                        f"[FAILURE DEMO - Case B] Simulating transient HTTP 503 Service Unavailable "
                        f"from downstream CMS on record '{payload.record_id}' (Attempt 1/3)!"
                    )
                    raise TransientCMSError("Simulated Downstream Error: HTTP 503 Service Unavailable")
                else:
                    logger.info(
                        f"[RESILIENCE SUCCESS] Retry succeeded for record '{payload.record_id}' "
                        f"after transient recovery on attempt 2!"
                    )

            # Ingest payload via Mock CMS
            try:
                if self.use_direct_asgi:
                    # In-process execution: validates against contract, logs, and persists to outputs/cms_delivered_records.json
                    from src.mock_cms import ingest_record
                    return ingest_record(payload)
                else:
                    # Standard HTTP REST call
                    with httpx.Client(timeout=10.0) as client:
                        resp = client.post(self.cms_url, json=payload.model_dump())
                        if resp.status_code in [502, 503, 504]:
                            raise TransientCMSError(f"Transient CMS error {resp.status_code}")
                        resp.raise_for_status()
                        return CMSReceipt.model_validate(resp.json())
            except TransientCMSError:
                raise
            except Exception as exc:
                raise TransientCMSError(f"Delivery exception connecting to CMS: {exc}") from exc


        return _attempt_delivery()

    def _dual_push_webhook(self, payload: DownstreamCMSPayload) -> None:
        """Dual-pushes payload to configured external webhook.site endpoint."""
        try:
            logger.info(f"[Dual-Push] Forwarding payload copy to Webhook URL: {self.webhook_site_url}")
            with httpx.Client(timeout=8.0) as client:
                r = client.post(self.webhook_site_url, json=payload.model_dump())
                logger.info(f"[Dual-Push] Webhook received payload with status HTTP {r.status_code}")
        except Exception as e:
            logger.warning(f"[Dual-Push] Webhook notification failed (non-blocking): {e}")
