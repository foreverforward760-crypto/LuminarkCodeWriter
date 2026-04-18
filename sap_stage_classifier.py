"""
sap_stage_classifier.py – SAP Stage Classifier ("The SAP Psychiatrist")
LUMINARK Active Governance Layer

Maps Python execution errors, test failures, and static analysis violations
to their corresponding SAP stage diagnosis. For each diagnosis the Psychiatrist
generates a "Surgical Prompt" — a targeted instruction to repair the code
while preserving stability.

The SAP Psychiatrist is the intelligence layer between the Lyapunov stability
monitor and the LuminarkLiveBridge orchestrator. When the Numerical Constitution
fails, the Psychiatrist determines WHY the system is unstable and prescribes
a specific, minimal intervention.

Error→Stage mapping rationale:
  Stage 0 — Void / Missing: ImportError, ModuleNotFoundError, AttributeError (missing)
  Stage 1 — Spark / Init:   NameError, UnboundLocalError
  Stage 2 — Vessel / Type:  TypeError, ValueError (type mismatch)
  Stage 3 — Engine / Logic: AssertionError, LogicError, wrong output
  Stage 4 — Crucible / Edge:IndexError, KeyError, boundary violations
  Stage 5 — Threshold:      RecursionError, infinite loop, timeout
  Stage 6 — Nexus / IO:     IOError, FileNotFoundError, PermissionError
  Stage 7 — Lens / Concurr: RuntimeError, thread/async errors, race conditions
  Stage 8 — False Hell:     Silent wrong result (no exception, wrong output)
  Stage 9 — Transparency:   SystemExit, MemoryError, critical resource exhaustion
"""

import re
from dataclasses import dataclass

# ── Diagnosis dataclass ───────────────────────────────────────────────────────


@dataclass
class SAPDiagnosis:
    """Result of the SAP Psychiatrist's analysis."""

    stage: int
    stage_name: str
    error_class: str
    error_message: str
    surgical_prompt: str
    confidence: float
    urgency: str  # LOW | MODERATE | HIGH | CRITICAL

    def __str__(self) -> str:
        return (
            f"[SAP Stage {self.stage} – {self.stage_name}] "
            f"{self.error_class}: {self.error_message[:80]}\n"
            f"  Urgency: {self.urgency} | Confidence: {self.confidence:.0%}\n"
            f"  Surgical Prompt: {self.surgical_prompt}"
        )


# ── Error pattern registry ────────────────────────────────────────────────────

