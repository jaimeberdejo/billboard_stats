---
last_mapped_date: 2026-04-27
---
# Integrations

## External Services
- **Billboard.com**: Uses the `billboard.py` unofficial API library to scrape and parse chart history data (Hot 100 and Billboard 200) from billboard.com.
- **Telegram Bot API**: Uses `python-telegram-bot` to interface with a custom Telegram Bot. Located in the `billboard_stats/bot/` directory, exposing queries and statistics to users through chat.

## Data Storage
- **PostgreSQL**: The single source of truth for the project. Raw JSON scraped from Billboard is parsed and loaded into a relational schema built with PostgreSQL. 
