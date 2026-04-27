---
last_mapped_date: 2026-04-27
---
# Coding Conventions

## Language Style
- Follows standard **PEP-8** styling guidelines. Variables and functions use `snake_case`; Classes and Pydantic models use `PascalCase`.
- Uses **Python Type Hinting** heavily throughout the service and model layers (e.g., `Optional[SongWithStats]`, `List[ChartRunEntry]`).

## Database and SQL
- Raw SQL queries are defined as explicit multiline strings within the respective `services/` modules rather than using an ORM like SQLAlchemy. 
- Uses `%s` string formatting placeholders in psycopg2 for all parameterized queries to safeguard against **SQL Injection**. Never uses f-strings to pass variables into SQL data queries directly.
- Read-heavy queries fetch raw dictionary rows and unpack them directly into Pydantic models (e.g., `Song(**rows[0])`).

## Error Handling
- Leverages optional typings (`Optional[T]`) for "Not Found" entity patterns (returning `None` instead of throwing exceptions).
- Context managers inside `db/connection.py` ensure PostgreSQL DB connections are properly yielded and released back to the pool in `try...finally` boundaries to prevent connection leaking.
