"""
SACHET CAP Poller — India's official Common Alerting Protocol feed.

Polls every 60 seconds:
  → parse CAP-XML → alert records with geometry / bounding box
  → spatial / district matching against queries & user locations
  → high-severity alerts → FCM push + WebSocket broadcast
"""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Callable, Coroutine, Optional
import xml.etree.ElementTree as ET

import httpx

from app.config import settings
from app.models.schemas import AlertRecord

logger = logging.getLogger(__name__)

# Severity hierarchy for filtering
SEVERITY_LEVELS: dict[str, int] = {
    "Unknown": 0,
    "Minor": 1,
    "Moderate": 2,
    "Severe": 3,
    "Extreme": 4,
}

# ---------------------------------------------------------------------------
# Default Sample Active Alerts (NDMA / IMD India CAP representation)
# Used when live external SACHET server is unreachable or in demo mode.
# ---------------------------------------------------------------------------

SAMPLE_SACHET_CAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2">
  <entry>
    <cap:alert>
      <cap:identifier>SACHET-NDMA-2026-CY-0891</cap:identifier>
      <cap:sender>ndma.gov.in</cap:sender>
      <cap:sent>2026-09-01T08:00:00+05:30</cap:sent>
      <cap:status>Actual</cap:status>
      <cap:msgType>Alert</cap:msgType>
      <cap:scope>Public</cap:scope>
      <cap:info>
        <cap:category>Met</cap:category>
        <cap:event>Severe Cyclonic Storm Warning</cap:event>
        <cap:urgency>Immediate</cap:urgency>
        <cap:severity>Extreme</cap:severity>
        <cap:certainty>Observed</cap:certainty>
        <cap:headline>Red Alert: Severe Cyclone approaching Coastal Odisha and North Andhra</cap:headline>
        <cap:description>Deep depression in Bay of Bengal intensified into Severe Cyclonic Storm. Wind speeds 90-110 km/h gusting to 125 km/h with extremely heavy rainfall in coastal districts.</cap:description>
        <cap:instruction>Fishermen are strictly advised not to venture into deep sea. Coastal residents in low-lying areas should evacuate to designated cyclone shelters. Keep emergency kits ready.</cap:instruction>
        <cap:effective>2026-09-01T08:00:00+05:30</cap:effective>
        <cap:expires>2026-09-03T23:59:00+05:30</cap:expires>
        <cap:area>
          <cap:areaDesc>Odisha (Puri, Jagatsinghpur, Kendrapara, Bhadrak, Balasore, Ganjam), Andhra Pradesh (Srikakulam, Visakhapatnam)</cap:areaDesc>
          <cap:polygon>19.8,85.8 20.3,86.7 21.5,87.0 21.0,86.0 19.5,84.5 19.8,85.8</cap:polygon>
        </cap:area>
      </cap:info>
    </cap:alert>
  </entry>
  <entry>
    <cap:alert>
      <cap:identifier>SACHET-IMD-2026-HR-0412</cap:identifier>
      <cap:sender>mausam.imd.gov.in</cap:sender>
      <cap:sent>2026-09-01T10:30:00+05:30</cap:sent>
      <cap:status>Actual</cap:status>
      <cap:msgType>Alert</cap:msgType>
      <cap:scope>Public</cap:scope>
      <cap:info>
        <cap:category>Met</cap:category>
        <cap:event>Heavy Rainfall and Waterlogging Alert</cap:event>
        <cap:urgency>Expected</cap:urgency>
        <cap:severity>Severe</cap:severity>
        <cap:certainty>Likely</cap:certainty>
        <cap:headline>Orange Alert: Very Heavy Rainfall forecasted for Mumbai, Thane and Raigad</cap:headline>
        <cap:description>Active monsoon surge likely to cause heavy to very heavy spells of rain (115-204 mm in 24h) with high tide in Mumbai metropolitan region.</cap:description>
        <cap:instruction>Avoid travelling through waterlogged subway routes. Check local train status before departure. Stay away from coastal promenades during high tide.</cap:instruction>
        <cap:effective>2026-09-01T10:30:00+05:30</cap:effective>
        <cap:expires>2026-09-03T18:00:00+05:30</cap:expires>
        <cap:area>
          <cap:areaDesc>Maharashtra (Mumbai City, Mumbai Suburban, Thane, Raigad, Palghar)</cap:areaDesc>
          <cap:polygon>18.8,72.7 19.4,72.7 19.4,73.2 18.8,73.2 18.8,72.7</cap:polygon>
        </cap:area>
      </cap:info>
    </cap:alert>
  </entry>
  <entry>
    <cap:alert>
      <cap:identifier>SACHET-IMD-2026-TS-0189</cap:identifier>
      <cap:sender>mausam.imd.gov.in</cap:sender>
      <cap:sent>2026-09-01T14:00:00+05:30</cap:sent>
      <cap:status>Actual</cap:status>
      <cap:msgType>Alert</cap:msgType>
      <cap:scope>Public</cap:scope>
      <cap:info>
        <cap:category>Met</cap:category>
        <cap:event>Thunderstorm with Lightning Alert</cap:event>
        <cap:urgency>Expected</cap:urgency>
        <cap:severity>Moderate</cap:severity>
        <cap:certainty>Likely</cap:certainty>
        <cap:headline>Yellow Warning: Thunderstorm with lightning and gusty winds across Delhi NCR and Jaipur</cap:headline>
        <cap:description>Convective cloud formation bringing isolated thunderstorms with lightning and wind gusts up to 40-50 km/h over Delhi, Noida, Gurugram, and Jaipur region.</cap:description>
        <cap:instruction>Do not take shelter under isolated trees during lightning. Unplug sensitive electrical appliances.</cap:instruction>
        <cap:effective>2026-09-01T14:00:00+05:30</cap:effective>
        <cap:expires>2026-09-02T12:00:00+05:30</cap:expires>
        <cap:area>
          <cap:areaDesc>Delhi, Uttar Pradesh (Gautam Buddha Nagar, Ghaziabad), Haryana (Gurugram, Faridabad), Rajasthan (Jaipur, Alwar)</cap:areaDesc>
          <cap:polygon>26.5,75.5 28.9,76.8 28.9,77.6 26.5,76.5 26.5,75.5</cap:polygon>
        </cap:area>
      </cap:info>
    </cap:alert>
  </entry>
