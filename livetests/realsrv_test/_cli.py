"""
CLI entry point for the realsrv-test live acceptance pipeline.

Console-script: ``realsrv-test`` (defined in livetests/pyproject.toml).

With no arguments, runs ALL suites sequentially (auto-discovered from
``realsrv_test.suites``) plus the generic alphabetical sweep over every live
command, and exits non-zero on any FAILED outcome or teardown error.  With
positional suite names, runs ONLY those suites' ordered lifecycles (no
generic sweep).

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

from realsrv_test.core.pipeline import run_pipeline
from realsrv_test.suites import collect_runners, list_suites


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
        help="Run only the named suites (default: all suites + full sweep).",
    )
    return parser


def _cmd_list() -> None:
    """Print all available suite names to stdout."""
    print("Available suites:")
    for name, runners in list_suites():
        print(f"  {name}  ({len(runners)} lifecycle runner(s))")


async def _async_main(argv: Sequence[str] | None = None) -> int:
    """Parse args, resolve the runner list from suite discovery, and run.

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

    if not args.cert or not args.key or not args.ca:
        print(
            "ERROR: --cert, --key, and --ca are required for live runs.\n"
            "       Use --list to list suites without connecting.",
            file=sys.stderr,
        )
        return 1

    requested: Sequence[str] = args.suites
    try:
        runners = collect_runners(requested or None)
    except KeyError as exc:
        print(f"ERROR: {exc.args[0]}", file=sys.stderr)
        return 1

    settings = {
        "host": args.host,
        "port": args.port,
        "protocol": "https",
        "ssl": {"cert": args.cert, "key": args.key, "ca": args.ca},
    }

    return await run_pipeline(
        settings,
        runners,
        full_sweep=not requested,
        project_prefix=args.project_prefix,
        keep_project=args.keep_project,
    )


def main_sync(argv: Sequence[str] | None = None) -> None:
    """Synchronous entry point used by the console_script wrapper.

    Args:
        argv: Argument list; ``None`` reads from ``sys.argv``.
    """
    raise SystemExit(asyncio.run(_async_main(argv)))


if __name__ == "__main__":
    main_sync()