_STAGE_PATTERNS: list[dict] = [
    # Stage 9 first — most critical, must be checked before generic RuntimeError
    {
        "stage": 9,
        "stage_name": "The Transparency",
        "patterns": [
            "MemoryError",
            "SystemExit",
            "OverflowError",
            "RecursionError.*maximum recursion",
        ],
        "urgency": "CRITICAL",
        "surgical_template": (
            "CRITICAL RESOURCE FAILURE detected ({error_class}). "
            "The function has exceeded its operational boundary. "
            "Rewrite {function_hint} to add explicit resource guards: "
            "cap recursion depth, add memory-efficient data structures, "
            "or split the operation into bounded sub-tasks."
        ),
    },
    {
        "stage": 8,
        "stage_name": "The Vessel of Grounding",
        "patterns": [
            "AssertionError.*wrong.*value",
            "wrong output",
            "expected.*got",
            "assert.*==.*False",
        ],
        "urgency": "HIGH",
        "surgical_template": (
            "SILENT FAILURE (Stage 8 False Hell) detected in {function_hint}. "
            "The code runs without raising an exception but produces the wrong result. "
            "This is the most dangerous failure mode. "
            "Add explicit output validation after the computation: "
            "assert the shape, dtype, range, or invariant that must hold. "
            "Then trace backward from the assertion failure to the root cause."
        ),
    },
    {
        "stage": 7,
        "stage_name": "The Lens",
        "patterns": [
            "RuntimeError",
            "concurrent",
            "asyncio",
            "ThreadError",
            "DeadlockError",
            "race condition",
        ],
        "urgency": "HIGH",
        "surgical_template": (
            "RUNTIME / CONCURRENCY FAILURE (Stage 7) in {function_hint}: {error_message}. "
            "Isolate the async or threaded section. "
            "Add a lock or ensure the function is called from a single context. "
            "If using asyncio, verify all awaits are correctly placed."
        ),
    },
    {
        "stage": 6,
        "stage_name": "The Nexus",
        "patterns": [
            "IOError",
            "FileNotFoundError",
            "PermissionError",
            "OSError",
            "ConnectionError",
            "TimeoutError",
        ],
        "urgency": "MODERATE",
        "surgical_template": (
            "I/O FAILURE (Stage 6) in {function_hint}: {error_message}. "
            "Wrap the I/O operation in a try/except block. "
            "Add a fallback path (default value, cached result, or graceful degradation). "
            "Verify file paths are relative to the project root, not the caller's CWD."
        ),
    },
    {
        "stage": 5,
        "stage_name": "The Dynamo",
        "patterns": [
            "RecursionError",
            "TimeoutExpired",
            "infinite loop",
            "maximum recursion depth",
            "took too long",
        ],
        "urgency": "HIGH",
        "surgical_template": (
            "THRESHOLD BREACH (Stage 5) in {function_hint}: {error_message}. "
            "Add a base case or iteration limit. "
            "Replace unbounded recursion with explicit stack management or memoisation. "
            "Add a circuit-breaker counter: if iterations > N, return a safe default."
        ),
    },
    {
        "stage": 4,
        "stage_name": "The Crucible",
        "patterns": [
            "IndexError",
            "KeyError",
            "StopIteration",
            "out of.*bound",
            "list index out of range",
        ],
        "urgency": "MODERATE",
        "surgical_template": (
            "BOUNDARY VIOLATION (Stage 4) in {function_hint}: {error_message}. "
            "Guard the access: check `if key in dict` before subscripting, "
            "use `list[i] if i < len(list) else default`, "
            "or use `.get(key, default)` for dicts. "
            "Add an explicit length/bounds assertion at the function entry."
        ),
    },
    {
        "stage": 3,
        "stage_name": "The Engine",
        "patterns": [
            "AssertionError",
            "wrong.*result",
            "logic error",
            "unexpected.*value",
            "ZeroDivisionError",
        ],
        "urgency": "MODERATE",
        "surgical_template": (
            "LOGIC FAILURE (Stage 3) in {function_hint}: {error_message}. "
            "The algorithm's intermediate state is incorrect. "
            "Add logging/print for all intermediate variables. "
            "Step through the computation manually for the failing input. "
            "Check all conditionals — a missing `not` or `≤` vs `<` is common here."
        ),
    },
    {
        "stage": 2,
        "stage_name": "The Vessel",
        "patterns": [
            "TypeError",
            "ValueError",
            "cannot.*convert",
            "unsupported operand",
            "invalid literal",
        ],
        "urgency": "MODERATE",
        "surgical_template": (
            "TYPE / VALUE MISMATCH (Stage 2) in {function_hint}: {error_message}. "
            "Add explicit type casting at the function boundary: `int(x)`, `str(x)`, `float(x)`. "
            "Add Pydantic validation or a type annotation with runtime checking. "
            "Ensure the caller is not passing None where a value is required."
        ),
    },
    {
        "stage": 1,
        "stage_name": "The Spark",
        "patterns": [
            "NameError",
            "UnboundLocalError",
            "not defined",
            "referenced before assignment",
        ],
        "urgency": "LOW",
        "surgical_template": (
            "UNBOUND NAME (Stage 1) in {function_hint}: {error_message}. "
            "The variable `{name_hint}` is used before it is assigned. "
            "Move the initialisation above the first use, or add a default: "
            "`{name_hint} = None` at the top of the function. "
            "Check for typos in variable names."
        ),
    },
    {
        "stage": 0,
        "stage_name": "Plenara",
        "patterns": [
            "ImportError",
            "ModuleNotFoundError",
            "AttributeError",
            "cannot import",
            "No module named",
            "has no attribute",
        ],
        "urgency": "LOW",
        "surgical_template": (
            "MISSING DEPENDENCY (Stage 0) in {function_hint}: {error_message}. "
            "Add the missing import or install the package: `pip install {module_hint}`. "
            "Check the module path is correct relative to the project root. "
            "If this is an attribute error, verify the object type before accessing."
        ),
    },
]


