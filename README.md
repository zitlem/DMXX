# DMXX

Web-based DMX lighting controller with real-time fader control, scene management, and Art-Net output.

## Features

- **Fader Control** - Real-time DMX channel control with WebSocket updates
- **Fixture Library** - Define and manage fixture profiles
- **Patch Manager** - Assign fixtures to DMX addresses
- **Scenes** - Save and recall lighting states
- **Groups** - Group channels for master control
- **Input/Output** - Art-Net input and output configuration
- **Channel Mapping** - Remap DMX channels between universes
- **Remote API** - HTTP API for external integration
- **Multi-user Auth** - Profile-based access with IP whitelist support

## Requirements

- Python 3.10+
- Node.js 18+ (for building frontend)
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Quick Start

```bash
./start.sh
```

This will:
1. Build the frontend if needed
2. Install Python dependencies automatically (via uvx)
3. Start the server

Open http://localhost:8000 in your browser.

Default password: `dmxx`

## Configuration

Edit `config.json` to configure:

```json
{
  "password": "dmxx",
  "secret_key": "change-this-in-production",
  "ip_whitelist": [],
  "host": "0.0.0.0",
  "port": 8000
}
```

| Option | Description |
|--------|-------------|
| `password` | Login password |
| `secret_key` | JWT signing key (change in production) |
| `ip_whitelist` | IPs that bypass authentication (e.g., `["192.168.1.*"]`) |
| `host` | Bind address |
| `port` | Server port |

## Updating a deployment

On a machine where DMXX is a git checkout run by systemd:

```bash
cd /opt/DMXX && ./update.sh
```

It backs up the database, fast-forwards to `origin`, reinstalls Python
dependencies and rebuilds the frontend only if those inputs changed, restarts
the service and health-checks it. If the service does not come back healthy it
rolls back to the previous commit and restarts.

```bash
./update.sh --check         # report what an update would do, change nothing
./update.sh --force-build   # rebuild the frontend even if nothing changed
./update.sh --no-build      # skip the build (use the committed dist)
./update.sh --no-restart    # update files only
```

It refuses to run if the checkout has uncommitted changes — commit or stash
them first, so edits made directly on the deployment are never discarded.

`config.json` and `data/*.db` are deliberately untracked, so a pull never
overwrites a deployment's credentials or its live show database.

## Testing

```bash
pip install -r requirements-dev.txt && pytest   # backend
cd frontend && npm install && npm test          # frontend
```

See `tests/README.md` and `frontend/tests/README.md`.

## Manual Start

If you prefer not to use `start.sh`:

```bash
# Install dependencies
pip install -r backend/requirements.txt

# Build frontend (first time only)
cd frontend && npm install && npm run build && cd ..

# Start server
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Or with uvx (no pip install needed):

```bash
uvx --with-requirements backend/requirements.txt uvicorn backend.main:app
```

## Development

Run frontend in dev mode with hot reload:

```bash
cd frontend
npm run dev
```

Backend will need to run separately.
