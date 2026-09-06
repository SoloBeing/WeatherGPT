"""
Tests for Session 07 — Containerization, Kubernetes Orchestration & System Demo.

Validates:
1. Dockerfile multi-stage structure, Astral uv tooling, and non-root security.
2. Docker Compose service dependency graphs, volumes, and healthchecks.
3. Kubernetes manifest configurations, StatefulSets, Deployments, and HPA policies.
4. End-to-end demo runner execution.
"""

from pathlib import Path
import yaml
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_dockerfile_structure():
    """Verify Dockerfile contains multi-stage build, Astral uv, and non-root user."""
    dockerfile_path = REPO_ROOT / "Dockerfile"
    assert dockerfile_path.exists(), "Dockerfile must exist at repository root"

    content = dockerfile_path.read_text(encoding="utf-8")
    assert "AS builder" in content, "Dockerfile must use a builder stage"
    assert "AS runtime" in content, "Dockerfile must use a runtime stage"
    assert "ghcr.io/astral-sh/uv" in content, "Dockerfile must use Astral uv"
    assert "USER weathergpt" in content, "Dockerfile must run as non-root user"
    assert "ENTRYPOINT" in content, "Dockerfile must define an ENTRYPOINT"
    assert "HEALTHCHECK" in content, "Dockerfile must configure a container HEALTHCHECK"


def test_dockerignore_configuration():
    """Verify .dockerignore excludes sensitive files and bulky caches."""
    dockerignore_path = REPO_ROOT / ".dockerignore"
    assert dockerignore_path.exists(), ".dockerignore must exist at repository root"

    content = dockerignore_path.read_text(encoding="utf-8")
    for pattern in [".git", ".venv", "__pycache__", ".pytest_cache", "dev-logs"]:
        assert pattern in content, f".dockerignore must ignore {pattern}"


def test_docker_entrypoint_executable():
    """Verify entrypoint.sh exists and supports api, worker, and migrate commands."""
    entrypoint_path = REPO_ROOT / "docker" / "entrypoint.sh"
    assert entrypoint_path.exists(), "docker/entrypoint.sh must exist"

    content = entrypoint_path.read_text(encoding="utf-8")
    assert "uvicorn app.main:app" in content
    assert "app.pipelines.scheduler" in content
    assert "alembic upgrade head" in content


def test_docker_compose_validity():
    """Verify docker-compose.yml defines all required services and dependency trees."""
    compose_path = REPO_ROOT / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml must exist"

    with open(compose_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    services = data.get("services", {})
    required_services = ["postgres", "redis", "minio", "minio-init", "migrations", "api", "worker"]
    for s in required_services:
        assert s in services, f"docker-compose.yml missing service: {s}"

    # Verify API depends on databases and completed migrations
    api_deps = services["api"].get("depends_on", {})
    assert "postgres" in api_deps
    assert "redis" in api_deps
    assert "minio" in api_deps
    assert "migrations" in api_deps
    assert api_deps["migrations"]["condition"] == "service_completed_successfully"

    # Verify persistent volumes
    volumes = data.get("volumes", {})
    for v in ["pgdata", "redisdata", "miniodata"]:
        assert v in volumes, f"docker-compose.yml missing volume: {v}"


def test_kubernetes_manifests_integrity():
    """Verify all Kubernetes manifests in k8s/ parse cleanly and contain required specs."""
    k8s_dir = REPO_ROOT / "k8s"
    assert k8s_dir.exists() and k8s_dir.is_dir()

    manifest_files = list(k8s_dir.glob("*.yaml"))
    assert len(manifest_files) == 13, f"Expected 13 k8s manifests, found {len(manifest_files)}"

    kinds_found = set()
    for mf in manifest_files:
        with open(mf, encoding="utf-8") as f:
            docs = list(yaml.safe_load_all(f))
            for doc in docs:
                if doc and "kind" in doc:
                    kinds_found.add(doc["kind"])

    expected_kinds = {
        "Namespace", "ConfigMap", "Secret", "StatefulSet",
        "Deployment", "Service", "Job", "HorizontalPodAutoscaler",
        "Ingress", "Kustomization",
    }
    for k in expected_kinds:
        assert k in kinds_found, f"Expected Kubernetes kind '{k}' not found in k8s/ manifests"


def test_hpa_scalability_parameters():
    """Verify HorizontalPodAutoscaler targets API deployment with 2-10 replicas."""
    hpa_path = REPO_ROOT / "k8s" / "api-hpa.yaml"
    assert hpa_path.exists()

    with open(hpa_path, encoding="utf-8") as f:
        hpa = yaml.safe_load(f)

    assert hpa["kind"] == "HorizontalPodAutoscaler"
    assert hpa["spec"]["scaleTargetRef"]["name"] == "weathergpt-api"
    assert hpa["spec"]["minReplicas"] == 2
    assert hpa["spec"]["maxReplicas"] == 10

    metrics = {m["resource"]["name"]: m["resource"]["target"]["averageUtilization"] for m in hpa["spec"]["metrics"]}
    assert metrics.get("cpu") == 70
    assert metrics.get("memory") == 80


@pytest.mark.asyncio
async def test_demo_script_runner():
    """Verify that the end-to-end demo script executes all steps cleanly."""
    from scripts.demo import main_demo
    exit_code = await main_demo()
    assert exit_code == 0, "scripts/demo.py should return exit code 0"
