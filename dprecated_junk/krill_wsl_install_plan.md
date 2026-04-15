# Krill WSL Installation Plan for `netbox_rpki`

**Prepared:** April 12, 2026  
**Target host shape:** WSL2 on Ubuntu 24.04 LTS  
**Install root:** `/home/mencken/src/krill_for_netbox_rpki`

## Goal

Stand up an isolated NLnet Labs Krill lab instance inside WSL for development of the `netbox_rpki` provider interfaces.

This plan is for a development-only delegated RPKI environment:

- isolated from system-wide Python packages
- isolated from `/usr` as much as practical
- reachable only on localhost
- easy to tear down and rebuild
- good enough to exercise Krill UI, CLI, and API behavior from the plugin

## Key Decisions

### 1. Use a dedicated Python virtual environment, but do not treat Krill as a Python package

Krill is a Rust application, not a Python package. The Python virtual environment should exist to isolate helper tooling used during provider development, for example:

- HTTP client scripts
- response capture tools
- adapter contract tests
- XML or JSON normalization helpers

The Krill binaries themselves should be installed under the same lab tree with Cargo.

### 2. Install Krill under the requested directory with Cargo, not `apt`

The official Ubuntu package is the simplest general install path, but it installs into system locations like `/usr`, `/etc`, and `/var/lib`. That conflicts with the requirement to keep this lab under `/home/mencken/src/krill_for_netbox_rpki`.

Use Cargo with a custom install root instead:

```bash
cargo install --locked --root /home/mencken/src/krill_for_netbox_rpki/cargo-root krill --version 0.16.0
```

That keeps `krill` and `krillc` under the requested tree and makes cleanup trivial.

### 3. Start as a child CA lab first, not as a full public RPKI service

For provider-interface development, the fastest useful shape is:

- local Krill instance in WSL
- one local CA
- localhost-only UI/API
- repository and parent wired to the NLnet Labs public Krill testbed, or another non-production parent later

This avoids building a public publication server, reverse proxy, and internet-reachable service URI before there is any plugin value.

### 4. Default to script-managed startup in WSL

This session is running on WSL2 Ubuntu 24.04, but PID 1 is not `systemd`. Because of that, the primary plan should use repo-local start/stop scripts. A secondary track can add systemd later if you want Krill to behave like a background service across WSL restarts.

## Target Layout

Use this filesystem layout:

```text
/home/mencken/src/krill_for_netbox_rpki/
  .venv/
  cargo-root/
    bin/
      krill
      krillc
  etc/
    krill.conf
    .env.krill
  var/
    data/
    run/
    log/
  state/
    publisher-request.xml
    repository-response.xml
    child-request.xml
    parent-response.xml
  scripts/
    start-krill.sh
    stop-krill.sh
    env.sh
```

## Implementation Plan

### Phase 1: Prepare the WSL host

Install the host dependencies Krill expects when built from source:

```bash
sudo apt update
sudo apt install -y \
  build-essential \
  libssl-dev \
  openssl \
  pkg-config \
  curl \
  git \
  python3-venv \
  jq
```

Install or update Rust with `rustup`, because current Krill documentation requires Rust 1.88 or newer.

### Phase 2: Create the lab root and Python environment

Create the requested root and the Python virtual environment:

```bash
mkdir -p /home/mencken/src/krill_for_netbox_rpki/{etc,var/data,var/run,var/log,state,scripts}
python3 -m venv /home/mencken/src/krill_for_netbox_rpki/.venv
```

Inside the venv, install only the development helpers you actually need. Initial candidates:

- `httpx`
- `requests`
- `pytest`
- `lxml`
- `pydantic`

Do not install NetBox or the plugin into this venv unless you later decide to use it for shared integration tooling.

### Phase 3: Install Krill into the custom root

After Rust is available, install a pinned Krill build into the custom root:

```bash
cargo install --locked \
  --root /home/mencken/src/krill_for_netbox_rpki/cargo-root \
  krill \
  --version 0.16.0
```

Expected result:

- `/home/mencken/src/krill_for_netbox_rpki/cargo-root/bin/krill`
- `/home/mencken/src/krill_for_netbox_rpki/cargo-root/bin/krillc`

If you later need to track an upstream fix instead of the crates.io release, switch to a tagged GitHub install for the same version line.

### Phase 4: Generate and harden a local-only config

Generate a starter config with `krillc config simple`, then edit it for a non-systemd, user-owned WSL layout.

Use a non-default port to reduce conflicts with any future local Krill instance:

```bash
/home/mencken/src/krill_for_netbox_rpki/cargo-root/bin/krillc \
  --token 'replace-me-with-a-real-token' \
  config simple \
  --data /home/mencken/src/krill_for_netbox_rpki/var/data/ \
  > /home/mencken/src/krill_for_netbox_rpki/etc/krill.conf
```

Then explicitly set or confirm these values in `krill.conf`:

```toml
ip = "127.0.0.1"
port = 3001
https_mode = "generate"
storage_uri = "/home/mencken/src/krill_for_netbox_rpki/var/data/"
service_uri = "https://localhost:3001/"
log_type = "file"
log_file = "/home/mencken/src/krill_for_netbox_rpki/var/log/krill.log"
pid_file = "/home/mencken/src/krill_for_netbox_rpki/var/run/krill.pid"
unix_socket_enabled = true
unix_socket = "/home/mencken/src/krill_for_netbox_rpki/var/run/krill.sock"
admin_token = "replace-me-with-a-real-token"
```

