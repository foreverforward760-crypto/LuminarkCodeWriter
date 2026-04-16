#!/usr/bin/env python3
"""
luminark_gate.py – LUMINARK Active Governance Gate
CLI entry point for the governance layer.

Usage:
    # Govern a Python file
    python luminark_gate.py govern path/to/code.py

    # Quick SAP stage report (no repair loop)
    python luminark_gate.py report path/to/code.py

    # Run the full clinical trial suite
    python luminark_gate.py test

    # Print system status
    python luminark_gate.py status

    # Govern inline code from stdin
    echo "print(2+2)" | python luminark_gate.py govern -

Exit codes:
    0  — PASS (code passed governance)
    1  — FAIL_EXHAUSTED or EXECUTION_ERROR
    2  — FAIL_REPAIRED (passed after repair — review recommended)
    3  — Usage error
"""

import sys
import os
import json
import argparse
import subprocess
import logging

# Allow both package and root-level imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.WARNING,   # quiet by default; use --verbose to see detail
    format="%(asctime)s [%(levelname)s] %(message)s"
)


def _get_bridge(mode: str = "local", max_iter: int = 3,
                threshold: float = 3.0, timeout: int = 30):
    """Import and construct LuminarkLiveBridge (root or package)."""
    try:
        from luminark.luminark_live_bridge import (
            LuminarkLiveBridge, ExecutionMode
        )
    except ImportError:
        from luminark_live_bridge import LuminarkLiveBridge, ExecutionMode

    exec_mode = ExecutionMode.DOCKER if mode == "docker" else ExecutionMode.LOCAL
    return LuminarkLiveBridge(
        execution_mode=exec_mode,
        max_iterations=max_iter,
        stability_threshold=threshold,
        sandbox_timeout=timeout,
    )


def cmd_govern(args) -> int:
    """Run the full governance loop on a file or stdin."""
    if args.path == "-":
        code = sys.stdin.read()
        source = "stdin"
    else:
        try:
            with open(args.path) as f:
                code = f.read()
            source = args.path
        except FileNotFoundError:
            print(f"❌ File not found: {args.path}", file=sys.stderr)
            return 3

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    bridge = _get_bridge(
        mode=args.mode,
        max_iter=args.max_iterations,
        threshold=args.threshold,
        timeout=args.timeout,
    )

    print(f"[LUMINARK GATE] Governing: {source}")
    result = bridge.govern(code, task_description=source)

    if args.json:
        out = {
            "verdict":      result.verdict.value,
            "iterations":   result.iterations,
            "elapsed_s":    result.total_elapsed_s,
            "audit_trail":  result.audit_trail,
            "diagnoses":    [
                {"stage": d.stage, "stage_name": d.stage_name,
                 "urgency": d.urgency, "surgical_prompt": d.surgical_prompt}
                for d in result.diagnoses
            ],
        }
        print(json.dumps(out, indent=2))
    else:
        print(result.summary())
        if result.diagnoses:
            print("\nSurgical Prompts:")
            for d in result.diagnoses:
                print(f"  [Stage {d.stage} – {d.stage_name}] {d.urgency}")
                print(f"    {d.surgical_prompt[:120]}...")

    # Exit codes
    from luminark_live_bridge import GovernanceVerdict
    if result.verdict == GovernanceVerdict.PASS:
        return 0
    if result.verdict == GovernanceVerdict.FAIL_REPAIRED:
        return 2
    return 1


def cmd_report(args) -> int:
    """Quick SAP stage report without the full governance loop."""
    if args.path == "-":
        code = sys.stdin.read()
    else:
        try:
            with open(args.path) as f:
                code = f.read()
        except FileNotFoundError:
            print(f"❌ File not found: {args.path}", file=sys.stderr)
            return 3

    bridge = _get_bridge(mode=args.mode)
    report = bridge.get_stage_report(code)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        status = "✅ STABLE" if report["passed"] else "❌ UNSTABLE"
        print(f"{status} | Stage {report['sap_stage']} – {report['stage_name']}")
        print(f"  V={report['V']:.4f} | action={report['action']}")
        print(f"  {report['message']}")

    return 0 if report["passed"] else 1


def cmd_test(args) -> int:
    """Run the full clinical trial suite."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )
    return result.returncode


def cmd_status(args) -> int:
    """Print system component status."""
    print("LUMINARK Active Governance Layer — System Status")
    print("=" * 50)

    # Check imports
    components = [
        ("sap_geometry_engine",      "SAPGeometry"),
        ("sap_constrained_bayesian", "SAPConstrainedBayesian"),
        ("sap_lyapunov",             "LyapunovController"),
        ("sap_stage_classifier",     "SAPPsychiatrist"),
        ("luminark_live_bridge",     "LuminarkLiveBridge"),
    ]

    all_ok = True
    for module, cls in components:
        try:
            mod = __import__(module)
            getattr(mod, cls)
            print(f"  ✅ {module}.{cls}")
        except (ImportError, AttributeError) as e:
            print(f"  ❌ {module}.{cls}: {e}")
            all_ok = False

    # Check Docker
    docker_ok = subprocess.run(
        ["docker", "info"], capture_output=True
    ).returncode == 0
    print(f"  {'✅' if docker_ok else '⚠️ '} Docker: {'available' if docker_ok else 'not available (LOCAL mode only)'}")

    # Check sandbox image
    if docker_ok:
        img_ok = subprocess.run(
            ["docker", "image", "inspect", "luminark-sandbox:latest"],
            capture_output=True
        ).returncode == 0
        print(f"  {'✅' if img_ok else '⚠️ '} luminark-sandbox:latest: {'built' if img_ok else 'not built — run: make build'}")

    print()
    print("  Overall:", "✅ Ready" if all_ok else "❌ Issues detected — run: make install")
    return 0 if all_ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="luminark_gate",
        description="LUMINARK Active Governance Gate",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--json", "-j", action="store_true",
                        help="Output JSON instead of human-readable text")

    sub = parser.add_subparsers(dest="command", required=True)

    # govern
    p_govern = sub.add_parser("govern", help="Run full governance loop on a file")
    p_govern.add_argument("path", help="Python file to govern (- for stdin)")
    p_govern.add_argument("--mode", default="local", choices=["docker", "local"])
    p_govern.add_argument("--max-iterations", type=int, default=3)
    p_govern.add_argument("--threshold", type=float, default=3.0)
    p_govern.add_argument("--timeout", type=int, default=30)

    # report
    p_report = sub.add_parser("report", help="Quick SAP stage report")
    p_report.add_argument("path", help="Python file to report on (- for stdin)")
    p_report.add_argument("--mode", default="local", choices=["docker", "local"])

    # test
    sub.add_parser("test", help="Run clinical trial test suite")

    # status
    sub.add_parser("status", help="Print system component status")

    args = parser.parse_args()

    dispatch = {
        "govern": cmd_govern,
        "report": cmd_report,
        "test":   cmd_test,
        "status": cmd_status,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
