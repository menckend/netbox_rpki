# Devrun Service Configuration Reference

This document records the explicitly configured non-NetBox services managed by [`devrun/`](/home/mencken/src/netbox_rpki/devrun).

Scope notes:

- This focuses on services outside the NetBox Django app itself.
- It excludes the NetBox runserver and RQ worker processes.
- It does not print generated secret values. It names where those values come from and where they are stored.
- Krill is included, but only the parts `devrun` actually manages are described as repo-owned configuration.

## Source Of Truth Files

- [`devrun/common.sh`](/home/mencken/src/netbox_rpki/devrun/common.sh)
- [`devrun/docker-compose.yml`](/home/mencken/src/netbox_rpki/devrun/docker-compose.yml)
- [`devrun/bootstrap-netbox.sh`](/home/mencken/src/netbox_rpki/devrun/bootstrap-netbox.sh)
- [`devrun/configure-routinator-validator.sh`](/home/mencken/src/netbox_rpki/devrun/configure-routinator-validator.sh)
- [`devrun/irrd/Dockerfile`](/home/mencken/src/netbox_rpki/devrun/irrd/Dockerfile)
- [`devrun/irrd/entrypoint.sh`](/home/mencken/src/netbox_rpki/devrun/irrd/entrypoint.sh)
- [`devrun/seed-irrd-data.sh`](/home/mencken/src/netbox_rpki/devrun/seed-irrd-data.sh)
- [`LOCAL_DEV_SETUP.md`](/home/mencken/src/netbox_rpki/LOCAL_DEV_SETUP.md)

## Shared Devrun State

`bootstrap-netbox.sh` creates or refreshes [`devrun/.env`](/home/mencken/src/netbox_rpki/devrun/.env) with these service-facing variables:

- `POSTGRES_DB=netbox`
- `POSTGRES_USER=netbox`
- `POSTGRES_PASSWORD=<generated from NETBOX_DATABASE_PASSWORD>`
- `ROUTINATOR_RTR_PORT=3323`
- `ROUTINATOR_HTTP_PORT=8323`
- `ROUTINATOR_METRICS_PORT=9556`
- `IRRD_DATABASE_NAME=irrd`
- `IRRD_DATABASE_USER=irrd`
- `IRRD_DATABASE_PASSWORD=<generated>`
- `IRRD_HTTP_PORT=6080`
- `IRRD_WHOIS_PORT=6043`
- `IRRD_SOURCE=LOCAL-IRR`
- `IRRD_OVERRIDE_PASSWORD=<generated>`

Generated secrets are stored in `~/.config/netbox-rpki-dev/credentials.env`. The generated values relevant to non-NetBox services are:

- `NETBOX_DATABASE_PASSWORD`
- `IRRD_DATABASE_PASSWORD`
- `IRRD_OVERRIDE_PASSWORD`

## Live Validation Snapshot

The values below were checked against running local instances on `2026-04-14` after the `devrun` environment was started.

Validation outcome:

- The documented Routinator, IRRd, and Krill listener values matched the running instances.
- No port or base-URL mismatches were found.
- The main documentation gaps were additional live Krill configuration details and some effective runtime details from Routinator and IRRd.

## PostgreSQL

Managed by Docker Compose as service `postgres`.

Explicit configuration:

- Image: `postgres:16`
- Container name: `netbox-rpki-postgres`
- Restart policy: `unless-stopped`
- Host bind: `127.0.0.1:5432:5432`
- Persistent volume: `postgres_data:/var/lib/postgresql/data`
- Database name: `netbox`
- Database user: `netbox`
- Database password: taken from `POSTGRES_PASSWORD` in `devrun/.env`
- Health check: `pg_isready -U $POSTGRES_USER -d $POSTGRES_DB`

Additional bootstrap behavior:

- `bootstrap-netbox.sh` grants schema ownership and `CREATE` on `public` to `netbox`.
- The same PostgreSQL container is also used by IRRd.
- The IRRd entrypoint creates or updates:
  - PostgreSQL role `irrd`
  - PostgreSQL database `irrd`
  - `pgcrypto` extension in the `irrd` database
  - schema ownership and privileges for the `irrd` database

