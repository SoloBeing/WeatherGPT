# Session 01 — Step 01: Install All Project Dependencies

**Date:** 2026-08-31  
**Time:** ~21:20 – 21:35 IST  
**Goal:** Install every Python dependency from the WeatherGPT spec sheet into the project via `uv add`.

---

## Pre-existing state

- Python 3.13 (set in `.python-version`)
- Package manager: `uv` (with `uv.lock` already present)
- `pyproject.toml` had zero dependencies
- Empty `main.py` with hello-world

---

## Commands Run

### 1. Create logs directory

```bash
mkdir -p logs/01-session
```

### 2. API layer dependencies

```bash
uv add fastapi "uvicorn[standard]" httpx pydantic-settings python-dotenv
```

**Installed (23 packages):**
annotated-doc, annotated-types, anyio, certifi, click, fastapi 0.141.1, h11, httpcore, httptools, httpx 0.28.1, idna, pydantic 2.13.5, pydantic-core, pydantic-settings 2.15.0, python-dotenv 1.2.3, pyyaml, starlette, typing-extensions, typing-inspection, uvicorn 0.52.4, uvloop, watchfiles, websockets 17.1

### 3. Data/grid layer dependencies

```bash
uv add xarray zarr cfgrib eccodes netcdf4 scipy herbie-data ecmwf-opendata
```

**Installed (30 packages):**
attrs, cffi, cfgrib 0.9.15.1, cftime, charset-normalizer, donfig, eccodes 2.48.0, eccodeslib, eckitlib, ecmwf-opendata 0.3.34, findlibs, google-crc32c, herbie-data 2026.3.0, multiurl, netcdf4 1.7.4, numcodecs, numpy 2.5.2, packaging, pandas 3.0.5, pycparser, pyproj, python-dateutil, pytz, requests, scipy 1.18.1, six, tqdm, urllib3, xarray 2026.7.0, zarr 3.3.0

### 4. Database, cache, and infra dependencies

```bash
uv add sqlalchemy asyncpg geoalchemy2 alembic redis minio boto3
```

**Installed (16 packages):**
alembic 1.19.1, argon2-cffi, argon2-cffi-bindings, asyncpg 0.31.0, boto3 1.43.83, botocore, geoalchemy2 0.20.0, greenlet, jmespath, mako, markupsafe, minio 7.2.20, pycryptodome, redis 8.1.0, s3transfer, sqlalchemy 2.0.52

### 5. LLM, realtime, push, and scheduling dependencies

```bash
uv add litellm paho-mqtt aiohttp apscheduler firebase-admin
```

**Installed (51 packages):**
aiohappyeyeballs, aiohttp 3.14.3, aiosignal, apscheduler 3.11.3, cachecontrol, cryptography, distro, fastuuid, filelock, firebase-admin 7.5.0, frozenlist, fsspec, google-api-core, google-auth, google-cloud-core, google-cloud-firestore, google-cloud-storage, google-resumable-media, googleapis-common-protos, grpcio, grpcio-status, h2, hf-xet, hpack, huggingface-hub, hyperframe, importlib-metadata, jinja2, jiter, jsonschema, jsonschema-specifications, litellm 1.98.0, msgpack, multidict, openai 2.54.0, paho-mqtt 2.1.0, propcache, proto-plus, protobuf, pyasn1, pyasn1-modules, pyjwt, referencing, regex, rpds-py, sniffio, tiktoken, tokenizers, tzlocal, yarl, zipp

### 6. Verify imports

```bash
uv run python -c "import fastapi, uvicorn, xarray, zarr, sqlalchemy, redis, litellm, httpx; print('All core imports OK')"
```

**Output:** `All core imports OK`

---

## Final `pyproject.toml` dependencies

```toml
dependencies = [
    "aiohttp>=3.14.3",
    "alembic>=1.19.1",
    "apscheduler>=3.11.3",
    "asyncpg>=0.31.0",
    "boto3>=1.43.83",
    "cfgrib>=0.9.15.1",
    "eccodes>=2.48.0",
    "ecmwf-opendata>=0.3.34",
    "fastapi>=0.141.1",
    "firebase-admin>=7.5.0",
    "geoalchemy2>=0.20.0",
    "herbie-data>=2026.3.0",
    "httpx>=0.28.1",
    "litellm>=1.98.0",
    "minio>=7.2.20",
    "netcdf4>=1.7.4",
    "paho-mqtt>=2.1.0",
    "pydantic-settings>=2.15.0",
    "python-dotenv>=1.2.3",
    "redis>=8.1.0",
    "scipy>=1.18.1",
    "sqlalchemy>=2.0.52",
    "uvicorn[standard]>=0.52.4",
    "xarray>=2026.7.0",
    "zarr>=3.3.0",
]
```

**Total: 25 direct dependencies, ~120 transitive packages installed.**

---

## Notes

- All packages confirmed compatible with Python 3.13 before installation.
- `cfgrib` and `eccodes` require the system-level ecCodes C library (`libeccodes-dev` on Debian/Ubuntu) — the Python `eccodeslib` wheel bundled it here, but this may need manual install on other systems.
- `websockets` was pulled in as a transitive dep of `uvicorn[standard]` — no separate install needed.

---

**Next:** Step 02 — Create project directory structure and scaffold files, then initial git commit.
