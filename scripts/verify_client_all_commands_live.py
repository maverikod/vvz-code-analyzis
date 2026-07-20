#!/usr/bin/env python3
r"""
Live-server smoke/coverage verifier for every command code-analysis-server exposes.

Connects via mTLS to a **real** running code-analysis-server instance,
enumerates essentially every command it exposes (via ``help`` with no
``cmdname``), and for each one either executes it safely against a disposable
throwaway project, classifies it as verify-only without calling it, or
records it as an expected/unexpected error. It never touches any project
other than the disposable one it creates itself, and never calls the fixed
list of dangerous/process-wide commands (see
``_verify_client_all_commands_catalog.BUCKET_B_REASONS``).

Design note on coverage: a meaningful fraction of commands will land in
``expected-error`` with reason "no generic fixture value for required param"
rather than ``executed-ok`` — this verifier deliberately does not hand-craft
parameters for all ~140 commands (see the generic provider table in
``_verify_client_all_commands_catalog.py``); when no generic value exists for
a required parameter, the command is skipped rather than guessed, which keeps
behavior deterministic and safe.

============================================================
USAGE: connecting to the real target server
============================================================
This target server is **different** from the local ``config.json`` at the
repo root (that file points at a dev server on a different host/port). Do
**not** reuse ``default_config_path()`` / ``from_server_config_path()`` here
— pass connection details explicitly::

    python scripts/verify_client_all_commands_live.py \
        --host 192.168.254.26 --port 15010 \
        --cert verifier.crt --key verifier.key --ca ca.crt

============================================================
USAGE: regenerating a client certificate for this verifier
============================================================
This script never generates certificates itself (no openssl calls) — that is
an operator/tester concern, documented here since this is the only place it
gets documented (no separate .md file).

CA location (note the doubled directory name)::

    mtls_certificates/mtls_certificates/ca/ca.crt
    mtls_certificates/mtls_certificates/ca/ca.key

Subject template (same as ``scripts/generate_code_analysis_certs.sh``)::

    /C=UA/ST=Kyiv/L=Kyiv/O=MCP-Proxy/OU=Client/CN=<name>-client

SAN / EKU for the client cert::

    DNS.1=<name>-client
    DNS.2=<name>.local
    extendedKeyUsage=clientAuth

Example commands for a **dedicated, disposable** identity — do NOT reuse
``client/code-analysis.*``::

    openssl genrsa -out verifier.key 2048
    openssl req -new -key verifier.key -out verifier.csr \
        -subj "/C=UA/ST=Kyiv/L=Kyiv/O=MCP-Proxy/OU=Client/CN=code-analysis-client-verifier-client"
    openssl x509 -req -in verifier.csr -CA mtls_certificates/mtls_certificates/ca/ca.crt \
        -CAkey mtls_certificates/mtls_certificates/ca/ca.key -CAcreateserial \
        -out verifier.crt -days 30 -extensions v3_client -extfile <(printf \
        '[v3_client]\nbasicConstraints=CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=clientAuth\nsubjectAltName=@alt_names\n[alt_names]\nDNS.1=code-analysis-client-verifier-client\nDNS.2=code-analysis-client-verifier.local\n')

**Rationale for the short ~30-day validity**: this is a disposable,
one-time-use verifier identity, not a long-lived service identity (those use
the 10-year default in ``generate_code_analysis_certs.sh``). There is no
CRL/revocation mechanism for these client certs, so short validity is the
safety control. Never commit the generated key/cert to git; delete them after
the run.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_CLIENT = _REPO / "client"
_EXAMPLES = _CLIENT / "examples"
for _p in (_REPO, _CLIENT, _EXAMPLES):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from _common import chdir_repo_root, ensure_client_package_on_path  # noqa: E402

ensure_client_package_on_path()
chdir_repo_root()

from code_analysis_client import CodeAnalysisAsyncClient  # noqa: E402

from _verify_client_all_commands_fixtures import seed_fixtures  # noqa: E402
from _verify_client_all_commands_sweep import print_summary, run_sweep  # noqa: E402
from _verify_client_all_commands_teardown import teardown_fixtures  # noqa: E402


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments for this verifier.

    Returns:
        Parsed argparse namespace.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Live-server smoke/coverage verifier for every command "
            "code-analysis-server exposes. See module docstring for the "
            "openssl recipe to generate --cert/--key."
        ),
    )
    parser.add_argument(
        "--host", default="192.168.254.26", help="Server host (default: %(default)s)."
    )
    parser.add_argument(
        "--port", type=int, default=15010, help="Server port (default: %(default)s)."
    )
    parser.add_argument(
        "--cert", required=True, help="Path to the client certificate (mTLS)."
    )
    parser.add_argument(
        "--key", required=True, help="Path to the client private key (mTLS)."
    )
    parser.add_argument(
        "--ca",
        required=True,
        help="Path to the CA certificate used to verify the server.",
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
    return parser.parse_args()


async def main() -> int:
    """Run the health gate, fixture setup, command sweep, and teardown.

    Returns:
        0 if no command sweep outcome landed in ``Status.FAILED`` and teardown
        completed cleanly; 1 otherwise. This is a hard gate on the initial
        mTLS health check and on fixture setup — both fail fast with a clear
        message and no further action.
    """
    args = _parse_args()
    settings = {
        "host": args.host,
        "port": args.port,
        "protocol": "https",
        "ssl": {"cert": args.cert, "key": args.key, "ca": args.ca},
    }
    # timeout=120.0 (default is 60.0): read-only Bucket-A commands issued
    # late in a run (project_pip_check / project_pip_list, right after the
    # project_pip_install venv-bootstrap job) observed a bare httpx
    # ReadTimeout('') under server load at the 60s default. This timeout
    # applies to every HTTP request the client makes, including queued-job
    # status polling, so doubling it is a plain headroom increase, not a
    # behavior change for any command that was already completing in time.
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


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
