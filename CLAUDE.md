# space

A monorepo of small, self-contained Python tools.

## Repo shape

Every root-level directory is **one independent tool**, apart from `docs/` and the dotfile
directories. Tools do not import each other — if two tools need the same code, duplicate it
or promote it to its own tool with a clear API. The only shared things are the toolchain and
the config in the root `pyproject.toml`.

```
space/
├── pyproject.toml        # uv workspace root; ruff + pytest config; dev dependencies
├── .editorconfig         # editor-side mirror of the ruff style settings
├── uv.lock               # committed — CI installs from it with `uv sync --locked`
├── .python-version       # 3.13 (used by uv and pyenv)
├── .github/workflows/    # CI
├── docs/                 # design records, kept by date; not tied to any one tool
└── <tool>/               # one directory per tool — an importable package
    ├── __init__.py       # makes the tool a package
    ├── __main__.py       # the CLI entry point, so `python -m <tool>` runs it
    ├── pyproject.toml    # workspace member metadata
    ├── conftest.py       # tool-wide pytest fixtures (optional)
    ├── *.py              # the tool's modules, flat inside the package
    └── tests/            # test_*.py
```

Each tool is a **package directory at the repo root**, with its modules flat inside it —
there is no `src/` and no nested package. The repo root is the only import root, so a tool
is imported as `starlight.catalog` and its own modules import each other relatively
(`from . import caldate`).

A tool's CLI lives in `__main__.py` and is invoked as `python -m <tool>`. Keep `__main__.py`
importable: it uses relative imports, so it cannot be run as a loose script, and it should
carry no shebang and no executable bit.

`docs/` holds dated design records — specs and implementation plans, named for the day they
were written. They describe a tool as it was designed, not as it is now, so read them as
history and keep current documentation in the tool's `README.md`.

## Commands

All commands run from the repo root. `uv` manages the single shared `.venv`.

```bash
uv sync                          # create/update the venv from uv.lock
uv run pytest                    # run every tool's tests
uv run pytest starlight          # run one tool's tests
uv run ruff check .              # lint
uv run ruff check --fix .        # lint, applying safe fixes
uv run ruff format .             # format
uv run ruff format --check .     # verify formatting without writing (what CI runs)
uv run python -m starlight Sirius             # run a tool
```

## Lint and formatting requirements

CI fails on any violation of the following, so run `uv run ruff check .` and
`uv run ruff format .` before committing.

- **Ruff is the only linter and formatter.** Do not add black, flake8, isort, or pylint.
- `.editorconfig` mirrors these settings for editors. It is a convenience, not a second
  source of truth — `pyproject.toml` is authoritative, and the two must agree. Changing
  the line length or quote style means changing both.
- **Line length 120**, double quotes, ruff's default formatter style otherwise.
- `ruff format` must leave the tree unchanged, and `ruff check` must report no errors.
- **All configuration lives in the root `pyproject.toml`.** Never add a `[tool.ruff]`
  section to a tool's `pyproject.toml` — one rule set applies repo-wide.
- Enabled rule sets: `E`, `W`, `F` (pycodestyle/pyflakes), `I` (import sorting),
  `N` (pep8-naming), `UP` (pyupgrade), `B` (bugbear), `A` (builtin shadowing),
  `C4` (comprehensions), `SIM`, `RET`, `ARG` (unused arguments), `TID` (tidy imports),
  and `RUF`.
- Deliberately ignored, with reasons recorded in `pyproject.toml`: `E501` (the formatter
  owns line length) and `RUF001`/`RUF002` (Greek letters in astronomical designations are
  intentional, not homoglyph typos). That is the whole list — everything else is enforced,
  including `N818`, so exception classes must end in `Error`.
- **Suppress narrowly.** A `# noqa` must name the specific rule and say why:
  `# noqa: ARG001 - signature fixed by the callback protocol`. Bare `# noqa` is not
  acceptable. Prefer fixing the code over suppressing.
- If a rule is genuinely wrong for this repo, change `select`/`ignore` in the root
  `pyproject.toml` with a comment — do not scatter suppressions.

## Testing

- pytest, configured in the root `pyproject.toml`. Tests live in `<tool>/tests/`.
- Tool-wide fixtures go in `<tool>/conftest.py` (at the tool root, not inside `tests/`).
- `tests/` directories must **not** contain `__init__.py`. Two tools may duplicate a
  module (see "Repo shape") and so may end up with same-named test files, e.g. both
  `starlight/tests/test_catalog.py` and `spacetime/tests/test_catalog.py`; pytest's
  root `addopts` sets `--import-mode=importlib` so those don't collide at collection.
- Tests must not touch the network. Stub the network seam and, where practical, add an
  autouse fixture that makes real calls fail loudly — see `starlight/conftest.py`.

## CLI help and error output

Every tool with a CLI documents itself through `--help`. This is a requirement, not a
nicety: `python -m <tool> --help` is the only documentation a user has in front of them at
the moment they need it, so it must be complete enough to use the tool without opening the
README. Build the parser in a `build_parser()` function that takes no arguments and returns
the `ArgumentParser`, so tests can render the help text without running the CLI.

Every parser carries all of:

