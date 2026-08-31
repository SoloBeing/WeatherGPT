"""
get_alerts(geom) — Active weather alerts for a geometry.

Queries PostGIS for SACHET CAP alerts + IMD district colour-coded warnings
that ST_Intersects with the given point/polygon.
"""
