"""
Alerts Routes — Weather alert endpoints.

  - GET /alerts?lat=...&lon=...  (active alerts for a location)
  - GET /alerts/subscribe         (register for push notifications)

Data flows from SACHET CAP → PostGIS → ST_Intersects → user match.
"""
