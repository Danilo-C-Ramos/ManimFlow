"""A lesson's version history: a local git repository inside the lesson folder.

ManimFlow drives it through pygit2, so the teacher needs no Git install and no
account, and nothing is ever pushed. Commit messages are in Portuguese, since
the teacher reads them. See docs/versioning.md.

- `History.open` starts the history of a new lesson (or of one without any) with
  a first commit of its files.
- `commit_agent_turn` after every agent turn, `commit_manual_edit` after the
  teacher's own edits.
- `manual_changes` is the diff of the teacher's edits since the agent's last
  turn, for the agent's next message.
"""

from pathlib import Path

import pygit2
from pygit2.enums import ConfigLevel

from manimflow.render import CACHE_DIR, OUTPUT_DIR

# A teacher who also uses Git may have settings (line endings, global ignores,
# diff prefixes) that would change what gets committed or how the diff reads.
# Only each lesson's own config applies.
for _level in (ConfigLevel.PROGRAMDATA, ConfigLevel.SYSTEM, ConfigLevel.XDG, ConfigLevel.GLOBAL):
    pygit2.settings.search_path[_level] = ""

FIRST_VERSION = "Primeira versão da aula"

OUTSIDE_EDITS = "Edições feitas fora do ManimFlow"

_AUTHOR = ("ManimFlow", "manimflow@localhost")
# Points at the lesson as the agent last left it, whether its turn committed or not.
_LAST_AGENT_TURN = "refs/manimflow/last-agent-turn"

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

    def commit_agent_turn(self, request: str) -> str | None:
        """Commits what the agent changed during the turn for `request`, the teacher's
        message, and returns the commit's id, or None when the turn changed no file.

        Call it after every turn, even one that changed nothing: the turn received
        the manual changes with its message, so they start over from here.
        """
        commit = self._commit(f"Pedido: {request}")
        self._mark_agent_turn()
        return commit

    def commit_manual_edit(self, message: str) -> str | None:
        """Commits the teacher's own edits with `message`, such as "Edição manual em
        fisica.py", and returns the commit's id, or None when no file changed."""
        return self._commit(message)

    def manual_changes(self) -> str:
        """The teacher's changes since the agent's last turn, committed or not, as a
        unified diff with paths relative to the lesson; empty when there are none."""
        since = self._repo.references[_LAST_AGENT_TURN].peel(pygit2.Commit).tree
        now = self._repo[self._snapshot()].peel(pygit2.Tree)
        return since.diff_to_tree(now).patch or ""

    def _commit(self, message: str) -> str | None:
        """Commits every file of the lesson as it is now, unless nothing changed."""
        tree = self._snapshot()
        parents = [] if self._repo.head_is_unborn else [self._repo.head.target]
        if parents and self._repo[parents[0]].peel(pygit2.Commit).tree_id == tree:
            return None
        author = pygit2.Signature(*_AUTHOR)
        return str(self._repo.create_commit("HEAD", author, author, message, tree, parents))

    def _snapshot(self) -> pygit2.Oid:
        """Stores every versioned file of the lesson as it is now, returning its tree."""
        index = self._repo.index
        # From scratch, so deleted files leave the snapshot too.
        index.clear()
        index.add_all()
        index.write()
        return index.write_tree()

    def _mark_agent_turn(self) -> None:
        self._repo.references.create(_LAST_AGENT_TURN, self._repo.head.target, force=True)
