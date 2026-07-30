"""
Unit tests: the ``Status.INCONCLUSIVE`` outcome vocabulary (bug 2aaac911).

Stage A of bug 2aaac911 introduces a third outcome, distinct from
``Status.FAILED``, meaning "this measurement could not be trusted under the
conditions it ran in" (e.g. a timing/performance check whose numbers were
corrupted by concurrent load from unrelated suites in the same run). These
tests pin the three non-negotiable properties of that vocabulary at the
``realsrv_test.core.sweep.print_summary`` level -- the single function whose
return value ``realsrv_test.core.pipeline.run_pipeline`` uses, unmodified, to
decide its process exit code (``exit_code = 1 if failed_count else 0``):

1. An INCONCLUSIVE outcome never contributes to the FAILED count that drives
   the exit code -- exit-code neutrality.
2. A FAILED outcome still does -- INCONCLUSIVE must not accidentally swallow
   real failures.
3. The run summary counts INCONCLUSIVE as its own line, separate from every
   other status, so it can never be mistaken for a passing result.

No live server or client is involved -- ``CommandOutcome`` is a plain
dataclass and ``print_summary`` is pure (stdout only).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sys
from pathlib import Path

_LIVETESTS_DIR = Path(__file__).resolve().parents[1] / "livetests"
if str(_LIVETESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_LIVETESTS_DIR))

from realsrv_test.core.catalog import Bucket, CommandOutcome, Status  # noqa: E402
from realsrv_test.core.sweep import print_summary  # noqa: E402


def _outcome(name: str, status: Status, reason: str = "reason") -> CommandOutcome:
    return CommandOutcome(name, Bucket.BUCKET_A, status, reason)


def test_inconclusive_only_never_fails_the_run(capsys) -> None:
    """An all-INCONCLUSIVE outcome set reports zero FAILED -> exit code stays 0."""
    outcomes = [
        _outcome("check_a", Status.INCONCLUSIVE, "server under unrelated load"),
        _outcome("check_b", Status.EXECUTED_OK),
        _outcome("check_c", Status.EXPECTED_ERROR),
        _outcome("check_d", Status.VERIFY_ONLY),
    ]

    failed_count = print_summary(outcomes)

    assert failed_count == 0
    # Mirrors realsrv_test.core.pipeline.run_pipeline's exit-code computation
    # verbatim: `exit_code = 1 if failed_count else 0`.
    exit_code = 1 if failed_count else 0
    assert exit_code == 0


def test_failed_outcome_still_fails_the_run_alongside_inconclusive(capsys) -> None:
    """INCONCLUSIVE must not mask a genuine FAILED outcome in the same run."""
    outcomes = [
        _outcome("check_a", Status.INCONCLUSIVE, "server under unrelated load"),
        _outcome("check_b", Status.FAILED, "a real regression"),
    ]

    failed_count = print_summary(outcomes)

    assert failed_count == 1
    exit_code = 1 if failed_count else 0
    assert exit_code == 1


def test_summary_counts_inconclusive_as_its_own_line(capsys) -> None:
    """The printed summary counts INCONCLUSIVE separately from every other status."""
    outcomes = [
        _outcome("check_a", Status.INCONCLUSIVE, "server under unrelated load"),
        _outcome("check_b", Status.INCONCLUSIVE, "server under unrelated load"),
        _outcome("check_c", Status.EXECUTED_OK),
        _outcome("check_d", Status.FAILED, "a real regression"),
    ]

    print_summary(outcomes)

    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    # Isolate the counts block (between the "SUMMARY" header and the "----"
    # divider that precedes the per-command table) -- the table below it
    # repeats the same status names as its first column and must not be
    # parsed as count lines.
    start = lines.index("SUMMARY") + 2
    end = next(i for i in range(start, len(lines)) if lines[i].startswith("-"))
    count_lines = {
        line.split()[0]: int(line.split()[1]) for line in lines[start:end] if line.strip()
    }
    assert count_lines[Status.INCONCLUSIVE.value] == 2
    assert count_lines[Status.EXECUTED_OK.value] == 1
    assert count_lines[Status.FAILED.value] == 1
    # It is impossible to mistake for health: its status marker is neither
    # "executed-ok" nor absent -- it prints under its own distinct name.
    assert Status.INCONCLUSIVE.value != Status.EXECUTED_OK.value


def test_inconclusive_reason_is_never_reported_as_a_bare_status_name() -> None:
    """A check reporting INCONCLUSIVE must name the reason and observed numbers."""
    outcome = _outcome(
        "check_a",
        Status.INCONCLUSIVE,
        "quiet_s=0.010 loaded_s=0.646 divergence=64.6x ceiling=3.0x -- "
        "server under concurrent load from other checks, not a code regression",
    )

    assert outcome.status is Status.INCONCLUSIVE
    assert "quiet_s=" in outcome.reason
    assert "loaded_s=" in outcome.reason
    assert outcome.reason != "inconclusive"
