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
