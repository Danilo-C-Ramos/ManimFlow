"""The manimflow skill the agent gets: it must teach the CLI that is really installed."""

import re

from manimflow.codex_agent import SKILL


def test_the_skill_teaches_each_subcommand_of_the_self_check_and_all_exist(manimflow):
    taught = set(re.findall(r"`manimflow ((?:plan )?[a-z-]+) \.", SKILL.read_text(encoding="utf-8")))

    assert taught == {"check-continuity", "frames", "plan validate", "preview", "render"}
    for command in taught:
        result = manimflow(*command.split(), "--help")
        assert result.returncode == 0, (command, result.stderr)
        # Every one takes the lesson folder first, which the skill writes as `.`.
        assert "lesson" in result.stdout, command
