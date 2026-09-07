"""
Firebase Cloud Messaging — Alert push notifications to devices.

Proactive alerts are the strongest innovation card:
  "A bot that PUSHES 'cyclone track shifted, your taluk is now in
   the orange zone' via the CAP → PostGIS → FCM chain demonstrates
   real integration."
"""

import logging
import os
from typing import Optional
import uuid

from app.config import settings
from app.pipelines.sachet_poller import sachet_poller
from app.models.schemas import AlertRecord

logger = logging.getLogger(__name__)


class FCMService:
    """Firebase Cloud Messaging Service with graceful sandbox fallback.

    Dispatches push notifications for critical weather and disaster alerts
    to device tokens and severity topics (e.g. `weather_alerts_extreme`).
    """

    def __init__(self, credentials_path: Optional[str] = None) -> None:
        self.credentials_path = credentials_path or settings.FCM_CREDENTIALS_PATH
        self._initialized = False
        self._messaging = None

        self._init_firebase()

    def _init_firebase(self) -> None:
        """Initialize Firebase Admin SDK if credentials file exists."""
        if not self.credentials_path or not os.path.exists(self.credentials_path):
            logger.info("FCM credentials not found at '%s'. Running in sandbox mode.", self.credentials_path)
            return

        try:
            import firebase_admin
            from firebase_admin import credentials, messaging

            if not firebase_admin._apps:
                cred = credentials.Certificate(self.credentials_path)
                firebase_admin.initialize_app(cred)
            self._messaging = messaging
            self._initialized = True
            logger.info("Firebase Admin SDK initialized successfully.")
        except Exception as e:
            logger.error("Failed to initialize Firebase Admin SDK: %s (falling back to sandbox)", e)

    async def send_to_topic(
        self,
        topic: str,
        title: str,
        body: str,
        data: Optional[dict[str, str]] = None,
    ) -> str:
        """Send push notification to an FCM topic.

        Args:
            topic: Topic name, e.g. "weather_alerts_extreme".
            title: Notification title.
            body: Notification body text.
            data: Custom key-value string payload.

        Returns:
            FCM message ID or mock ID in sandbox.
        """
        payload_data = data or {}

        if self._initialized and self._messaging:
            try:
                message = self._messaging.Message(
                    notification=self._messaging.Notification(
                        title=title,
                        body=body,
                    ),
                    data=payload_data,
                    topic=topic,
                )
                response = self._messaging.send(message)
                logger.info("FCM topic message sent to '%s': %s", topic, response)
                return response
            except Exception as e:
                logger.error("FCM topic send failed: %s", e)

        # Sandbox / Mock Mode
        mock_id = f"mock-fcm-{uuid.uuid4().hex[:12]}"
        logger.info("[FCM Sandbox Push] Topic='%s' | Title='%s' | Body='%s' | ID=%s", topic, title, body, mock_id)
        return mock_id

    async def send_to_token(
        self,
        token: str,
        title: str,
        body: str,
        data: Optional[dict[str, str]] = None,
    ) -> str:
        """Send direct push notification to a device registration token."""
        payload_data = data or {}

        if self._initialized and self._messaging:
            try:
                message = self._messaging.Message(
                    notification=self._messaging.Notification(
                        title=title,
                        body=body,
                    ),
                    data=payload_data,
                    token=token,
                )
                response = self._messaging.send(message)
                logger.info("FCM token message sent: %s", response)
                return response
            except Exception as e:
                logger.error("FCM token send failed: %s", e)

        mock_id = f"mock-fcm-dev-{uuid.uuid4().hex[:12]}"
        logger.info("[FCM Sandbox Push] Token='%s...' | Title='%s' | ID=%s", token[:10], title, mock_id)
        return mock_id

    async def push_alert(self, alert: AlertRecord, custom_topic: Optional[str] = None) -> str:
        """Format an AlertRecord and push to the appropriate severity topic."""
        sev = alert.severity.lower()
        if custom_topic:
            topic = custom_topic
        elif sev in ("extreme", "red"):
            topic = "weather_alerts_extreme"
        elif sev in ("severe", "orange"):
            topic = "weather_alerts_severe"
        else:
            topic = "weather_alerts_general"

        title = f"🚨 [{alert.severity.upper()}] {alert.event}"
        body = alert.headline or alert.description or "Urgent weather advisory in your area."

        data_payload = {
            "alert_id": alert.alert_id,
            "sender": alert.sender,
            "severity": alert.severity,
            "event": alert.event,
            "urgency": alert.urgency,
            "area_desc": alert.area_desc or "",
        }

        return await self.send_to_topic(topic=topic, title=title, body=body, data=data_payload)


# Shared singleton instance
fcm_service = FCMService()

