---
last_mapped_date: 2026-04-27
---
# Codebase Concerns

## Technical Debt & Architecture Fragility
1. **Raw SQL in Services**: The `services/` layer invokes raw, un-abstracted SQL queries (some large, multi-line) using string blocks throughout the codebase. While performant and direct for PostgreSQL features like `pg_trgm`, this creates fragility against schema refactors and makes the codebase reliant exclusively on psycopg2 and PostgreSQL.
2. **Lack of Automated Testing**: Complex queries, ETL gap repairs logic, and Streamlit state mutations are untested beyond Pydantic validation. The lack of standard test scripts (`pytest`) creates friction when refactoring core data processing pipelines safely.

## UX & Application Performance
3. **Database Dependency**: The Streamlit frontend performs direct database lookups for each click via synchronous functions. This may cause blocking in the UI main thread under heavy read operations or if the database sits on remote latency.
4. **State Management**: Streamlit relies on `st.rerun()` loops or mutations to `st.session_state["page"]`. Excessive navigation components or deeply nested views sharing the root `app.py` might compound maintenance burdens down the line without dedicated route encapsulation layers.
