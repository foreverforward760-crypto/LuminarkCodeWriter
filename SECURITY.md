# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x     | ✅ Active  |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Please report security vulnerabilities by emailing:

**LuminarkMeridian@gmail.com**

Subject line: `[SECURITY] LuminarkCodeWriter — <brief description>`

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact assessment
- Any suggested mitigations

You will receive an acknowledgement within **48 hours** and a resolution
timeline within **7 days**.

---

## Sandbox Security Model

The LUMINARK governance sandbox (Docker container) is designed with
defence-in-depth:

### Container-level controls
- **Network isolation:** `--network none` — no inbound or outbound traffic
- **Memory limit:** `--memory 256m` — prevents memory exhaustion attacks
- **CPU limit:** `--cpus 0.5` — prevents CPU monopolisation
- **PID limit:** `--pids-limit 64` — prevents fork bombs
- **Read-only filesystem:** `--read-only` with tmpfs for `/tmp`
- **No new privileges:** `--security-opt no-new-privileges:true`
- **Non-root user:** all code runs as `luminark` (UID 1001)

### Process-level controls (entrypoint.sh ulimits)
- CPU time: 25 seconds hard limit (SIGKILL on breach)
- Virtual memory: 256 MB
- Open files: 64 descriptors
- Child processes: 32
- Core dump size: 0 (no crash dumps in sandbox)

### What the sandbox cannot do
- Access the network
- Write outside `/tmp` and `/workspace`
- Escalate privileges
- Persist state across executions
- Access host filesystem (read-only bind mount for task file only)

---

## Known Limitations

1. **LOCAL execution mode** (for development) does **not** apply container
   or ulimit constraints. Never use LOCAL mode in production.

2. The sandbox does not currently scan for GPU resource exhaustion. If
   GPU-accelerated code is submitted, use `--gpus none` in Docker flags.

3. The `_apply_surgical_repair()` heuristics in LOCAL mode add a comment
   to the repaired code. In DOCKER mode, the repaired code runs in a fresh
   container with no state from the previous run.

---

## Responsible Disclosure Timeline

- **T+0:** Vulnerability reported
- **T+48h:** Acknowledgement sent
- **T+7d:** Resolution timeline communicated
- **T+30d:** Fix released (or compensating control documented)
- **T+90d:** Public disclosure (coordinated with reporter)

© 2026 Meridian Axiom Alignment Technologies LLC