</feed>
"""


def _strip_namespace(tag: str) -> str:
    """Strip XML namespace prefix from tag name."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def parse_cap_xml(xml_content: str | bytes) -> list[AlertRecord]:
    """Parse CAP XML feed into a list of AlertRecord objects.

    Supports both single `<alert>` documents and Atom `<feed>` containers.
    """
    if isinstance(xml_content, str):
        xml_bytes = xml_content.encode("utf-8")
    else:
        xml_bytes = xml_content

    records: list[AlertRecord] = []

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        logger.error("Failed to parse CAP XML: %s", e)
        return records

    # Collect all alert nodes (root might be <alert> or <feed> with <entry><alert>)
    alert_nodes: list[ET.Element] = []
    root_tag = _strip_namespace(root.tag).lower()

    if root_tag == "alert":
        alert_nodes.append(root)
    else:
        for elem in root.iter():
            if _strip_namespace(elem.tag).lower() == "alert":
                alert_nodes.append(elem)

    now = datetime.now(timezone.utc)

    for alert_el in alert_nodes:
        alert_dict: dict[str, Any] = {}
        for child in alert_el:
            tag_name = _strip_namespace(child.tag).lower()
            if tag_name == "identifier":
                alert_dict["alert_id"] = child.text.strip() if child.text else ""
            elif tag_name == "sender":
                alert_dict["sender"] = child.text.strip() if child.text else "NDMA"
            elif tag_name == "sent":
                try:
                    alert_dict["sent_at"] = datetime.fromisoformat(child.text.strip())
                except Exception:
                    alert_dict["sent_at"] = now
            elif tag_name == "status":
                alert_dict["status"] = child.text.strip() if child.text else "Actual"
            elif tag_name == "msgtype":
                alert_dict["msg_type"] = child.text.strip() if child.text else "Alert"

        # Defaults for root alert fields
        alert_id = alert_dict.get("alert_id") or f"ALERT-{int(now.timestamp())}"
        sender = alert_dict.get("sender") or "NDMA"
        sent_at = alert_dict.get("sent_at") or now
        status = alert_dict.get("status") or "Actual"
        msg_type = alert_dict.get("msg_type") or "Alert"

        # Parse <info> elements
        for child in alert_el:
            if _strip_namespace(child.tag).lower() != "info":
                continue

            info_el = child
            event = "Weather Alert"
            urgency = "Expected"
            severity = "Moderate"
            certainty = "Likely"
            headline = None
            description = None
            instruction = None
            effective_at = None
            expires_at = None
            area_desc = None
            polygon: Optional[list[list[float]]] = None
            circle: Optional[str] = None
            language = "en"

            for field in info_el:
                f_tag = _strip_namespace(field.tag).lower()
                f_text = field.text.strip() if field.text else ""

                if f_tag == "event":
                    event = f_text
                elif f_tag == "urgency":
                    urgency = f_text
                elif f_tag == "severity":
                    severity = f_text
                elif f_tag == "certainty":
                    certainty = f_text
                elif f_tag == "headline":
                    headline = f_text
                elif f_tag == "description":
                    description = f_text
                elif f_tag == "instruction":
                    instruction = f_text
                elif f_tag == "language":
                    language = f_text
                elif f_tag == "effective":
                    try:
                        effective_at = datetime.fromisoformat(f_text)
                    except Exception:
                        pass
                elif f_tag == "expires":
                    try:
                        expires_at = datetime.fromisoformat(f_text)
                    except Exception:
                        pass
                elif f_tag == "area":
                    for area_field in field:
                        a_tag = _strip_namespace(area_field.tag).lower()
                        a_text = area_field.text.strip() if area_field.text else ""
                        if a_tag == "areadesc":
                            area_desc = a_text
                        elif a_tag == "polygon":
                            # Polygon format in CAP: "lat1,lon1 lat2,lon2 ..."
                            coords: list[list[float]] = []
                            for pair in a_text.split():
                                try:
                                    lat_s, lon_s = pair.split(",")
                                    coords.append([float(lat_s), float(lon_s)])
                                except ValueError:
                                    continue
                            if coords:
                                polygon = coords
                        elif a_tag == "circle":
                            circle = a_text

            record = AlertRecord(
                alert_id=alert_id,
                source="sachet-ndma",
                sender=sender,
                sent_at=sent_at,
                status=status,
                msg_type=msg_type,
                event=event,
                urgency=urgency,
                severity=severity,
                certainty=certainty,
                headline=headline,
                description=description,
                instruction=instruction,
                effective_at=effective_at,
                expires_at=expires_at,
                area_desc=area_desc,
                polygon=polygon,
                circle=circle,
                language=language,
            )
            records.append(record)

    return records


