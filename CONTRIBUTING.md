# Contributing

## Local Setup

```bash
python -m pip install -e ".[dev,stack,dask]"
```

## Checks

```bash
ruff check .
mypy src
pytest
python -m build
```

## Notes

- Keep the legacy `gee_downloader.py` and `access_GEE_generic.py` scripts ignored; they are local references only.
- Favor pure functions in the discovery and grid-planning layers so they remain easy to test without live Earth Engine access.
- Live Earth Engine checks belong in the optional `smoke-live-gee.yml` workflow, not in the default unit test suite.
