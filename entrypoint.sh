#!/bin/bash
# entrypoint.sh – LUMINARK Sandbox Resource Constraints
# Applied before every code execution in the Crucible.
#
# Resource limits (ulimits):
#   CPU time    : 25 seconds hard limit (prevents infinite loops)
#   File size   : 10 MB max file write (prevents disk exhaustion)
#   Open files  : 64 max file descriptors (prevents resource leaks)
#   Processes   : 32 max child processes (prevents fork bombs)
#   Core dumps  : 0 (no core files in the sandbox)
#
# NOTE: Virtual memory (ulimit -v) is intentionally NOT set here.
# Docker's --memory flag enforces container-level memory limits via cgroups,
# which is the correct mechanism. Setting ulimit -v inside the container
# constrains the shell's own address space and causes fork failures on
# GitHub Actions runners where the kernel maps large address ranges by default.
#
# These complement Docker's --memory and --cpus flags:
#   Docker enforces cgroup-level limits (container level)
#   ulimits enforce per-process limits (additional layer)

set -euo pipefail

# ── Apply ulimits ─────────────────────────────────────────────────────────────

# CPU time: 25 seconds (SIGXCPU on soft limit, SIGKILL on hard limit)
ulimit -t 25

# Maximum file size: 10 MB
ulimit -f $((10 * 1024))

# Open file descriptors
ulimit -n 64

# Maximum user processes
ulimit -u 32

# Core file size: 0 (no dumps)
ulimit -c 0

# ── Log constraints (visible in container logs) ───────────────────────────────

echo "[LUMINARK SANDBOX] Resource constraints applied:"
echo "  CPU time:    $(ulimit -t)s"
echo "  Max files:   $(ulimit -n)"
echo "  Max procs:   $(ulimit -u)"
echo "[LUMINARK SANDBOX] Executing: $*"
echo "---"

# ── Execute ───────────────────────────────────────────────────────────────────

exec "$@"
