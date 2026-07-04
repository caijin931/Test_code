# CI Usage

## What runs in CI

- `pytest --cov=testcode --cov-report=term-missing --cov-report=xml`
- Coverage artifact upload

## Local equivalent

```bash
pip install -e .[dev]
pytest --cov=testcode --cov-report=term-missing --cov-report=xml
```

## Notes

- Integration tests are not run by default in CI.
- If you add secret-backed integration coverage later, gate it behind a separate workflow or manual dispatch.
