"""Offline eval CLI.

Free-tier chains run in REPORT mode by default: the score is printed, the gate never
fails CI, and the run exits 0. Set EVAL_MODE=enforce (or use a paid provider) to make
a score below EVAL_MIN_SCORE return exit code 1.
"""

import asyncio

from app.core.config import settings
from app.eval.runner import run_eval
from app.services.llm_client import get_llm_client


def _provider_is_paid() -> bool:
    """Anthropic is the only provider in this project that is paid-only end to end."""
    provider = (settings.LLM_PROVIDER or "").strip().lower()
    return provider == "anthropic" and bool((settings.ANTHROPIC_API_KEY or "").strip())


def _report_mode() -> bool:
    mode = (settings.EVAL_MODE or "auto").strip().lower()
    if mode == "report":
        return True
    if mode == "enforce":
        return False
    return not _provider_is_paid()


def main() -> int:
    llm = get_llm_client(role="writer")
    report = asyncio.run(run_eval(llm))
    threshold = settings.EVAL_MIN_SCORE

    for result in report.results:
        print(
            f"{result.benchmark.topic}: score={result.score} "
            f"passed={result.passed} issues={result.structure_issues}"
        )
    print(f"average_score={report.average_score:.2f} threshold={threshold:.2f}")

    if _report_mode():
        print(
            "NOTE: free-tier / report mode -> eval score is informational and does NOT fail CI. "
            "Set EVAL_MODE=enforce to gate on it (requires paid quota for reliable scores)."
        )
        return 0
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