Live validation:

- Running container name: `netbox-rpki-postgres`
- Effective Docker volume name: `devrun_postgres_data`
- PostgreSQL was accepting connections on `127.0.0.1:5432`

## Redis

Managed by Docker Compose as service `redis`.

Explicit configuration:

- Image: `redis:7-alpine`
- Container name: `netbox-rpki-redis`
- Restart policy: `unless-stopped`
- Host bind: `127.0.0.1:6379:6379`
- Command: `redis-server --save "" --appendonly no`
- Health check: `redis-cli ping`

Explicit usage split:

- NetBox tasks Redis DB: `0`
- NetBox caching Redis DB: `1`
- IRRd Redis DB: `2`

Operational note:

- Persistence is intentionally disabled for Redis in this environment.

## Routinator

Managed by Docker Compose as service `routinator`.

Explicit configuration:

- Image: `nlnetlabs/routinator:latest`
- Container name: `netbox-rpki-routinator`
- Restart policy: `unless-stopped`
- Repository cache volume: `routinator_cache:/home/routinator/.rpki-cache`
- Repository dir argument: `/home/routinator/.rpki-cache/repository`
- ASPA support: enabled via `--enable-aspa`

Container command:

```text
--repository-dir /home/routinator/.rpki-cache/repository
--enable-aspa
server
--rtr 0.0.0.0:3323
--http 0.0.0.0:8323
--http 0.0.0.0:9556
```

Host port bindings:

- RTR: `127.0.0.1:${ROUTINATOR_RTR_PORT}:3323` with default `3323`
- HTTP API/status: `127.0.0.1:${ROUTINATOR_HTTP_PORT}:8323` with default `8323`
- Metrics HTTP: `127.0.0.1:${ROUTINATOR_METRICS_PORT}:9556` with default `9556`

Derived local endpoints:

- Base URL: `http://127.0.0.1:8323`
- Status URL: `http://127.0.0.1:8323/api/v1/status`
- Metrics URL: `http://127.0.0.1:9556/metrics`

Readiness behavior:

- `devrun` treats HTTP `200` as ready.
- It also treats `503` as reachable during initial validation startup.

NetBox-side integration created by `devrun`:

- `configure-routinator-validator.sh` creates or updates a `ValidatorInstance` named `Local Routinator` by default.
- That object is written with:
  - `software_name="Routinator"`
  - `base_url=$ROUTINATOR_BASE_URL`

Live validation:

- Running container name: `netbox-rpki-routinator`
- Effective Docker volume name: `devrun_routinator_cache`
- The live status endpoint reported version `routinator/0.15.1`
- The live metrics endpoint on port `9556` was serving Prometheus metrics at `/metrics`
- Active trust anchors observed in the live status payload:
  - `afrinic`
  - `apnic`
  - `arin`
  - `lacnic`
  - `ripe`
- ASPA payloads were present in the live status response, which is consistent with `--enable-aspa`

## IRRd

Managed by Docker Compose as service `irrd`, built locally from [`devrun/irrd/Dockerfile`](/home/mencken/src/netbox_rpki/devrun/irrd/Dockerfile).

### Image Build

Explicit build choices:

- Base image: `python:3.12-slim`
- Installed system packages:
  - `build-essential`
  - `cargo`
  - `curl`
  - `gnupg`
  - `libffi-dev`
  - `libpq-dev`
  - `libssl-dev`
  - `pkg-config`
  - `postgresql-client`
- Runtime user/group:
  - user `irrd`
  - group `irrd`
- Python package installed into the image: `irrd==4.5.2`
- Post-install compatibility override:
  - `bcrypt` is force-reinstalled as `4.0.1` after the `irrd==4.5.2` install
  - reason: `irrd==4.5.2` pulls `bcrypt==4.3.0`, which emits a non-fatal `passlib` compatibility warning at runtime because `bcrypt.__about__` is missing there

### Container Wiring

Explicit Compose configuration:

