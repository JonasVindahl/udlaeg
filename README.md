# Udlæg

Self-hosted single-user app til at tracke udlæg jeg lægger ud for andre
(typisk mine forældre). FastAPI + HTMX + SQLite, med kvitteringsupload.

## Stack

Python 3.12 · FastAPI · SQLAlchemy 2 (async) · Alembic · SQLite (aiosqlite) ·
fastapi-users (cookie/JWT) · Jinja2 + HTMX · Prometheus · uv · ruff · pytest

## Quickstart (lokal udvikling)

```sh
uv sync
cp .env.example .env          # ret SECRET_KEY (se nedenfor)
mkdir -p db data/receipts data/backups
uv run alembic upgrade head
uv run python -m app.cli create-user dig@example.dk hemmeligt
uv run uvicorn app.main:app --reload
```

Appen kører på http://localhost:8000 — log ind på `/login`.

Generér en `SECRET_KEY`:

```sh
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

### Test, lint

```sh
uv run pytest
uv run ruff check .
uv run ruff format .
```

## Docker compose deployment

Bygges som image og køres i Proxmox Docker LXC (192.168.255.15),
eksponeres via Cloudflare Tunnel + Nginx Proxy Manager på
`udlaeg.jonasvindahl.dk`.

```sh
docker compose build
# .env skal ligge ved siden af docker-compose.yml
docker compose up -d
```

Bind-mounts (oprettes på LXC før første start):

| Host                    | Container             | Lager        |
|-------------------------|-----------------------|--------------|
| `/opt/udlaeg/db`        | `/app/db`             | lokal disk   |
| `/mnt/udlaeg/receipts`  | `/app/data/receipts`  | NFS          |
| `/mnt/udlaeg/backups`   | `/app/data/backups`   | NFS          |

Containeren kører som uid:gid `568:568`, så bind-mountede filer ikke
ejes af root. Sørg for at host-mapperne er ejet af `568:568`:

```sh
mkdir -p /opt/udlaeg/db /mnt/udlaeg/receipts /mnt/udlaeg/backups
chown -R 568:568 /opt/udlaeg/db /mnt/udlaeg/receipts /mnt/udlaeg/backups
```

`alembic upgrade head` køres automatisk i containerens entrypoint.

### Seed bruger

Ingen public registrering. Opret brugeren manuelt:

```sh
docker exec udlaeg python -m app.cli create-user dig@example.dk hemmeligt
```

### Manuel backup

```sh
docker exec udlaeg /app/scripts/backup.sh
```

### Cron på LXC (backup nat + rotation)

Lægges i LXC'ens crontab — ikke i containeren:

```cron
# Konsistent .backup hver nat kl. 03:15 (skrives til NFS)
15 3 * * * docker exec udlaeg /app/scripts/backup.sh >> /var/log/udlaeg-backup.log 2>&1

# Slet backups ældre end 14 dage
30 3 * * * find /mnt/udlaeg/backups -name 'udlaeg-*.db' -mtime +14 -delete
```

## Observability

- `GET /health` — `{"status":"ok","db":"ok"}` efter en `SELECT 1`.
- `GET /metrics` — Prometheus-metrics (prometheus-fastapi-instrumentator).
- Logging er JSON på stdout (`python-json-logger`), niveau via `LOG_LEVEL`.
  Auth-events, expense create/update/delete og file upload/delete logges.

Offentlige routes uden auth: `/login`, `/health`, `/metrics`, `/static/*`.
Alt andet kræver login-cookie (`udlaeg_session`, httponly, samesite=lax,
secure styret af `SESSION_COOKIE_SECURE`).

## Architecture decisions

**Hvorfor er SQLite splittet fra NFS?**
SQLite's fil-locking virker ikke pålideligt over NFS — samtidige writes
kan korruptere databasen. Derfor ligger den aktive DB på LXC'ens lokale
disk (`/opt/udlaeg/db`), mens kvitteringer og backups ligger på NFS.
`scripts/backup.sh` bruger `sqlite3 .backup`, som tager et konsistent
snapshot fra lokal disk og skriver det til NFS. Dermed ender databasen
alligevel på NFS hver nat — uden at den aktive fil nogensinde lever der.

**Status beregnes on read.** Der gemmes ingen status-kolonne. I stedet
udledes `pending` / `partial` / `paid` i `app/services/balance.py` ud fra
`sum(payments) vs expense.amount_dkk`. Saldo pr. person er summen af
restbeløb på udlæg der ikke er fuldt betalt. Det fjerner en hel klasse af
"status er ude af sync"-bugs.

## TODO / Bonus features

- **Magic-link til debitorer** så fx forældre kan se egen status uden
  fuld konto (fastapi-users understøtter token-flows let).
- **OCR** af kvitteringer: Tesseract lokalt først, med VLM-fallback via
  Open WebUI eller Claude API. `receipt.ocr_text`-kolonnen er allerede der.
- **PDF-eksport** af en "regning" til at sende.
- **MobilePay deep-link** på saldo-view.
- **Split** af ét udlæg på flere personer.
- **Recurring udlæg**.
- **Påmindelser** ved gamle ubetalte poster.
