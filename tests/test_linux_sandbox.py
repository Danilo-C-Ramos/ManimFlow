"""The Linux sandbox check, with a stand-in `bwrap` on the PATH."""

import sys

import pytest

from manimflow import linux_sandbox

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Codex uses bubblewrap on Linux only")


@pytest.fixture
def bwrap(tmp_path):
    """Makes the `bwrap` on a PATH of its own exit with `code` and print `stderr`."""

    def make(code: int, stderr: str = "") -> str:
        program = tmp_path / "bwrap"
        program.write_text(f"#!/bin/sh\necho '{stderr}' >&2\nexit {code}\n")
        program.chmod(0o755)
        return str(tmp_path)

    return make


@pytest.fixture
def restricted(tmp_path, monkeypatch):
    """Sets the AppArmor user namespace restriction that `problem` reads."""

    def set_to(value: str) -> None:
        sysctl = tmp_path / "apparmor_restrict_unprivileged_userns"
        sysctl.write_text(value + "\n")
        monkeypatch.setattr(linux_sandbox, "RESTRICT_SYSCTL", sysctl)

    return set_to


def test_a_sandbox_that_starts_has_no_problem(bwrap):
    assert linux_sandbox.problem(bwrap(0)) is None


def test_ubuntus_restriction_comes_with_the_command_that_lifts_it(bwrap, restricted):
    restricted("1")

    problem = linux_sandbox.problem(bwrap(1, "bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted"))

    assert problem is not None
    assert "Ubuntu" in problem
    assert linux_sandbox.fix_command() in problem


def test_another_failure_shows_what_bubblewrap_said(bwrap, restricted):
    restricted("0")

    problem = linux_sandbox.problem(bwrap(1, "bwrap: No permissions to create new namespace"))

    assert problem is not None
    assert "No permissions to create new namespace" in problem
    assert "sudo" not in problem


def test_the_fix_installs_the_profile_shipped_with_manimflow():
    assert linux_sandbox.PROFILE.is_file()
    assert "profile manimflow-bwrap /usr/bin/bwrap" in linux_sandbox.PROFILE.read_text()
    assert str(linux_sandbox.PROFILE) in linux_sandbox.fix_command()
