"""
main.py – LUMINARK Live Bridge FastAPI Service

HTTP API layer wrapping the LuminarkLiveBridge governance orchestrator.
Adds Redis telemetry for:
  - Lyapunov V-series storage (dV/dt monitoring)
  - Stage history per context
  - Full audit trail persistence
  - Latest governance verdict per context

Endpoints:
  POST /govern          — run full governance loop on submitted code
  POST /stage-report    — quick SAP stage check (no governance loop)
  GET  /telemetry/{id}  — retrieve stored V-series + stage history for a context
  GET  /health          — liveness check

Environment variables:
  REDIS_URL             — Redis connection string (default: redis://redis:6379)
  LUMINARK_DOCKER_IMAGE — sandbox image name (default: luminark-sandbox:latest)
  LUMINARK_MAX_ITERATIONS — max repair iterations (default: 3)
  LUMINARK_MODE         — "docker" | "local" (default: docker)
  LUMINARK_STABILITY_THRESHOLD — Lyapunov V threshold (default: 3.0)

Start:
  uvicorn main:app --host 0.0.0.0 --port 8080
"""

import json
import logging
import os
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from luminark_live_bridge import (
    ExecutionMode,
    LuminarkLiveBridge,
)

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# ── Configuration from environment ────────────────────────────────────────────

REDIS_URL           = os.getenv("REDIS_URL",             "redis://redis:6379")
DOCKER_IMAGE        = os.getenv("LUMINARK_DOCKER_IMAGE", "luminark-sandbox:latest")
MAX_ITERATIONS      = int(os.getenv("LUMINARK_MAX_ITERATIONS", "3"))
EXEC_MODE           = os.getenv("LUMINARK_MODE",         "docker")
STABILITY_THRESHOLD = float(os.getenv("LUMINARK_STABILITY_THRESHOLD", "3.0"))

# Redis key prefixes
_KEY_V_SERIES    = "luminark:v_series:{ctx}"        # list of floats
_KEY_STAGE_SEQ   = "luminark:stage_seq:{ctx}"       # list of ints
_KEY_AUDIT       = "luminark:audit:{ctx}"            # list of JSON strings
_KEY_LATEST      = "luminark:latest:{ctx}"           # JSON of latest result
_KEY_VERDICT_CTR = "luminark:verdicts:{verdict}"     # global counters

# ── Redis client ──────────────────────────────────────────────────────────────

def _get_redis() -> redis.Redis:
    """Return a Redis client. Raises RuntimeError if Redis is unavailable."""
    try:
        r = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=3)
        r.ping()
        return r
    except Exception as exc:
        logger.warning(f"Redis unavailable ({exc}) — telemetry will be skipped")
        return None


# ── Bridge singleton ──────────────────────────────────────────────────────────

_bridge: LuminarkLiveBridge | None = None


def _get_bridge() -> LuminarkLiveBridge:
    global _bridge
    if _bridge is None:
        mode = ExecutionMode.DOCKER if EXEC_MODE == "docker" else ExecutionMode.LOCAL
        _bridge = LuminarkLiveBridge(
            execution_mode      = mode,
            max_iterations      = MAX_ITERATIONS,
            docker_image        = DOCKER_IMAGE,
            stability_threshold = STABILITY_THRESHOLD,
        )
        logger.info(f"LuminarkLiveBridge singleton created | mode={mode.value}")
    return _bridge


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("LUMINARK Bridge starting up — warming bridge and Redis connection")
    _get_bridge()
    _get_redis()
    yield
    logger.info("LUMINARK Bridge shutting down")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "LUMINARK Live Bridge",
    description = (
        "SAP-governed code execution service. Runs code in an isolated sandbox, "
        "evaluates Lyapunov stability, and iteratively repairs failures via the "
        "SAPPsychiatrist. Stores full telemetry in Redis."
    ),
    version     = "1.0.0",
    lifespan    = lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins  = ["*"],
    allow_methods  = ["*"],
    allow_headers  = ["*"],
)


# ── Request / Response models ─────────────────────────────────────────────────

class GovernRequest(BaseModel):
    code:             str  = Field(..., description="Python source code to govern")
    task_description: str  = Field("",  description="Human-readable task description")
    context_id:       str  = Field("default", description="ID for telemetry grouping")
    prev_stage:       int | None = Field(None, ge=0, le=9)


class StageReportRequest(BaseModel):
    code:       str = Field(..., description="Python source code to classify")
    context_id: str = Field("default")


# ── Telemetry helper ──────────────────────────────────────────────────────────

