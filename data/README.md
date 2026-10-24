# data/

Local data directories for development and debugging.

| Path | Purpose |
|------|---------|
| `raw/` | Optional local copies of raw payloads (production archive is object storage) |
| `processed/` | Intermediate local exports for analysis |
| `samples/` | Small, anonymized or publicly redistributable examples for docs/tests |

**Policy:** never commit secrets; never fabricate sensor readings as if they were live API responses. Large raw/processed files are gitignored.
