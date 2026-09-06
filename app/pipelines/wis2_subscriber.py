"""
WIS2 MQTT Subscriber — Long-running connection to WMO Global Broker.

  → MQTTS globalbroker.meteo.fr:8883
  → topic origin/a/wis2/#, filter India centres
  → notification carries a canonical URL → fetch payload
  → parse → Postgres
"""
