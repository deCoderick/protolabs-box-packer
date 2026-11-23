## Box Packer

A small FastAPI service that, given a list of packages, returns how many shipping boxes are needed to ship them.

### Quick start

Requires [uv](https://docs.astral.sh/uv/) (it installs the pinned Python version automatically).

```bash
uv sync                                          # install dependencies
uv run uvicorn box_packer.main:app --reload      # run on http://127.0.0.1:8000 (docs at /docs)
uv run pytest                                    # run tests
uv run ruff check . && uv run mypy src tests     # lint + type-check
```

_Work in progress — approach, assumptions and trade-offs will be documented here._