- Container name: `netbox-rpki-irrd`
- Restart policy: `unless-stopped`
- Depends on healthy `postgres` and `redis`
- Persistent volume: `irrd_state:/var/lib/irrd`
- Host HTTP bind: `127.0.0.1:${IRRD_HTTP_PORT}:8000` with default `6080`
- Host whois bind: `127.0.0.1:${IRRD_WHOIS_PORT}:6043` with default `6043`
- Health check: `curl -fsS http://127.0.0.1:8000/v1/status/`

Environment passed into the container:

- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `IRRD_DATABASE_NAME`
- `IRRD_DATABASE_USER`
- `IRRD_DATABASE_PASSWORD`
- `IRRD_HTTP_PORT=8000`
- `IRRD_WHOIS_PORT=6043`
- `IRRD_EXTERNAL_HTTP_URL=http://127.0.0.1:${IRRD_HTTP_PORT}`
- `IRRD_SOURCE`
- `IRRD_OVERRIDE_PASSWORD`

Derived local endpoints:

- Base URL: `http://127.0.0.1:6080`
- Status URL: `http://127.0.0.1:6080/v1/status/`
- Whois port: `127.0.0.1:6043`

### Entrypoint-Owned IRRd Config

At startup, `entrypoint.sh` writes `/etc/irrd.yaml` with these explicit settings:

- `database_url=postgresql://irrd:<password>@postgres:5432/irrd`
- `redis_url=redis://redis:6379/2`
- `piddir=/var/lib/irrd/pids`
- `user=irrd`
- `group=irrd`
- status access list `local_status` allows all IPv4 and IPv6 sources
- HTTP server:
  - `interface: 0.0.0.0`
  - `port: 8000`
  - `workers: 1`
  - `url: http://127.0.0.1:6080`
- whois server:
  - `interface: 0.0.0.0`
  - `port: 6043`
  - `max_connections: 2`
- auth:
  - `gnupg_keyring=/var/lib/irrd/gnupg`
  - `override_password=<bcrypt hash of IRRD_OVERRIDE_PASSWORD>` when the password is present
- email:
  - footer: `Local IRRd development instance`
  - from: `irrd-dev@example.invalid`
  - recipient override: `irrd-dev@example.invalid`
  - smtp host: `localhost`
- RPKI:
  - `roa_source: null`
- compatibility:
  - `inetnum_search_disabled: true`
- default source list:
  - `LOCAL-IRR` by default
- source definition for `LOCAL-IRR` by default:
  - `authoritative: true`
  - `keep_journal: true`
  - `object_class_filter` includes:
    - `person`
    - `route`
    - `route6`
    - `route-set`
    - `as-set`
    - `aut-num`
    - `mntner`

Startup sequence owned by the entrypoint:

- Wait for PostgreSQL TCP reachability on `postgres:5432`
- Wait for Redis TCP reachability on `redis:6379`
- Ensure the `irrd` database role exists and has the configured password
- Ensure the `irrd` database exists and is owned by `irrd`
- Ensure `pgcrypto` exists in the `irrd` database
- Clear stale `*.pid` files from `/var/lib/irrd/pids`
  - reason: the PID directory lives on the persistent `irrd_state` volume, so stale PID files can survive restarts and block IRRd startup
- Run `irrd_database_upgrade`
- Start `irrd --foreground --config=/etc/irrd.yaml`

Live validation:

- Running container name: `netbox-rpki-irrd`
- Effective Docker volume name: `devrun_irrd_state`
- The generated live config at `/etc/irrd.yaml` matched the documented values for:
  - `database_url`
  - `redis_url`
  - HTTP port `8000`
  - whois port `6043`
  - `sources_default`
  - `sources.LOCAL-IRR`
- Effective behaviors observed from the live status and whois endpoints:
  - version `4.5.2`
  - `RPKI validation enabled: No`
  - `Scope filter enabled: No`
  - no NRTM configuration present for `LOCAL-IRR`
  - whois `!v` returned `IRRd -- version 4.5.2`
