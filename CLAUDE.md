# space

A monorepo of small, self-contained Python tools.

## Repo shape

Every root-level directory is **one independent tool**. Tools do not import each other — if
two tools need the same code, duplicate it or promote it to its own tool with a clear API.
The only shared things are the toolchain and the config in the root `pyproject.toml`.

```
space/
├── pyproject.toml        # uv workspace root; ruff + pytest config; dev dependencies
├── uv.lock               # committed — CI installs from it with `uv sync --locked`
├── .python-version       # 3.13 (used by uv and pyenv)
├── .github/workflows/    # CI
└── <tool>/               # one directory per tool
    ├── pyproject.toml    # workspace member metadata
    ├── conftest.py       # tool-wide pytest fixtures (optional)
    ├── *.py              # flat modules
    └── tests/            # test_*.py
```

Tools use a **flat module layout**: modules live directly in the tool directory and import
each other by bare name (`import catalog`). There is no `src/` and no package directory.

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
uv run python starlight/starlight.py Sirius   # run a tool
```

## Lint and formatting requirements

CI fails on any violation of the following, so run `uv run ruff check .` and
`uv run ruff format .` before committing.

- **Ruff is the only linter and formatter.** Do not add black, flake8, isort, or pylint.
- **Line length 100**, double quotes, ruff's default formatter style otherwise.
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
   into the shared venv but does not try to build it as a distribution, which a flat module
   layout could not support anyway.

2. Register it in the root `pyproject.toml`, in **three** places:
   - `[tool.uv.workspace] members`
   - `[tool.ruff] src` — so ruff sorts the tool's own modules as first-party imports
   - `[tool.pytest.ini_options] testpaths` and `pythonpath` — `pythonpath` is what puts the
     tool directory on `sys.path` so `tests/` can `import <module>` by bare name

3. Run `uv sync` to refresh `uv.lock`, then `uv run ruff check . && uv run ruff format . && uv run pytest`.

### Name your modules distinctively

Because every tool directory goes on `sys.path`, two tools with a module of the same name
(`config.py`, `catalog.py`, `utils.py`) will shadow each other during a repo-wide pytest run.
Prefix or specialize module names when there is any chance of collision.

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