def _persist_telemetry(r: redis.Redis | None, context_id: str, result_dict: dict):
    """
    Write governance result to Redis.

    Storage layout:
      luminark:v_series:{ctx}    — RPUSH each V value (for dV/dt plotting)
      luminark:stage_seq:{ctx}   — RPUSH each stage value
      luminark:audit:{ctx}       — RPUSH full JSON result per run
      luminark:latest:{ctx}      — SET latest result (overwrite)
      luminark:verdicts:{verdict} — INCR global counter
    """
    if r is None:
        return

    try:
        ctx = context_id

        # V-series: one entry per governance iteration
        for v in result_dict.get("v_history", []):
            r.rpush(_KEY_V_SERIES.format(ctx=ctx), v)

        # Stage sequence
        for s in result_dict.get("stage_history", []):
            r.rpush(_KEY_STAGE_SEQ.format(ctx=ctx), s)

        # Full audit — store last 100 runs per context
        r.rpush(_KEY_AUDIT.format(ctx=ctx), json.dumps(result_dict))
        r.ltrim(_KEY_AUDIT.format(ctx=ctx), -100, -1)

        # Latest result (quick dashboard lookup)
        r.set(_KEY_LATEST.format(ctx=ctx), json.dumps(result_dict))

        # Global verdict counters
        r.incr(_KEY_VERDICT_CTR.format(verdict=result_dict.get("verdict", "UNKNOWN")))

    except Exception as exc:
        logger.warning(f"Telemetry write failed for context '{context_id}': {exc}")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/govern")
def govern(request: GovernRequest):
    """
    Run the full LUMINARK governance loop on submitted code.

    1. Execute code in the sandbox (Docker or LOCAL).
    2. Extract NSDT vector from execution behaviour.
    3. Evaluate Lyapunov stability (Numerical Constitution).
    4. If FAIL: SAPPsychiatrist generates a Surgical Prompt.
    5. Repair and retry up to max_iterations.
    6. Persist full telemetry to Redis.
    7. Return GovernanceResult as JSON.
    """
    bridge = _get_bridge()
    r      = _get_redis()

    try:
        result = bridge.govern(
            code             = request.code,
            task_description = request.task_description,
            prev_stage       = request.prev_stage,
        )
    except Exception as exc:
        logger.error(f"Bridge govern() raised: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Governance error: {exc}") from exc

    result_dict = result.to_dict()
    _persist_telemetry(r, request.context_id, result_dict)

    # dV/dt summary for the response
    v_hist = result.v_history
    dv_dt  = None
    if len(v_hist) >= 2:
        dv_dt = round(v_hist[-1] - v_hist[0], 4)

    return {
        **result_dict,
        "context_id":    request.context_id,
        "dv_dt_overall": dv_dt,
        "telemetry_stored": r is not None,
    }


@app.post("/stage-report")
def stage_report(request: StageReportRequest):
    """
    Quick SAP stage classification — no full governance loop.
    Useful for dashboard / monitoring use without execution overhead.
    """
    bridge = _get_bridge()
    try:
        report = bridge.get_stage_report(request.code)
    except Exception as exc:
        logger.error(f"stage_report error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Stage report error: {exc}") from exc

    return {
        "context_id": request.context_id,
        **report,
    }


@app.get("/telemetry/{context_id}")
def get_telemetry(context_id: str, limit: int = 50):
    """
    Retrieve stored Lyapunov V-series and stage history for a context ID.

    Returns:
      v_series      — last `limit` V values (for dV/dt plotting)
      stage_sequence — last `limit` SAP stage values
      latest        — most recent full governance result
      run_count     — total runs stored for this context
    """
    r = _get_redis()
    if r is None:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    try:
        ctx = context_id
        v_raw    = r.lrange(_KEY_V_SERIES.format(ctx=ctx), -limit, -1)
        s_raw    = r.lrange(_KEY_STAGE_SEQ.format(ctx=ctx), -limit, -1)
        latest_s = r.get(_KEY_LATEST.format(ctx=ctx))
        run_count = r.llen(_KEY_AUDIT.format(ctx=ctx))

        v_series       = [float(v) for v in v_raw]
        stage_sequence = [int(s) for s in s_raw]

        # dV/dt: slope across the stored V-series
        dv_dt = None
        if len(v_series) >= 2:
            dv_dt = round(v_series[-1] - v_series[0], 4)

        # Flag any dV > 0 windows (instability events)
        instability_events = [
            {"index": i + 1, "dV": round(v_series[i + 1] - v_series[i], 4)}
            for i in range(len(v_series) - 1)
            if v_series[i + 1] > v_series[i]
        ]

        return {
            "context_id":        context_id,
            "v_series":          v_series,
            "stage_sequence":    stage_sequence,
            "dv_dt_overall":     dv_dt,
            "instability_events": instability_events,
            "run_count":         run_count,
            "latest":            json.loads(latest_s) if latest_s else None,
        }
    except Exception as exc:
        logger.error(f"Telemetry read failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Telemetry read error: {exc}") from exc


@app.get("/health")
def health():
    """Liveness check — confirms bridge and Redis status."""
    r      = _get_redis()
    _get_bridge()
    return {
        "status":       "ok",
        "service":      "LUMINARK Live Bridge",
        "version":      "1.0.0",
        "exec_mode":    EXEC_MODE,
        "max_iterations": MAX_ITERATIONS,
        "stability_threshold": STABILITY_THRESHOLD,
        "redis":        "connected" if r is not None else "unavailable",
        "bridge":       "ready",
    }
