# Release Checklist

## Code quality

- [ ] Run `pytest`
- [ ] Run `pytest -m integration` when test keys are available
- [ ] Run `pytest --cov=testcode --cov-report=term-missing`
- [ ] Run `ruff check .`
- [ ] Review `mypy` output if type checking is enabled

## Configuration

- [ ] Verify `config/settings.example.yaml` matches the documented options
- [ ] Verify `.env.example` includes all required variables
- [ ] Ensure no secrets are committed

## Deployment

- [ ] Build the Docker image successfully
- [ ] Start the stack with `docker compose up --build`
- [ ] Confirm Redis cache fallback works when Redis is unavailable
- [ ] Confirm `n8n` webhook URLs are correct for the target environment

## Documentation

- [ ] Update `README.md` for user-facing changes
- [ ] Update `CONTRIBUTING.md` for new extension points
- [ ] Update `docs/` for workflow or deployment changes

## Release artifacts

- [ ] Save generated reports to `artifacts/`
- [ ] Publish versioned release notes if needed
