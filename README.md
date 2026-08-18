# space

A monorepo of small, self-contained Python tools. Every root-level directory is one
independent tool; they share a toolchain and nothing else.

## Tools

| Tool | What it does |
| ---- | ------------ |
| [`starlight`](starlight/) | Tells you when the light you're seeing from a star left it. |

## Getting started

The repo is a [uv](https://docs.astral.sh/uv/) workspace with a single shared virtualenv.

```bash
uv sync                                       # create the venv from uv.lock
uv run pytest                                 # run every tool's tests
uv run python -m starlight Sirius             # run a tool
```

## Development

```bash
uv run ruff check .          # lint
uv run ruff format .         # format
uv run pytest starlight      # run one tool's tests
```

CI runs lint, a formatting check, and the tests on every push to `main` and every pull
request. Run all three locally before committing — the formatter's output is not
negotiable, so `ruff format .` should be the last thing you do.

[`CLAUDE.md`](CLAUDE.md) is the full contributor guide: repo layout, the lint and
formatting rules CI enforces, and how to add a new tool. [`docs/`](docs/) holds dated design
records for the tools — history, not current documentation.

## License

MIT — see [LICENSE](LICENSE).
