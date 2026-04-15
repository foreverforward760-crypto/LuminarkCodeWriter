# Contributing to LUMINARK CodeWriter

**Meridian Axiom Alignment Technologies (MAAT)**

Thank you for contributing to the LUMINARK Active Governance Layer. This document
describes the developer setup, coding standards, and pull request process.

---

## Architecture Overview

Before contributing, understand the three-layer architecture:

```
┌─────────────────────────────────────────────────────┐
│  LuminarkLiveBridge  (orchestrator)                  │
│  ├── Execute code in Docker sandbox (The Crucible)   │
│  ├── Evaluate via Numerical Constitution             │
│  └── Repair via SAPPsychiatrist Surgical Prompts     │
├─────────────────────────────────────────────────────┤
│  SAP Core (geometry + probability + energy)          │
│  ├── sap_geometry_engine.py   — 10-stage state space │
│  ├── sap_constrained_bayesian.py — posterior + traps │
│  └── sap_lyapunov.py          — stability monitor    │
├─────────────────────────────────────────────────────┤
│  Intelligence Layer                                   │
│  └── sap_stage_classifier.py — SAP Psychiatrist      │
└─────────────────────────────────────────────────────┘
```

---

## Developer Setup

### Prerequisites

- Python 3.11+
- Docker 24+ (for sandbox execution)
- Git 2.40+

### 1. Clone and install

```bash
git clone https://github.com/foreverforward760-crypto/LuminarkCodeWriter.git
cd LuminarkCodeWriter

# Create virtual environment
python -m venv .venv
source .venv/bin/activate      # macOS/Linux
.venv\Scripts\activate.bat     # Windows

# Install with dev dependencies
pip install -e ".[dev]"
```

### 2. Build the sandbox

```bash
docker build -t luminark-sandbox:latest .
```

### 3. Run the test suite

```bash
pytest tests/ -v
```

### 4. Run the linter

```bash
ruff check .
ruff format --check .
```

---

## Coding Standards

### Python style

- **Formatter:** `ruff format` (black-compatible, line length 100)
- **Linter:** `ruff check` — all rules in `pyproject.toml` must pass
- **Type hints:** required on all public functions
- **Docstrings:** required on all classes and public methods
- **No bare `except:`** — always specify the exception type

### SAP invariants

All contributions must preserve the following invariants — the test suite
checks these automatically:

1. **Posterior sums to 1.0** — `sum(posterior) == 1.0 ± 1e-5`
2. **Trap energy ∈ [0, 1]** — for all stages and all NSDT inputs
3. **Geometric constraint** — Stage 5 transitions are irreversible in `enforce_geometry()`
4. **Lyapunov V ≥ 0** — for all (entropy, energy, velocity) inputs
5. **Determinism** — identical NSDT inputs produce identical stage outputs

### The Numerical Constitution

Any code that modifies the SAP core (`sap_geometry_engine.py`,
`sap_constrained_bayesian.py`, `sap_lyapunov.py`) must:

- Not lower the stability guarantee (V thresholds must not increase)
- Not remove geometric transition constraints
- Include property-based tests (Hypothesis) for any new invariant

---

## Pull Request Process

### Branch naming

```
feat/short-description    # new feature
fix/issue-number-description  # bug fix
refactor/module-name      # refactoring
test/what-is-being-tested # adding tests
docs/section-name         # documentation only
```

### PR checklist

Before opening a PR, verify:

- [ ] `pytest tests/ -v` passes with no failures
- [ ] `ruff check . && ruff format --check .` passes
- [ ] New functionality has tests in `tests/`
- [ ] SAP invariants are not broken (run `tests/test_nsdt_clinical_trial.py`)
- [ ] Docstrings added/updated for all changed public APIs
- [ ] `CHANGELOG.md` entry added under `[Unreleased]`

### PR description template

```markdown
## Summary
Brief description of the change.

## SAP Stage Analysis
Which SAP stages does this change affect, and how?

## Numerical Constitution
Does this change affect the Lyapunov stability guarantees?
- [ ] No change to stability guarantees
- [ ] Stability guarantee improved (describe)
- [ ] Stability guarantee requires re-evaluation (explain)

## Tests Added
List the new tests and what invariant they verify.
```

### Review criteria

- PRs that break any SAP invariant will be declined without exception.
- PRs that reduce test coverage will be declined.
- The LuminarkLiveBridge's `govern()` contract (PASS/FAIL_REPAIRED/FAIL_EXHAUSTED)
  must remain backward-compatible.

---

## Running Individual Components

```bash
# Test the SAP Psychiatrist with a specific error
python -c "
from sap_stage_classifier import SAPPsychiatrist
p = SAPPsychiatrist()
d = p.diagnose_from_strings('ImportError', \"No module named 'numpy'\")
print(d)
"

# Test the Numerical Constitution
python -c "
from sap_lyapunov import NumericalConstitution
nc = NumericalConstitution()
report = nc.certify(entropy=2.1, energy=0.6, velocity=1.2)
print(report)
"

# Test the full governance loop (LOCAL mode — no Docker required)
python -c "
from luminark_live_bridge import LuminarkLiveBridge, ExecutionMode
bridge = LuminarkLiveBridge(execution_mode=ExecutionMode.LOCAL, max_iterations=2)
result = bridge.govern('print(1 + 1)')
print(result.summary())
"
```

---

## Project Structure

```
LuminarkCodeWriter/
├── sap_geometry_engine.py       # 10-stage SAP classification
├── sap_constrained_bayesian.py  # Bayesian posterior + trap energy
├── sap_lyapunov.py              # Lyapunov stability monitor
├── sap_stage_classifier.py      # SAP Psychiatrist
├── luminark_live_bridge.py      # Main orchestrator
├── Dockerfile                   # Sandbox definition
├── entrypoint.sh                # Resource-constrained execution
├── docker-compose.yml           # sandbox + redis services
├── pyproject.toml               # Dependencies and tooling
├── CONTRIBUTING.md              # This file
├── .gitignore
└── tests/
    └── test_nsdt_clinical_trial.py  # Clinical trial test suite
```

---

## Contact

**Meridian Axiom Alignment Technologies LLC (MAAT)**
**Founder & Chief Science Officer:** Richard Stanfield
**Email:** LuminarkMeridian@gmail.com
**Location:** St. Petersburg, FL

---

*LUMINARK™ and the Stanfield Axiom of Perpetuity (SAP) are proprietary intellectual
property of Richard Stanfield / MAAT. All rights reserved.*