# ── SAP Psychiatrist ──────────────────────────────────────────────────────────


class SAPPsychiatrist:
    """
    The SAP Psychiatrist analyses execution failures and maps them to
    SAP stages, then generates Surgical Prompts for the LuminarkLiveBridge.

    Usage:
        psychiatrist = SAPPsychiatrist()
        diagnosis = psychiatrist.diagnose(error, traceback_str, function_name)
        print(diagnosis.surgical_prompt)
    """

    def __init__(self):
        self._patterns = _STAGE_PATTERNS

    def diagnose(
        self,
        error: Exception,
        traceback_str: str = "",
        function_name: str = "unknown_function",
        source_code: str = "",
    ) -> SAPDiagnosis:
        """
        Diagnose a code failure and return a SAPDiagnosis with surgical prompt.

        Parameters
        ----------
        error          : the caught exception
        traceback_str  : full traceback text
        function_name  : name of the failing function (for the prompt)
        source_code    : snippet of the failing code (for context)
        """
        error_class = type(error).__name__
        error_message = str(error)
        combined = f"{error_class} {error_message} {traceback_str}"

        stage_entry, confidence = self._match_stage(combined)

        # Extract hints from traceback
        name_hint = self._extract_name_hint(error_message)
        module_hint = self._extract_module_hint(error_message)

        surgical_prompt = stage_entry["surgical_template"].format(
            error_class=error_class,
            error_message=error_message[:120],
            function_hint=function_name,
            name_hint=name_hint,
            module_hint=module_hint,
        )

        return SAPDiagnosis(
            stage=stage_entry["stage"],
            stage_name=stage_entry["stage_name"],
            error_class=error_class,
            error_message=error_message,
            surgical_prompt=surgical_prompt,
            confidence=confidence,
            urgency=stage_entry["urgency"],
        )

    def diagnose_from_strings(
        self, error_class: str, error_message: str, function_name: str = "unknown_function"
    ) -> SAPDiagnosis:
        """
        Diagnose from string representations (useful for test output parsing).
        """
        combined = f"{error_class} {error_message}"
        stage_entry, confidence = self._match_stage(combined)
        name_hint = self._extract_name_hint(error_message)
        module_hint = self._extract_module_hint(error_message)

        surgical_prompt = stage_entry["surgical_template"].format(
            error_class=error_class,
            error_message=error_message[:120],
            function_hint=function_name,
            name_hint=name_hint,
            module_hint=module_hint,
        )

        return SAPDiagnosis(
            stage=stage_entry["stage"],
            stage_name=stage_entry["stage_name"],
            error_class=error_class,
            error_message=error_message,
            surgical_prompt=surgical_prompt,
            confidence=confidence,
            urgency=stage_entry["urgency"],
        )

    def _match_stage(self, text: str) -> tuple[dict, float]:
        """Find the best-matching stage entry for the given error text."""
        text_lower = text.lower()
        for entry in self._patterns:
            for pattern in entry["patterns"]:
                if re.search(pattern.lower(), text_lower):
                    return entry, 0.90
        # Default: Stage 3 (logic error — unknown cause)
        return _STAGE_PATTERNS[6], 0.50  # index 6 = Stage 3 in the list

    @staticmethod
    def _extract_name_hint(error_message: str) -> str:
        match = re.search(r"name '(\w+)'", error_message)
        if match:
            return match.group(1)
        match = re.search(r"'(\w+)' is not defined", error_message)
        if match:
            return match.group(1)
        return "variable_name"

    @staticmethod
    def _extract_module_hint(error_message: str) -> str:
        match = re.search(r"No module named '([^']+)'", error_message)
        if match:
            return match.group(1)
        match = re.search(r"cannot import name '([^']+)'", error_message)
        if match:
            return match.group(1)
        return "package_name"

    def batch_diagnose(self, failures: list[dict]) -> list[SAPDiagnosis]:
        """
        Diagnose a batch of failures from test output.
        Each item: {"error_class": str, "error_message": str, "function": str}
        """
        return [
            self.diagnose_from_strings(
                f.get("error_class", "UnknownError"),
                f.get("error_message", ""),
                f.get("function", "unknown"),
            )
            for f in failures
        ]
