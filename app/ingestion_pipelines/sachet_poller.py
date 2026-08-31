"""
SACHET CAP Poller — India's official Common Alerting Protocol feed.

Polls every 60 seconds:
  → parse CAP-XML → alert row with PostGIS geometry
  → ST_Intersects against user_locations
  → matched users → FCM push + WebSocket broadcast
"""
