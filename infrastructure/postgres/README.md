# infrastructure/postgres

PostgreSQL bootstrap and local tuning for the Lahore AQI platform.

| Path | Purpose |
|------|---------|
| `init/00_extensions.sql` | `pgcrypto` (and future extensions) |
| `init/01_schemas.sql` | Logical schemas (`raw`, `staging`, …) |
| `postgresql.conf` | Dev-oriented tuning for append-heavy tables |

**Table DDL is not defined here.** Compose runs Alembic via the `migrate` service before the consumer starts. From the host:

```bash
docker compose up -d
# or manually:
docker compose run --rm migrate alembic upgrade head
```

Credentials come from `.env` / `lahore_air_quality.config.Settings` — never hard-code passwords.