- Observed runtime notes:
  - the stale PID cleanup is required for reliable restarts with the persistent `irrd_state` volume
  - the previous `passlib`/`bcrypt` warning is eliminated once the image forces `bcrypt==4.0.1`
  - IRRd still logs status requests as `/v1/status/v1/status/` even when the health check and manual probes call `http://127.0.0.1:6080/v1/status/` directly and receive `200 OK`
  - treat that doubled-path log entry as an IRRd runtime quirk for now, not as a failing `devrun` probe

### Seeded Local Data

`seed-irrd-data.sh` seeds the local IRRd instance through `POST /v1/submit/` using the generated override password.

Explicit seed inputs:

- Fixture template: [`devrun/irrd/fixtures/local-authoritative.rpsl`](/home/mencken/src/netbox_rpki/devrun/irrd/fixtures/local-authoritative.rpsl)
- Source placeholder filled from `IRRD_SOURCE`
- Maintainer auth hash generated from `IRRD_OVERRIDE_PASSWORD`

## Krill

Krill is not defined in [`devrun/docker-compose.yml`](/home/mencken/src/netbox_rpki/devrun/docker-compose.yml). `devrun` only manages an external Krill workspace if it already exists.

Repo-owned Krill assumptions from `common.sh`:

- Workspace root default: `~/src/krill_for_netbox_rpki`
- Start script path: `~/src/krill_for_netbox_rpki/scripts/start-krill.sh`
- Stop script path: `~/src/krill_for_netbox_rpki/scripts/stop-krill.sh`
- PID file path: `~/src/krill_for_netbox_rpki/var/run/krill.pid`
- Process match pattern:
  - `~/src/krill_for_netbox_rpki/cargo-root/bin/krill -c ~/src/krill_for_netbox_rpki/etc/krill.conf`

Lifecycle behavior owned by `devrun`:

- `./dev.sh start` starts Krill only if the start and stop scripts are executable and Krill is not already running.
- `./dev.sh stop` calls the external stop script if the workspace is present.
- `status.sh` reports Krill as:
  - running
  - installed but stopped
  - not installed under the configured `KRILL_ROOT`

Important boundary:

- The repo does not generate `krill.conf`.
- The repo does not install the `krill` binary.
- The repo does not define Krill ports, storage layout, or certificates in code.

Documented external workspace details from [`LOCAL_DEV_SETUP.md`](/home/mencken/src/netbox_rpki/LOCAL_DEV_SETUP.md), not from repo-managed scripts:

- expected workspace files include `etc/krill.conf`, `cargo-root/bin/krill`, and helper scripts
- the currently documented local setup serves Krill on `https://localhost:3001/`
- the currently documented local setup stores data under `var/data`
- the currently documented local setup stores logs and PID files under `var/log` and `var/run`
- the currently documented local setup uses `krill 0.16.0`

Live validation from the running external workspace:

- Process command:
  - `/home/mencken/src/krill_for_netbox_rpki/cargo-root/bin/krill -c /home/mencken/src/krill_for_netbox_rpki/etc/krill.conf`
- Effective `krill.conf` values observed locally:
  - `ip = "127.0.0.1"`
  - `port = 3001`
  - `https_mode = "generate"`
  - `service_uri = "https://localhost:3001/"`
  - `storage_uri = "/home/mencken/src/krill_for_netbox_rpki/var/data/"`
  - `log_type = "file"`
  - `log_level = "info"`
  - `log_file = "/home/mencken/src/krill_for_netbox_rpki/var/log/krill.log"`
  - `pid_file = "/home/mencken/src/krill_for_netbox_rpki/var/run/krill.pid"`
  - `unix_socket_enabled = true`
  - `unix_socket = "/home/mencken/src/krill_for_netbox_rpki/var/run/krill.sock"`
  - an `admin_token` is configured in the file, but it is a secret and is not reproduced here
- Live endpoints confirmed:
  - `https://localhost:3001/stats/info` returned version `0.16.0`
  - `krillc health` against `https://localhost:3001` returned `Ok`

## Service Inventory Summary

Services directly managed by Docker Compose:

- PostgreSQL
- Redis
- Routinator
- IRRd

Externally managed service with `devrun` lifecycle hooks only:

- Krill
