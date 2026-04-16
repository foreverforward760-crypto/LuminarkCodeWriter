---
name: Bug Report
about: Report a failure in the LUMINARK governance layer
title: "[BUG] "
labels: ["bug", "needs-triage"]
assignees: []
---

## SAP Stage Diagnosis

Which SAP stage does this bug most closely resemble?

- [ ] Stage 0 – Plenara (missing dependency / import failure)
- [ ] Stage 1 – The Spark (unbound name)
- [ ] Stage 2 – The Vessel (type mismatch)
- [ ] Stage 3 – The Engine (logic error / wrong output)
- [ ] Stage 4 – The Crucible (boundary violation)
- [ ] Stage 5 – The Dynamo (recursion / timeout)
- [ ] Stage 6 – The Nexus (I/O / file error)
- [ ] Stage 7 – The Lens (runtime / concurrency)
- [ ] Stage 8 – The Vessel of Grounding (silent wrong result)
- [ ] Stage 9 – The Transparency (critical resource exhaustion)
- [ ] Unknown

## Description

A clear description of the bug.

## Steps to Reproduce

```python
# Minimal code that triggers the bug
```

1.
2.
3.

## Expected Behavior

What should happen (including expected SAP verdict and Lyapunov V value).

## Actual Behavior

What actually happens. Include the full error message and traceback.

## Governance Output

```
# Paste the output of: python luminark_gate.py govern <file> --verbose
```

## Environment

- OS:
- Python version:
- LUMINARK version:
- Execution mode: [ ] Docker [ ] Local
- Docker version (if applicable):

## Lyapunov V at time of failure

If available: V = _____, action = _____, stage = _____

## Additional Context

Any other context, logs, or screenshots.
