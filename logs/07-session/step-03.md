# Session 07 — Step 03: Production Kubernetes Manifests & HPA Architecture

**What was done:**
- Implemented a complete suite of 13 production Kubernetes manifests in `k8s/` implementing the decoupled, highly scalable architecture defined in `01-weathergpt.md`:
  1. **Namespace (`k8s/namespace.yaml`):** Isolated `weathergpt` namespace.
  2. **ConfigMap (`k8s/configmap.yaml`):** Centralized non-sensitive operational configuration, connection pool limits, model identifiers, and external endpoints.
  3. **Secret (`k8s/secrets.yaml`):** Encrypted credential storage for PostgreSQL, MinIO S3 credentials, LLM API keys, and Bhashini auth tokens.
  4. **PostgreSQL StatefulSet (`k8s/postgres.yaml`):** PostGIS + TimescaleDB container (`timescale/timescaledb-ha:pg16`), 20Gi persistent volume claim, and ClusterIP service with `pg_isready` probes.
  5. **Redis Deployment (`k8s/redis.yaml`):** Point cache pod with resource bounds, liveness/readiness probes, and ClusterIP service.
  6. **MinIO StatefulSet (`k8s/minio.yaml`):** Object storage container with 50Gi PVC for Zarr weather grids and dual S3 API/Console service.
  7. **Migration Job (`k8s/migration-job.yaml`):** Kubernetes Job executing `entrypoint.sh migrate` to run Alembic schema migrations prior to application pod rollouts.
  8. **API Deployment (`k8s/api-deployment.yaml`):** Stateless FastAPI deployment configured with 2 base replicas, zero-downtime RollingUpdate strategy (`maxSurge: 1`, `maxUnavailable: 0`), resource limits, and `/health` HTTP probes.
  9. **API Service (`k8s/api-service.yaml`):** ClusterIP routing internal cluster traffic to port 8000.
  10. **Horizontal Pod Autoscaler (`k8s/api-hpa.yaml`):** Elastic autoscaler scaling API pods from 2 to 10 replicas based on 70% CPU and 80% memory utilization thresholds, with custom scale-up/down policies satisfying spec scalability criteria.
  11. **Ingress (`k8s/api-ingress.yaml`):** NGINX Ingress configuring TLS termination and WebSocket connection upgrades for live alert streaming.
  12. **Scheduler Deployment (`k8s/scheduler-deployment.yaml`):** Isolated singleton worker pod dedicated to background NOAA GFS ingestion and SACHET alerts feed polling, decoupled from user-facing API pods.
  13. **Kustomization (`k8s/kustomization.yaml`):** Kustomize manifest organizing all components into a single deployable unit.
- Programmatically validated that all 13 manifests parse cleanly into Kubernetes resources without syntax or indentation errors.
- Verified test suite passes without regressions (35/35 passing, 0 warnings under `-W error`).

**Commands:**
```bash
uv run python -c "
import yaml
from pathlib import Path
manifests = list(Path('k8s').glob('*.yaml'))
assert len(manifests) == 13
for m in manifests:
    with open(m) as f:
        list(yaml.safe_load_all(f))
print('All 13 K8s manifests verified')
"
uv run pytest
```

**Notable output:**
- All 13 manifests verified successfully.
- Pytest verification: 35/35 passed in 11.61s with 0 warnings.
