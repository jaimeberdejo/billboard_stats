---
last_mapped_date: 2026-04-27
---
# Testing Practices

## Current State
- The codebase currently lacks a formal automated testing framework (`pytest` is not present in requirements nor is there an active `tests/` directory).
- Validation and schema enforcement is pushed largely onto **Pydantic** models instead of explicit unit checks for structured data flows.
- Tests (if any exist) are presumably run manually ad-hoc against the PostgreSQL instance or via visual regressions by interacting with the app (`app.py`).

## Future Implementations
- It is recommended to introduce `pytest` along with a test database and fixtures to exercise `services/` logic (which contains raw SQL text mappings) and `etl/` logic. 
