# LUMINARK CodeWriter
## Active Governance Layer — Stanfield's Axiom of Perpetuity

**Meridian Axiom Alignment Technologies (MAAT)**

> *"The system that cannot see its own failure mode is already in Stage 8."*

---

## What is LUMINARK?

LUMINARK CodeWriter is an **Active Governance Layer** for AI-generated and human-written Python code. It applies the **Stanfield Axiom of Perpetuity (SAP)** — a 10-stage mathematical framework for modelling dynamic system evolution — to classify, monitor, and repair code failures before they reach production.

Instead of asking *"did this code run?"*, LUMINARK asks:

> *"Where is this system on the SAP torus cycle, and is it moving toward stability or collapse?"*

### The Three Guarantees

1. **Lyapunov Stability** — `V(H, E, v) = w_H·H + w_E·E + w_v·v²` governs every execution. Code that increases V is escalated. Code that decreases V is accepted.
2. **Geometric Constraint** — SAP stage transitions are hard-enforced. Stage 5 is a point of no return. Stage 8 is a terminal branch. No skipping.
3. **Surgical Repair** — Every failure is diagnosed by the SAP Psychiatrist, mapped to its exact SAP stage, and given a targeted repair instruction.

---

## Architecture

```
luminark_gate.py              ← CLI entry point
main.py                       ← FastAPI HTTP service + Redis telemetry
│
├── luminark/
│   ├── sap_geometry_engine.py      ← 10-stage SAP classification
│   ├── sap_constrained_bayesian.py ← Bayesian posterior + trap energy field
│   ├── sap_lyapunov.py             ← Lyapunov V(H,E,v) + NumericalConstitution
│   ├── sap_stage_classifier.py     ← SAP Psychiatrist + Surgical Prompts
│   └── luminark_live_bridge.py     ← Governance orchestrator (The Bridge)
│
├── Dockerfile                ← Python 3.11-slim sandbox (The Crucible)
├── entrypoint.sh             ← ulimit resource constraints
├── docker-compose.yml        ← sandbox + redis services
└── tests/
    ├── test_nsdt_clinical_trial.py  ← 54-test clinical trial suite
    └── test_live_bridge.py          ← Integration tests for the Bridge
```

---

## Governance Loop

```
Code Input
    │
    ▼
Execute in Sandbox (Docker — network-isolated, memory/CPU-limited)
    │
    ▼
Extract NSDT Vector [Complexity, Stability, Tension, Adaptability, Coherence]
    │
    ▼
SAPConstrainedBayesian.forward()  →  SAP Stage (0–9) + Posterior + Trap Energy
    │
    ▼
NumericalConstitution.certify()   →  V = w_H·H + w_E·E + w_v·v²
    │
    ├── V < threshold  →  ✅ PASS
    │
    └── V ≥ threshold  →  SAPPsychiatrist.diagnose()
                              │
                              ▼
                         Surgical Prompt  →  Repair  →  Re-execute
                         (up to max_iterations)
                              │
                              └── Still failing  →  FAIL_EXHAUSTED
```

---

## SAP Stage Reference

| Stage | Name | Geometry | Logistics Analogy |
|-------|------|----------|-------------------|
| 0 | Plenara | Sphere | Void / Missing dependency |
| 1 | The Spark | Point | Unbound name |
| 2 | The Vessel | Line | Type mismatch |
| 3 | The Engine | Triangle | Logic error |
| 4 | The Crucible | Square | Boundary violation |
| 5 | The Dynamo | Pentagon | **Threshold — point of no return** |
| 6 | The Nexus | Hexagon | I/O failure |
| 7 | The Lens | Heptagon | Runtime / concurrency |
| 8 | The Vessel of Grounding | Octagon | **False Hell — silent wrong result** |
| 9 | The Transparency | Nonagon | Critical resource exhaustion |

---

## Quick Start

### Install

```bash
git clone https://github.com/foreverforward760-crypto/LuminarkCodeWriter.git
cd LuminarkCodeWriter
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### Build the sandbox

```bash
make build
```

### Run governance on a file

```bash
# LOCAL mode (no Docker needed)
python luminark_gate.py govern path/to/code.py

# DOCKER mode (production — resource-constrained sandbox)
python luminark_gate.py govern path/to/code.py --mode docker
```

### Run as HTTP service

```bash
docker-compose up --build
# POST http://localhost:8080/govern
```

### Run tests

```bash
make test
# or
pytest tests/ -v
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/govern` | Full governance loop — returns verdict + audit trail |
| `POST` | `/stage-report` | Quick SAP stage check (no repair) |
| `GET`  | `/telemetry/{id}` | V-series + stage history from Redis |
| `GET`  | `/health` | Liveness check |

### POST `/govern`

```json
{
  "code": "def add(a, b):\n    return a + b\nprint(add(1, 2))",
  "context_id": "my-session-001",
  "task_description": "simple addition function"
}
```

**Response:**

```json
{
  "verdict": "PASS",
  "iterations": 1,
  "sap_stage": 4,
  "stage_name": "The Crucible",
  "V": 1.23,
  "passed": true,
  "audit_trail": [...]
}
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LUMINARK_MODE` | `docker` | `docker` or `local` |
| `LUMINARK_MAX_ITERATIONS` | `3` | Max repair attempts |
| `LUMINARK_STABILITY_THRESHOLD` | `3.0` | Lyapunov V pass threshold |
| `LUMINARK_DOCKER_IMAGE` | `luminark-sandbox:latest` | Sandbox image |
| `REDIS_URL` | `redis://redis:6379` | Redis connection string |

---

## License

**Proprietary & Confidential**
© 2026 Meridian Axiom Alignment Technologies LLC. All rights reserved.

SAP (Stanfield's Axiom of Perpetuity) is proprietary intellectual property of
Richard Stanfield / MAAT. Unauthorized use prohibited.

---

*Built with SAP. Governed by Mathematics. Stability is not optional.*
