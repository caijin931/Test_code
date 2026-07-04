# Contributing

Thank you for improving Testcode. This document explains how to extend the project safely.

## Development setup

1. Create a Python 3.11+ virtual environment.
2. Install development dependencies:

```bash
pip install -e .[dev]
```

3. Run tests before submitting changes:

```bash
pytest
```

## Adding a new testing task

1. Define the data contract in `src/testcode/models/`.
2. Implement the provider or orchestration logic in `src/testcode/`.
3. Add unit tests under `tests/` using mocks or stub transports.
4. If the task requires external APIs, mark those tests with `@pytest.mark.integration`.
5. Update `README.md` and any relevant docs when the workflow changes.

## Coding guidelines

- Keep provider-specific logic inside adapters.
- Prefer small, testable orchestration methods.
- Use structured data models for inputs and outputs.
- Preserve backward compatibility for public interfaces whenever possible.

## Pull request checklist

- Tests pass locally.
- New configuration is documented.
- User-facing CLI or workflow changes are reflected in the README.
- No secrets are committed to the repository.
