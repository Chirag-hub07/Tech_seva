"""Shared CLI error handling: one-line, sanitised messages; no tracebacks, IDs, dates or paths."""

from __future__ import annotations

import sys

from exacerbalert_ml.exclusions import AuditInputError
from exacerbalert_ml.features import LeakageError
from exacerbalert_ml.runner import RunError
from exacerbalert_ml.splits import SplitError
from verify_temporal import EXIT_ERROR, error_report, sanitize

KNOWN = ((AuditInputError, "audit_inputs"), (SplitError, "validation_design"),
         (LeakageError, "leakage_guard"), (RunError, "refused"))


def run_safely(fn, args, ids_holder) -> int:
    try:
        return fn(args)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("ERROR [interrupted]: stopped by the user.", file=sys.stderr)
        return EXIT_ERROR
    except BaseException as exc:  # noqa: BLE001 - every failure is reported safely
        ids = getattr(ids_holder, "ids", ())
        for cls, cat in KNOWN:
            if isinstance(exc, cls):
                print(f"ERROR [{cat}]: {sanitize(exc, ids)}", file=sys.stderr)
                return EXIT_ERROR
        category, message = error_report(exc, ids)
        print(f"ERROR [{category}]: {message}", file=sys.stderr)
        return EXIT_ERROR