Why these overrides matter:

- `service_uri` must match the actual localhost URL and must end with a trailing slash
- `unix_socket` and `pid_file` should not live under `/run/krill` when not using the distro package or systemd
- `https_mode = "generate"` is appropriate for a localhost-only lab
- `log_type = "file"` is easier than syslog inside WSL

Store operator-facing variables in `etc/.env.krill`, for example:

```bash
export KRILL_BASE_URL='https://localhost:3001/'
export KRILL_CLI_SERVER='https://localhost:3001/'
export KRILL_CLI_TOKEN='replace-me-with-a-real-token'
export KRILL_VERIFY_TLS='false'
export KRILL_CA_HANDLE='netbox-rpki-dev'
```

### Phase 5: Add user-managed start and stop scripts

Use the Krill documentation's script-based startup model first.

`scripts/start-krill.sh` should:

- source `scripts/env.sh` or `etc/.env.krill`
- ensure `cargo-root/bin` is on `PATH`
- start `krill -c /home/mencken/src/krill_for_netbox_rpki/etc/krill.conf`
- write output to `var/log/krill.log`
- write the PID to `var/run/krill.pid`

`scripts/stop-krill.sh` should:

- read `var/run/krill.pid`
- stop the process cleanly
- remove the stale PID file if needed

This is enough for development and avoids the extra WSL/systemd branch immediately.

### Phase 6: Optional WSL systemd track

If you want Krill to behave more like a normal service in WSL, enable systemd in `/etc/wsl.conf`:

```ini
[boot]
systemd=true
```

Then restart WSL from Windows with:

```powershell
wsl.exe --shutdown
```

After that, either:

- keep the script-managed model, or
- create a dedicated service unit for the custom install root

This track is optional. It improves ergonomics, but it is not required to develop the NetBox provider adapter.

### Phase 7: Create the delegated CA lab

Once Krill is running:

1. Open `https://localhost:3001/`.
2. Authenticate with the admin token.
3. Create a CA handle such as `netbox-rpki-dev`.
4. Export the repository request XML and child request XML.
5. Use the NLnet Labs public testbed as the first non-production parent/repository backend.
6. Save the returned repository response XML and parent response XML in `state/`.
7. Import those XML responses into the local Krill CA.

This produces a realistic delegated-RPKI workflow without needing your own public repository service first.

## Plugin-Facing Development Plan

Once the local Krill instance exists, use it as the first live backend for the provider interface work:

### First adapter scope

Implement and validate these operations first:

- health check
- server info/version read
- CA listing
- ROA listing
- ROA create/update/delete
- import of repository and parent state only as far as the plugin model needs it

### Local development contract

Standardize on these adapter settings in local development:

- base URL: `https://localhost:3001/`
- auth: bearer token from `KRILL_CLI_TOKEN`
- TLS verification: disabled only for local self-signed development
- CA handle: `netbox-rpki-dev`

### Fixture capture

Use the Python venv to build small helper scripts that:

- call the Krill API
- persist normalized sample payloads under a fixtures directory
- record failure cases for adapter tests

That lets the plugin evolve from live experimentation to repeatable offline tests.

## Exit Criteria

Treat the plan as complete when all of the following are true:

1. `krill` and `krillc` run from `/home/mencken/src/krill_for_netbox_rpki/cargo-root/bin/`.
2. Krill starts without root and keeps all mutable state under `/home/mencken/src/krill_for_netbox_rpki/`.
3. `https://localhost:3001/health` responds successfully.
4. `krillc health` and `krillc info` succeed when pointed at `https://localhost:3001/`.
5. A local CA named `netbox-rpki-dev` exists.
6. The local CA is connected to a non-production parent/repository path.
7. The `netbox_rpki` code can exercise at least ROA read operations against the live Krill API.

## Risks and Follow-On Work

- If WSL remains non-systemd, background process management is slightly less convenient but still acceptable for development.
- If the public Krill testbed changes behavior, the local lab still remains useful for API exploration; only the delegated-parent portion needs adjustment.
- If provider work expands beyond ROAs into ASPA, manifests, or repository inventory, add fixture capture scripts early.
- If this lab becomes shared team infrastructure, move from localhost/self-signed TLS to a reverse-proxied internal hostname.

## References

- Krill install and run: https://krill.docs.nlnetlabs.nl/en/stable/install-and-run.html
- Krill build from source: https://krill.docs.nlnetlabs.nl/en/stable/building-from-source.html
- Krill CLI and API usage: https://krill.docs.nlnetlabs.nl/en/stable/cli.html
- Krill configuration options: https://krill.docs.nlnetlabs.nl/en/stable/config.html
- Krill getting started: https://krill.docs.nlnetlabs.nl/en/stable/get-started.html
- Krill child CA delegation: https://krill.docs.nlnetlabs.nl/en/stable/manage-children.html
- WSL systemd guidance: https://learn.microsoft.com/en-us/windows/wsl/systemd
- Cargo install root behavior: https://doc.rust-lang.org/cargo/commands/cargo-install.html
