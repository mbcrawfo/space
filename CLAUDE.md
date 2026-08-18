# space

A monorepo of small, self-contained Python tools.

## Repo shape

Every root-level directory is **one independent tool**. Tools do not import each other — if
two tools need the same code, duplicate it or promote it to its own tool with a clear API.
The only shared things are the toolchain and the config in the root `pyproject.toml`.

```
space/
├── pyproject.toml        # uv workspace root; ruff + pytest config; dev dependencies
├── .editorconfig         # editor-side mirror of the ruff style settings
├── uv.lock               # committed — CI installs from it with `uv sync --locked`
├── .python-version       # 3.13 (used by uv and pyenv)
├── .github/workflows/    # CI
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
  owns line length), `RUF001`/`RUF002` (Greek letters in astronomical designations are
  intentional, not homoglyph typos), and `N818` (exception names are part of a tool's
  public API; the rule would force renames like `StarNotFound` → `StarNotFoundError`).
- **Suppress narrowly.** A `# noqa` must name the specific rule and say why:
  `# noqa: ARG001 - signature fixed by the callback protocol`. Bare `# noqa` is not
  acceptable. Prefer fixing the code over suppressing.
- If a rule is genuinely wrong for this repo, change `select`/`ignore` in the root
  `pyproject.toml` with a comment — do not scatter suppressions.

## Testing

- pytest, configured in the root `pyproject.toml`. Tests live in `<tool>/tests/`.
- Tool-wide fixtures go in `<tool>/conftest.py` (at the tool root, not inside `tests/`).
- `tests/` directories must **not** contain `__init__.py`.
- Tests must not touch the network. Stub the network seam and, where practical, add an
  autouse fixture that makes real calls fail loudly — see `starlight/conftest.py`.

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

3. Register the directory in `[tool.uv.workspace] members` in the root `pyproject.toml`.
   That is the only place — `[tool.ruff] src` and `[tool.pytest.ini_options] pythonpath` are
   both `["."]` and cover every tool, and pytest collects tests from the whole repo, so a
   new tool's tests cannot be silently skipped.

4. Run `uv sync` to refresh `uv.lock`, then `uv run ruff check . && uv run ruff format . && uv run pytest`.

Because each tool is its own package, two tools may both have a `config.py` or a `catalog.py`
without shadowing each other.

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