- **`prog="python -m <tool>"`.** That is how the tool is actually invoked — `__main__.py`
  uses relative imports and has no shebang, so a bare filename in the usage line names
  something that cannot be run. `prog` also prefixes argparse's own error messages.
- **A `description` that says what the tool computes**, not just what it is about — a
  headline sentence, then a short paragraph on the method and what the numbers mean.
- **An `epilog` holding worked examples and a table of exit codes.** Examples use real
  star names or inputs that actually resolve, and their comment column is aligned. The
  exit codes must match the README's table and the codes the tool really returns —
  remember that argparse exits 2 of its own accord, so whatever a tool uses 2 for has to
  cover that too.
- **A `help=` on every argument stating what it accepts and what it changes in the
  output** — the accepted format and its edge cases, the default, and any case where the
  flag silently does nothing. "show the range" is not enough; name the range and say when
  it is absent.

`description` and `epilog` are printed verbatim under `RawDescriptionHelpFormatter`, so
hand-wrap them to about 88 columns. Per-argument `help=` strings are still reflowed by
argparse — write them as one string and let it wrap.

A command line argparse itself rejects — a missing required argument, a value of the
wrong type, an unrecognized flag — must print the **whole help**, not the usage line
alone. Usage names the flags but says nothing about what any of them accepts, which is
precisely what a user who just got the command line wrong is missing. Subclass
`ArgumentParser` and override `error()`:

```python
class _HelpOnErrorParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.print_help(sys.stderr)
        self.exit(2, f"\n{self.prog}: error: {message}\n")
```

The help goes to stderr, because this is still an error, and the message is printed after
it so it stays the last thing on a scrolled terminal. Each tool carries its own copy of
this class — tools do not import each other.

Errors a tool raises about a *value* argparse already accepted — a date that does not
exist, an acceleration of zero — stay concise instead. They print what was wrong **and**
what would work, and nothing else; a screen of help would only bury the hint, which is
the useful half:

```
Acceleration must be a positive, finite number of G, not 0.0.
Try --accel 1 for Earth-normal gravity on deck.
```

Raise the "what was wrong" half from the module that knows (`caldate.DateError`,
`relativity.TripError`, `catalog.StarNotFoundError`) and print the exception directly, so
the sentence exists in exactly one place; add the "what would work" half in `__main__.py`,
where the flag names live.

Test the help text and the error hints like any other behavior — assert against
`build_parser().format_help()` and against stderr. `starlight/tests/test_starlight.py` and
`spacetime/tests/test_spacetime.py` are the worked examples.

## Adding a tool

1. Create `<tool>/` with a `pyproject.toml`:

   ```toml
   [project]
   name = "<tool>"
   version = "0.1.0"
   description = "..."
   requires-python = ">=3.10"
   dependencies = []

   [tool.uv]
   package = false
   ```

   `package = false` marks it as a virtual workspace member: uv installs its dependencies
   into the shared venv but does not try to build it as a distribution. Tools are run with
   `python -m <tool>`, not installed.

2. Add `__init__.py` and, for anything with a CLI, `__main__.py` ending in:

   ```python
   if __name__ == "__main__":
       sys.exit(main())
   ```

   A CLI's parser and error output must meet the standard in
   [CLI help and error output](#cli-help-and-error-output).

3. Register the directory in `[tool.uv.workspace] members` in the root `pyproject.toml`.
   That is the only place — `[tool.ruff] src` and `[tool.pytest.ini_options] pythonpath` are
   both `["."]` and cover every tool, and pytest collects tests from the whole repo, so a
   new tool's tests cannot be silently skipped.

4. Run `uv sync` to refresh `uv.lock`, then `uv run ruff check . && uv run ruff format . && uv run pytest`.

Because each tool is its own package, two tools may both have a `config.py` or a `catalog.py`
without shadowing each other.

## Toolchain versions

Everything the toolchain depends on is pinned, so a CI run is reproducible from the commit
alone:

- **uv** — `required-version` under `[tool.uv]` in the root `pyproject.toml`. `uv` refuses to
  run if the installed version differs, and `astral-sh/setup-uv` reads the same field, so CI
  and local use one version and the workflow needs no `version:` input of its own. Bumping it
  means upgrading your local uv in the same commit.
- **pytest and ruff** — floors in `[dependency-groups] dev`, exact versions in `uv.lock`. CI
  installs from the lock with `uv sync --locked`; run `uv lock --upgrade` to move them.
- **GitHub Actions** — pinned to commit SHAs; see [CI](#ci).

## Python versions

Tools declare `requires-python = ">=3.10"`, and ruff's `target-version` is `py310`, so
generated fixes stay 3.10-compatible. CI only exercises **3.13** — older versions are
supported by declaration, not by testing.

## CI

`.github/workflows/ci.yml` runs on pushes to `main` and on pull requests: `uv sync --locked`,
then lint, format check, and tests, as a single job on Python 3.13.

Every action is **pinned to a commit SHA** with the version tag in a trailing comment. When
bumping an action, update both the SHA and the comment; resolve the SHA with:

```bash
gh api repos/<owner>/<repo>/git/ref/tags/<tag> --jq '.object.sha'
```
