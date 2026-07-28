"""
CLI entry point for the realsrv-test live acceptance pipeline.

Console-script: ``realsrv-test`` (defined in livetests/pyproject.toml).

With no arguments, runs ALL suites sequentially against the live server and
exits non-zero on any FAILED outcome or teardown error.

Options
-------
--host HOST         Server host (default: 192.168.254.26).
--port PORT         Server port (default: 15010).
--cert PATH         Path to the client certificate (mTLS).  Required unless
                    --list is given.
--key PATH          Path to the client private key (mTLS).  Required unless
                    --list is given.
--ca PATH           Path to the CA certificate.  Required unless --list is given.
--project-prefix P  Prefix for the disposable project name (default: verify_live).
--keep-project      Skip teardown for post-run debugging.
--list              List available suite names and exit.
[suite ...]         Run only the named suites (subset run).

Certificate recipe (mint a disposable mTLS identity):

    openssl genrsa -out verifier.key 2048
    openssl req -new -key verifier.key -out verifier.csr \\
        -subj "/C=UA/ST=Kyiv/L=Kyiv/O=MCP-Proxy/OU=Client/CN=code-analysis-client-verifier-client"
    openssl x509 -req -in verifier.csr \\
        -CA mtls_certificates/mtls_certificates/ca/ca.crt \\
        -CAkey mtls_certificates/mtls_certificates/ca/ca.key \\
        -CAcreateserial -out verifier.crt -days 30 \\
        -extensions v3_client -extfile <(printf \\
        '[v3_client]\\nbasicConstraints=CA:FALSE\\nkeyUsage=critical,digitalSignature,keyEncipherment\\nextendedKeyUsage=clientAuth\\nsubjectAltName=@alt_names\\n[alt_names]\\nDNS.1=code-analysis-client-verifier-client\\nDNS.2=code-analysis-client-verifier.local\\n')

Never commit verifier.key / verifier.crt to git; delete them after the run.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Sequence

import realsrv_test._bootstrap  # noqa: F401 — must run before any scripts/ import

from realsrv_test.suites import list_suites
from _verify_client_all_commands_sweep import print_summary
from _verify_client_all_commands_fixtures import seed_fixtures
from _verify_client_all_commands_sweep import run_sweep
from _verify_client_all_commands_teardown import teardown_fixtures

from code_analysis_client import CodeAnalysisAsyncClient


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser.

    Returns:
        Configured :class:`argparse.ArgumentParser`.
    """
    parser = argparse.ArgumentParser(
        prog="realsrv-test",
        description=(
            "Live-server acceptance pipeline for code-analysis-server.\n"
            "Runs ALL suites by default; pass suite names to run a subset.\n"
            "See --list for available suite names."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--host",
        default="192.168.254.26",
        help="Server host (default: %(default)s).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=15010,
        help="Server port (default: %(default)s).",
    )
    parser.add_argument(
        "--cert",
        default=None,
        help="Path to the client certificate (mTLS).  Required for live runs.",
    )
    parser.add_argument(
        "--key",
        default=None,
        help="Path to the client private key (mTLS).  Required for live runs.",
    )
    parser.add_argument(
        "--ca",
        default=None,
        help="Path to the CA certificate.  Required for live runs.",
    )
    parser.add_argument(
        "--project-prefix",
        default="verify_live",
        help="Prefix for the disposable project name (default: %(default)s).",
    )
    parser.add_argument(
        "--keep-project",
        action="store_true",
        default=False,
        help="Skip teardown of the disposable project for post-run debugging.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        default=False,
        help="List available suite names and exit.",
    )
    parser.add_argument(
        "suites",
        nargs="*",
        metavar="SUITE",
        help="Run only the named suites (default: all suites).",
    )
    return parser


def _cmd_list() -> None:
    """Print all available suite names to stdout and return."""
    suites = list_suites()
    print("Available suites:")
    for name, runners in suites:
        runner_count = len(runners)
        print(f"  {name}  ({runner_count} lifecycle runner(s))")


async def _run(args: argparse.Namespace) -> int:
    """Execute the pipeline and return the process exit code.

    Args:
        args: Parsed CLI arguments.

    Returns:
        0 on full success, 1 on any FAILED outcome or teardown error.
    """
    if not args.cert or not args.key or not args.ca:
        print(
            "ERROR: --cert, --key, and --ca are required for live runs.\n"
            "       Use --list to list suites without connecting.",
            file=sys.stderr,
        )
        return 1

    requested: Sequence[str] = args.suites
    available_suites = list_suites()
    available_names = [name for name, _ in available_suites]

    if requested:
        unknown = sorted(set(requested) - set(available_names))
        if unknown:
            print(
                f"ERROR: unknown suite(s): {unknown}. "
                f"Available: {available_names}",
                file=sys.stderr,
            )
            return 1

    settings = {
        "host": args.host,
        "port": args.port,
        "protocol": "https",
        "ssl": {"cert": args.cert, "key": args.key, "ca": args.ca},
    }

    # timeout=120.0: same as the old script (ReadTimeout observed at 60s default
    # during project_pip_check/project_pip_list after a venv-bootstrap job).
    async with CodeAnalysisAsyncClient.from_adapter_settings(
        settings, check_hostname=False, timeout=120.0
    ) as client:
        try:
            await client.rpc.health()
        except Exception as exc:
            print(f"FAILED health-check: {exc!r}")
            return 1

        try:
            fixtures = await seed_fixtures(client, args.project_prefix)
        except Exception as exc:
            print(f"FAILED fixture setup: {exc!r}")
            return 1

        exit_code = 0
        try:
            outcomes = await run_sweep(client, fixtures)
            failed_count = print_summary(outcomes)
            if failed_count:
                exit_code = 1
        finally:
            teardown_ok = await teardown_fixtures(
                client, fixtures, keep_project=args.keep_project
            )
            if not teardown_ok:
                exit_code = 1

    return exit_code


async def _async_main(argv: Sequence[str] | None = None) -> int:
    """Parse args and dispatch to the appropriate sub-command.

    Args:
        argv: Argument list; ``None`` reads from ``sys.argv``.

    Returns:
        Process exit code.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.list:
        _cmd_list()
        return 0

    return await _run(args)


def main_sync(argv: Sequence[str] | None = None) -> None:
    """Synchronous entry point used by the console_script wrapper.

    Args:
        argv: Argument list; ``None`` reads from ``sys.argv``.
    """
    raise SystemExit(asyncio.run(_async_main(argv)))


if __name__ == "__main__":
    main_sync()
