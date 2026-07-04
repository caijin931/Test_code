# Architecture

## Responsibilities

- `src/` contains the Python orchestration layer.
- `config/` stores runtime configuration for environments and providers.
- `scripts/` holds automation helpers for setup, release, and maintenance.
- `tests/` validates orchestration behavior and provider contracts.
- `artifacts/` stores generated output and intermediate deliverables.

## Workflow

1. Load configuration from `config/` and environment variables.
2. Validate workflow inputs with Pydantic models.
3. Route orchestration requests to the appropriate provider adapter.
4. Execute provider-specific actions in n8n, Dify, or Coze.
5. Log results and store generated outputs in `artifacts/` when needed.

## Mermaid diagram

```mermaid
flowchart TD
  A[User / CLI / Automation] --> B[Python Orchestration Layer]
  B --> C[Configuration Loader]
  B --> D[Validation Models]
  B --> E[Provider Router]
  E --> F[n8n Adapter]
  E --> G[Dify Adapter]
  E --> H[Coze Adapter]
  F --> I[Workflow Execution]
  G --> J[AI App / Prompt Automation]
  H --> K[Conversational Automation]
  I --> L[Artifacts and Logs]
  J --> L
  K --> L
```
