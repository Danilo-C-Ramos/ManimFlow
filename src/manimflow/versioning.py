"""A lesson's version history: a local git repository inside the lesson folder.

ManimFlow drives it through pygit2, so the teacher needs no Git install and no
account, and nothing is ever pushed. Commit messages are in Portuguese, since
the teacher reads them. See docs/versioning.md.

- `History.open` starts the history of a new lesson (or of one without any) with
  a first commit of its files.
- `commit_agent_turn` after every agent turn, `commit_manual_edit` after the
  teacher's own edits.
- `manual_changes` is the diff of the teacher's edits since the agent's last
  turn, for the agent's next message. It leaves out the plan, which reaches the
  agent through "Aprovar plano".
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pygit2
from pygit2.enums import ConfigLevel

from manimflow.plan import PLAN_FILE
from manimflow.render import CACHE_DIR, OUTPUT_DIR

# A teacher who also uses Git may have settings (line endings, global ignores,
# diff prefixes) that would change what gets committed or how the diff reads.
# Only each lesson's own config applies.
for _level in (ConfigLevel.PROGRAMDATA, ConfigLevel.SYSTEM, ConfigLevel.XDG, ConfigLevel.GLOBAL):
    pygit2.settings.search_path[_level] = ""

FIRST_VERSION = "Primeira versão da aula"

OUTSIDE_EDITS = "Edições feitas fora do ManimFlow"

_AUTHOR = ("ManimFlow", "manimflow@localhost")
# The digest of plano.yaml as the teacher last approved it, kept in the history's folder
# so it moves with the lesson and never shows among the teacher's files.
_APPROVED_PLAN = "manimflow-plano-aprovado"
RESTORED = "Voltei para a versão de {when}"
# Points at the lesson as the agent last left it, whether its turn committed or not.
_LAST_AGENT_TURN = "refs/manimflow/last-agent-turn"
# Ends the message of a turn's version, so the chat finds the version of each past turn.
_TURN = "\n\nTurno: "

# Everything a render or a test run can reproduce. Kept in .git/info/exclude
# rather than a .gitignore, so the teacher's folder gets no extra file.
_NOT_VERSIONED = [
    f"/{OUTPUT_DIR}/",
    f"/{CACHE_DIR}/",
    # Where Manim writes when run by hand, outside ManimFlow's CLI.
    "/media/",
    "__pycache__/",
    "*.pyc",
    ".pytest_cache/",
]


class History:
    def __init__(self, repo: pygit2.Repository) -> None:
        self._repo = repo

    @classmethod
    def open(cls, lesson: Path) -> "History":
        """Opens the lesson's history, first creating it with a commit of the current
        files when the lesson has none."""
        dot_git = lesson / ".git"
        # Not a search upwards: a lesson inside another repository still gets its own.
        if dot_git.is_dir():
            repo = pygit2.Repository(str(dot_git))
        else:
            repo = pygit2.init_repository(str(lesson))
        # Rewritten on every open, so older lessons pick up a changed list.
        exclude = dot_git / "info" / "exclude"
        exclude.parent.mkdir(exist_ok=True)
        exclude.write_text("\n".join(_NOT_VERSIONED) + "\n", encoding="utf-8")
        history = cls(repo)
        # Also when an earlier open stopped between creating the repository and committing.
        if repo.head_is_unborn:
            history._commit(FIRST_VERSION)
        if _LAST_AGENT_TURN not in repo.references:
            history._mark_agent_turn()
        return history

    def commit_agent_turn(self, request: str, turn: str | None = None) -> str | None:
        """Commits what the agent changed during the turn for `request`, the teacher's
        message, and returns the commit's id, or None when the turn changed no file.
        `turn` is the turn's id in the agent's conversation.

        Call it after every turn, even one that changed nothing: the turn received
        the manual changes with its message, so they start over from here.
        """
        commit = self._commit(f"Pedido: {request}" + (f"{_TURN}{turn}" if turn else ""))
        self._mark_agent_turn()
        return commit

    def commit_manual_edit(self, message: str, paths: Sequence[str] | None = None) -> str | None:
        """Commits the teacher's own edits with `message`, such as "Edição manual em
        fisica.py", and returns the commit's id, or None when no file changed.

        With `paths`, relative to the lesson, only those files' changes go in.
        """
        return self._commit(message, paths)

    def manual_changes(self) -> str:
        """The teacher's changes since the agent's last turn, committed or not, as a
        unified diff with paths relative to the lesson; empty when there are none.

        Changes to the plan are left out: its approval message carries them.
        """
        since = self._repo.references[_LAST_AGENT_TURN].peel(pygit2.Commit).tree
        now = self._repo[self._snapshot()].peel(pygit2.Tree)
        return "".join(
            patch.text or ""
            for patch in since.diff_to_tree(now)
            if patch is not None and PLAN_FILE not in (patch.delta.old_file.path, patch.delta.new_file.path)
        )

    def approve_plan(self) -> None:
        """Records plano.yaml as it is now as the plan the teacher approved."""
        workdir = Path(self._repo.workdir)
        approval_file(workdir).write_text(_digest(workdir / PLAN_FILE))

    def versions(self) -> list["Version"]:
        """The lesson's versions, newest first."""
        if self._repo.head_is_unborn:
            return []
        versions = []
        for commit in self._repo.walk(self._repo.head.target):
            message, _, turn = commit.message.strip().partition(_TURN)
            when = datetime.fromtimestamp(commit.commit_time).astimezone()
            versions.append(Version(str(commit.id), message, when, turn.strip() or None))
        return versions

    def turn_versions(self) -> dict[str, "Version"]:
        """The version each agent turn saved, by the turn's id."""
        return {version.turn: version for version in self.versions() if version.turn is not None}

    def restore(self, version: str) -> str | None:
        """Brings the lesson's versioned files back to `version`, as a new version made by
        the teacher, and returns its id, or None when nothing changed.

        Files added since then are removed; renders and caches stay.
        """
        commit = self._repo.revparse_single(version).peel(pygit2.Commit)
        # Whatever the teacher changed since the last version is kept in history first.
        self._commit("Edições antes de voltar a uma versão")
        workdir = Path(self._repo.workdir)
        then = _files(commit.tree)
        for path in _files(self._repo.head.peel(pygit2.Commit).tree):
            if path not in then:
                (workdir / path).unlink(missing_ok=True)
        for path, blob in then.items():
            target = workdir / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self._repo[blob].peel(pygit2.Blob).data)
        when = datetime.fromtimestamp(commit.commit_time).astimezone()
        return self._commit(RESTORED.format(when=f"{when:%d/%m às %H:%M}"))

    def _commit(self, message: str, paths: Sequence[str] | None = None) -> str | None:
        """Commits the lesson's files as they are now, or only `paths` when given, unless
        nothing changed."""
        tree = self._snapshot(paths)
        parents = [] if self._repo.head_is_unborn else [self._repo.head.target]
        if parents and self._repo[parents[0]].peel(pygit2.Commit).tree_id == tree:
            return None
        author = pygit2.Signature(*_AUTHOR)
        return str(self._repo.create_commit("HEAD", author, author, message, tree, parents))

    def _snapshot(self, paths: Sequence[str] | None = None) -> pygit2.Oid:
        """Stores every versioned file of the lesson as it is now, or only `paths` on top
        of the last commit, returning its tree."""
        index = self._repo.index
        # From scratch, so deleted files leave the snapshot too.
        index.clear()
        if paths is None or self._repo.head_is_unborn:
            index.add_all()
        else:
            index.read_tree(self._repo.head.peel(pygit2.Commit).tree)
            for path in paths:
                if (Path(self._repo.workdir) / path).is_file():
                    index.add(path)
                elif path in index:
                    index.remove(path)
        index.write()
        return index.write_tree()

    def _mark_agent_turn(self) -> None:
        self._repo.references.create(_LAST_AGENT_TURN, self._repo.head.target, force=True)


@dataclass(frozen=True)
class Version:
    id: str
    message: str
    # Aware, in the teacher's time zone.
    when: datetime
    # The agent turn that saved it, if one did.
    turn: str | None = None


def approval_file(lesson: Path) -> Path:
    return lesson / ".git" / _APPROVED_PLAN


def plan_approved(lesson: Path) -> bool:
    """Whether plano.yaml is, byte for byte, the plan the teacher last approved."""
    try:
        approved = approval_file(lesson).read_text()
    except OSError:
        return False
    return approved == _digest(lesson / PLAN_FILE)


def _digest(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _files(tree: pygit2.Tree, prefix: str = "") -> dict[str, pygit2.Oid]:
    """Every file in the tree, by its path, with its blob."""
    found: dict[str, pygit2.Oid] = {}
    for entry in tree:
        path = f"{prefix}{entry.name}"
        if entry.type_str == "tree":
            found.update(_files(entry, f"{path}/"))  # type: ignore[arg-type]
        else:
            found[path] = entry.id
    return found
