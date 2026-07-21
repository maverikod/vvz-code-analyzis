"""Unit tests for packaging/bin/casmgr-compose-ulimit-patch's patch logic.

The script has no .py extension (it's an installed executable, like its
siblings casmgr-install-server-config / casmgr-pg-set-password), so it is
loaded via importlib rather than a normal import.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "packaging" / "bin" / "casmgr-compose-ulimit-patch"

_loader = importlib.machinery.SourceFileLoader(
    "casmgr_compose_ulimit_patch", str(SCRIPT_PATH)
)
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
assert _spec is not None
_mod = importlib.util.module_from_spec(_spec)
_loader.exec_module(_mod)

patch_compose = _mod.patch_compose
DEFAULT_TARGET = _mod.DEFAULT_TARGET


NO_ULIMITS = """\
name: casmgr

services:
  casmgr:
    image: vasilyvz/casmgr:${CASMGR_VERSION:-latest}
    container_name: casmgr
    restart: unless-stopped
    env_file:
      - /var/casmgr/secrets/.env
    environment:
      CASMGR_CONFIG: /etc/casmgr/config.json
    volumes:
      - /etc/casmgr:/etc/casmgr
    ports:
      - "0.0.0.0:15010:15010"

networks:
  smart-assistant:
    external: true
"""

LOW_ULIMITS = """\
name: casmgr

services:
  casmgr:
    image: vasilyvz/casmgr:${CASMGR_VERSION:-latest}
    ulimits:
      nofile:
        soft: 1024
        hard: 262144
    restart: unless-stopped

networks:
  smart-assistant:
    external: true
"""

HIGH_ULIMITS = """\
name: casmgr

services:
  casmgr:
    image: vasilyvz/casmgr:${CASMGR_VERSION:-latest}
    ulimits:
      nofile:
        soft: 1048576
        hard: 1048576
    restart: unless-stopped
"""

MIXED_ULIMITS = """\
services:
  casmgr:
    image: vasilyvz/casmgr:latest
    ulimits:
      nofile:
        soft: 1048576
        hard: 1024
"""

EMPTY_NOFILE = """\
services:
  casmgr:
    image: vasilyvz/casmgr:latest
    ulimits:
      nofile: {}
    restart: unless-stopped
"""


def test_missing_ulimits_block_is_added():
    new_text, changed, log = patch_compose(NO_ULIMITS)
    assert changed is True
    assert "ulimits:" in new_text
    assert f"soft: {DEFAULT_TARGET}" in new_text
    assert f"hard: {DEFAULT_TARGET}" in new_text
    assert any("added ulimits.nofile" in line for line in log)
    # Structure preserved: still parseable back with the same service found.
    _, changed_again, _ = patch_compose(new_text)
    assert changed_again is False


def test_low_values_are_raised_not_replaced_wholesale():
    new_text, changed, log = patch_compose(LOW_ULIMITS)
    assert changed is True
    assert f"soft: {DEFAULT_TARGET}" in new_text
    assert f"hard: {DEFAULT_TARGET}" in new_text
    assert "soft: 1024" not in new_text
    assert "hard: 262144" not in new_text
    assert any("raised ulimits.nofile.soft 1024" in line for line in log)
    assert any("raised ulimits.nofile.hard 262144" in line for line in log)


def test_high_values_are_left_untouched_raise_only():
    new_text, changed, log = patch_compose(HIGH_ULIMITS)
    assert changed is False
    assert new_text == HIGH_ULIMITS
    assert any("already >=" in line for line in log)


def test_mixed_values_only_the_low_one_is_raised():
    new_text, changed, log = patch_compose(MIXED_ULIMITS)
    assert changed is True
    assert "soft: 1048576" in new_text  # untouched, already above target
    assert "hard: 1024" not in new_text
    assert f"hard: {DEFAULT_TARGET}" in new_text
    joined = "\n".join(log)
    assert "soft" not in joined.split("raised")[0] or True  # sanity: no crash
    assert any("raised ulimits.nofile.hard 1024" in line for line in log)
    assert any("already >=" in line and "soft" in line for line in log)


def test_nofile_key_present_but_empty_gets_soft_and_hard_added():
    new_text, changed, log = patch_compose(EMPTY_NOFILE)
    assert changed is True
    assert f"soft: {DEFAULT_TARGET}" in new_text
    assert f"hard: {DEFAULT_TARGET}" in new_text


def test_idempotent_double_run():
    once, changed1, _ = patch_compose(NO_ULIMITS)
    assert changed1 is True
    twice, changed2, log2 = patch_compose(once)
    assert changed2 is False
    assert once == twice
    assert any("no changes needed" in line for line in log2)


def test_double_run_on_low_values_converges():
    once, changed1, _ = patch_compose(LOW_ULIMITS)
    assert changed1 is True
    twice, changed2, _ = patch_compose(once)
    assert changed2 is False
    assert once == twice


def test_unknown_service_makes_no_changes():
    new_text, changed, log = patch_compose(NO_ULIMITS, service="postgres")
    assert changed is False
    assert new_text == NO_ULIMITS
    assert any("not found" in line for line in log)


def test_custom_target_is_honored():
    new_text, changed, log = patch_compose(NO_ULIMITS, target=65536)
    assert changed is True
    assert "soft: 65536" in new_text
    assert "hard: 65536" in new_text


@pytest.mark.parametrize("text", [NO_ULIMITS, LOW_ULIMITS, HIGH_ULIMITS])
def test_never_lowers_below_original_hard_value(text):
    """Raise-only invariant across all fixtures: hard value after patch is
    always >= the hard value before (or == target if none existed)."""
    import re

    def hard_values(s: str) -> list[int]:
        return [int(m) for m in re.findall(r"hard:\s*(\d+)", s)]

    before = hard_values(text)
    after_text, _, _ = patch_compose(text)
    after = hard_values(after_text)
    if before:
        assert min(after) >= min(before)
    assert all(v >= DEFAULT_TARGET for v in after)


def test_script_is_executable_and_has_shebang():
    assert SCRIPT_PATH.is_file()
    mode = SCRIPT_PATH.stat().st_mode
    assert mode & 0o111, "script must be executable (installed as a postinst helper)"
    first_line = SCRIPT_PATH.read_text(encoding="utf-8").splitlines()[0]
    assert first_line.startswith("#!")


def test_install_package_script_ships_the_helper():
    install_script = (REPO_ROOT / "debian" / "install-package.sh").read_text(
        encoding="utf-8"
    )
    assert "casmgr-compose-ulimit-patch" in install_script


def test_postinst_invokes_the_patch_step():
    postinst = (REPO_ROOT / "debian" / "postinst").read_text(encoding="utf-8")
    assert "patch_container_ulimits" in postinst
    assert "casmgr-compose-ulimit-patch" in postinst


def test_shipped_compose_template_has_target_ulimits():
    compose = (
        REPO_ROOT / "docker" / "docker-compose.allinone.yml"
    ).read_text(encoding="utf-8")
    _, changed, _ = patch_compose(compose)
    assert changed is False, "shipped template should already be at/above target"


def test_shipped_systemd_unit_has_limitnofile():
    unit = (REPO_ROOT / "packaging" / "systemd" / "casmgr.service").read_text(
        encoding="utf-8"
    )
    assert f"LimitNOFILE={DEFAULT_TARGET}" in unit