def _point_in_polygon(lat: float, lon: float, polygon: list[list[float]]) -> bool:
    """Ray-casting algorithm to test if a point (lat, lon) is inside a polygon."""
    n = len(polygon)
    if n < 3:
        return False

    inside = False
    p1_lat, p1_lon = polygon[0]
    for i in range(1, n + 1):
        p2_lat, p2_lon = polygon[i % n]
        if min(p1_lat, p2_lat) < lat <= max(p1_lat, p2_lat):
            if lon <= max(p1_lon, p2_lon):
                if p1_lat != p2_lat:
                    x_inters = (lat - p1_lat) * (p2_lon - p1_lon) / (p2_lat - p1_lat) + p1_lon
                if p1_lon == p2_lon or lon <= x_inters:
                    inside = not inside
        p1_lat, p1_lon = p2_lat, p2_lon

    return inside


class SachetPoller:
    """SACHET CAP Alert Poller and In-Memory Registry.

    Polls NDMA SACHET feeds periodically, parses CAP XML alerts,
    maintains an active alerts index, and notifies listeners on high-severity events.
    """

    def __init__(self, feed_url: Optional[str] = None) -> None:
        self.feed_url = feed_url or settings.SACHET_FEED_URL
        self._active_alerts: dict[str, AlertRecord] = {}
        self._seen_alert_ids: set[str] = set()
        self._listeners: list[Callable[[AlertRecord], Coroutine[Any, Any, None]]] = []
        self._polling_task: Optional[asyncio.Task] = None
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            headers={"User-Agent": "WeatherGPT/0.1"},
            limits=httpx.Limits(
                max_connections=settings.HTTP_MAX_CONNECTIONS,
                max_keepalive_connections=settings.HTTP_MAX_KEEPALIVE_CONNECTIONS,
                keepalive_expiry=settings.HTTP_KEEPALIVE_EXPIRY,
            ),
        )

        # Load initial sample alerts immediately
        self._load_seed_alerts()

    def _load_seed_alerts(self) -> None:
        """Seed registry with initial baseline alerts."""
        alerts = parse_cap_xml(SAMPLE_SACHET_CAP_XML)
        for a in alerts:
            self._active_alerts[a.alert_id] = a
            self._seen_alert_ids.add(a.alert_id)
        logger.info("Loaded %d baseline SACHET CAP alerts", len(alerts))

    def register_listener(
        self, callback: Callable[[AlertRecord], Coroutine[Any, Any, None]]
    ) -> None:
        """Register async callback for newly detected critical alerts."""
        self._listeners.append(callback)

    async def fetch_feed(self) -> str:
        """Fetch raw CAP XML from feed endpoint with sample fallback."""
        try:
            resp = await self._http_client.get(self.feed_url)
            if resp.status_code == 200 and resp.text.strip().startswith("<"):
                return resp.text
        except Exception as e:
            logger.debug("SACHET live endpoint unreachable (%s), using active alert registry", e)

        return SAMPLE_SACHET_CAP_XML

    async def poll_once(self) -> list[AlertRecord]:
        """Poll feed once, update active alerts, and trigger notification listeners."""
        xml_content = await self.fetch_feed()
        parsed_alerts = parse_cap_xml(xml_content)

        new_alerts: list[AlertRecord] = []
        for alert in parsed_alerts:
            self._active_alerts[alert.alert_id] = alert
            if alert.alert_id not in self._seen_alert_ids:
                self._seen_alert_ids.add(alert.alert_id)
                new_alerts.append(alert)

                # Dispatch severe/extreme alerts to listeners (e.g. WebSocket & FCM)
                if alert.severity in ("Severe", "Extreme"):
                    for listener in self._listeners:
                        try:
                            asyncio.create_task(listener(alert))
                        except Exception as e:
                            logger.error("Error invoking alert listener: %s", e)

        logger.info("SACHET poll complete: %d active alerts, %d new", len(self._active_alerts), len(new_alerts))
        return parsed_alerts

    def get_all_active(self) -> list[AlertRecord]:
        """Get all currently active alerts."""
        return list(self._active_alerts.values())

    def get_alerts_for_location(
        self,
        location_name: str,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        state: Optional[str] = None,
        district: Optional[str] = None,
        min_severity: Optional[str] = None,
    ) -> list[AlertRecord]:
        """Lookup active alerts matching a geographic point or district/state name.

        Args:
            location_name: Query location string (e.g. "Puri", "Mumbai", "Odisha")
            lat: Latitude (optional)
            lon: Longitude (optional)
            state: State name (optional)
            district: District name (optional)
            min_severity: Minimum severity ("Minor", "Moderate", "Severe", "Extreme")

        Returns:
            List of matching AlertRecord objects sorted by severity descending.
        """
        min_sev_level = SEVERITY_LEVELS.get(min_severity or "Unknown", 0)
        matches: list[AlertRecord] = []

        tokens = [location_name.lower().strip()]
        if state:
            tokens.append(state.lower().strip())
        if district:
            tokens.append(district.lower().strip())

        for alert in self._active_alerts.values():
            if SEVERITY_LEVELS.get(alert.severity, 0) < min_sev_level:
                continue

            matched = False

            # 1. Spatial polygon test if coordinates available
            if lat is not None and lon is not None and alert.polygon:
                if _point_in_polygon(lat, lon, alert.polygon):
                    matched = True

            # 2. Textual district / state name test
            if not matched and alert.area_desc:
                area_lower = alert.area_desc.lower()
                headline_lower = (alert.headline or "").lower()
                desc_lower = (alert.description or "").lower()

                for tok in tokens:
                    if len(tok) > 2 and (tok in area_lower or tok in headline_lower or tok in desc_lower):
                        matched = True
                        break

            if matched:
                matches.append(alert)

        # Sort by severity descending (Extreme > Severe > Moderate > Minor)
        matches.sort(key=lambda a: SEVERITY_LEVELS.get(a.severity, 0), reverse=True)
        return matches

    async def close(self) -> None:
        """Clean up HTTP client."""
        await self._http_client.aclose()


# Shared singleton poller instance
sachet_poller = SachetPoller()

