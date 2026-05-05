# Release Assistant

A Slack-integrated agent that reads thread conversations, extracts Linear ticket references (from text, URLs, and screenshots via OCR), fetches ticket details from Linear's GraphQL API, and posts a formatted release summary back into the thread.

## Features

- `/release` slash command for Slack
- Extracts ticket IDs from plain text, Linear URLs, and image screenshots
- Modular OCR: EasyOCR, Tesseract, or OpenAI Vision
- Async-first architecture with FastAPI and slack_bolt
- Formatted release summary with clickable links, assignees, and PIC
- Structured logging, retry logic, and health checks

## Quick Start

### 1. Clone and configure

```bash
cp .env.example .env
# Edit .env with your actual tokens (see sections below)
```

### 2. Run with Docker

```bash
docker compose up --build
```

### 3. Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

The server starts on `http://localhost:3000`.

---

## Slack App Setup

### Create the Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and click **Create New App**.
2. Choose **From an app manifest** and paste the manifest below, or configure manually.

### App Manifest

**Option A: HTTP mode** (replace `YOUR_DOMAIN` with your actual domain):

```yaml
_metadata:
  major_version: 1
  minor_version: 1
display_information:
  name: Release Assistant
  description: Generates release summaries from thread conversations
features:
  bot_user:
    display_name: Release Bot
    always_online: true
  slash_commands:
    - command: /release
      url: https://YOUR_DOMAIN/slack/commands
      description: Generate a release summary from this thread
      usage_hint: "[thread_ts]"
      should_escape: false
oauth_config:
  scopes:
    bot:
      - channels:history
      - chat:write
      - commands
      - files:read
      - groups:history
      - im:history
      - mpim:history
settings:
  org_deploy_enabled: false
  socket_mode_enabled: false
  token_rotation_enabled: false
```

**Option B: Socket Mode** (no public URL needed — recommended for local dev):

```yaml
_metadata:
  major_version: 1
  minor_version: 1
display_information:
  name: Release Assistant
  description: Generates release summaries from thread conversations
features:
  bot_user:
    display_name: Release Bot
    always_online: true
  slash_commands:
    - command: /release
      description: Generate a release summary from this thread
      usage_hint: "[thread_ts]"
      should_escape: false
oauth_config:
  scopes:
    bot:
      - channels:history
      - chat:write
      - commands
      - files:read
      - groups:history
      - im:history
      - mpim:history
settings:
  org_deploy_enabled: false
  socket_mode_enabled: true
  token_rotation_enabled: false
```

> With Socket Mode, slash commands don't need a URL — Slack routes them over a
> WebSocket connection. After creating the app, generate an **App-Level Token**
> with `connections:write` scope and set `SLACK_APP_TOKEN` and
> `SLACK_SOCKET_MODE=true` in your `.env`.

### Required Bot Scopes

| Scope | Purpose |
|-------|---------|
| `channels:history` | Read messages in public channels |
| `chat:write` | Post release summaries |
| `commands` | Handle `/release` slash command |
| `files:read` | Download image attachments for OCR |
| `groups:history` | Read messages in private channels |
| `im:history` | Read direct messages |
| `mpim:history` | Read group direct messages |

### Slash Command Configuration

- **Command**: `/release`
- **Request URL**: `https://YOUR_DOMAIN/slack/commands`
- **Short Description**: Generate a release summary from this thread

### Socket Mode (alternative)

If you prefer not to expose a public URL:

1. Enable **Socket Mode** in your app settings.
2. Generate an **App-Level Token** with `connections:write` scope.
3. Set in `.env`:
   ```
   SLACK_APP_TOKEN=xapp-...
   SLACK_SOCKET_MODE=true
   ```
4. Run `python -m app.main` — no public URL needed.

### Installation

1. Install the app to your workspace via **OAuth & Permissions**.
2. Copy the **Bot User OAuth Token** (`xoxb-...`) to `SLACK_BOT_TOKEN`.
3. Copy the **Signing Secret** from **Basic Information** to `SLACK_SIGNING_SECRET`.

---

## Linear Setup

### API Key

1. Go to [linear.app/settings/api](https://linear.app/settings/api).
2. Click **Create key** under Personal API keys.
3. Copy the key to `LINEAR_API_KEY` in your `.env`.

### Permissions

The API key inherits your user permissions. Ensure you have read access to the teams whose tickets you want to include.

### GraphQL API

- **Endpoint**: `https://api.linear.app/graphql`
- **Auth header**: `Authorization: <API_KEY>`
- **Rate limits**: 1,500 requests per hour. The agent uses bounded concurrency and exponential backoff to stay within limits.
- **Pagination**: Handled automatically for thread messages. Linear queries use `first: 1` per identifier (no pagination needed).

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SLACK_BOT_TOKEN` | Yes | — | Bot OAuth token (`xoxb-...`) |
| `SLACK_SIGNING_SECRET` | Yes | — | App signing secret |
| `SLACK_APP_TOKEN` | No | `""` | App-level token for Socket Mode (`xapp-...`) |
| `SLACK_SOCKET_MODE` | No | `false` | Enable Socket Mode |
| `LINEAR_API_KEY` | Yes | — | Linear personal API key |
| `LINEAR_COMPANY_SLUG` | No | `company` | Company slug in Linear URLs |
| `OPENAI_API_KEY` | No | `""` | Required only for Vision OCR provider |
| `OCR_PROVIDER` | No | `easyocr` | `easyocr`, `tesseract`, or `vision` |
| `PORT` | No | `3000` | Server port |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `FALLBACK_MESSAGE_COUNT` | No | `20` | Messages to scan outside a thread |

---

## Architecture

```
app/
  main.py                 # FastAPI + Bolt entrypoint
  config/settings.py      # Pydantic Settings with .env
  api/health.py           # GET /health
  slack/
    commands.py           # /release handler
    thread.py             # Thread message fetcher
    formatter.py          # Slack mrkdwn builder
  linear/
    client.py             # Async GraphQL client
    queries.py            # GraphQL query strings
    models.py             # Linear response models
  ocr/
    base.py               # OCRProvider protocol
    tesseract.py          # Tesseract provider
    easyocr_provider.py   # EasyOCR provider
    vision.py             # OpenAI Vision provider
    factory.py            # Provider factory
  parsers/
    ticket_parser.py      # Regex extraction
    image_parser.py       # Image download + OCR
  services/
    release_service.py    # Orchestrator
    pic_service.py        # PIC calculation
  models/
    ticket.py             # TicketInfo model
    release.py            # ReleaseSummary model
  utils/
    logging.py            # structlog setup
    retry.py              # tenacity retry decorator
tests/
  test_ticket_parser.py
  test_pic_service.py
  test_formatter.py
  test_linear_client.py
```

### Flow

1. User types `/release` in a Slack thread
2. Bolt acknowledges immediately, dispatches async task
3. Thread messages are fetched (text + file attachments)
4. Ticket IDs extracted via regex from text/URLs
5. Images downloaded and processed through OCR provider
6. All unique IDs fetched from Linear GraphQL API
7. PIC determined (assignee with most tickets)
8. Formatted release summary posted back into the thread

---

## Release Summary Format

```
:round_pushpin: RELEASE May 4

PIC: @raj

Bugs and Improvements:

1. <https://linear.app/company/issue/ENG-101|Fix onboarding crash> - @raj
2. <https://linear.app/company/issue/ENG-222|Improve retry handling> - @john

Dev ETA : TBD
Prod ETA : TBD
```

Ticket titles are clickable Slack hyperlinks. Raw URLs are never visible.

---

## OCR Providers

| Provider | Pros | Cons |
|----------|------|------|
| **EasyOCR** (default) | Good accuracy, no system deps beyond Python | Slower, larger memory footprint |
| **Tesseract** | Fast, lightweight | Requires system package `tesseract-ocr` |
| **Vision** | Best accuracy | Requires OpenAI API key, costs per request |

Set `OCR_PROVIDER` in `.env` to switch.

---

## Testing

```bash
pip install -r requirements.txt
pytest tests/ -v
```

---

## Deployment

### Docker

```bash
docker compose up --build -d
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: release-agent
spec:
  replicas: 1
  selector:
    matchLabels:
      app: release-agent
  template:
    metadata:
      labels:
        app: release-agent
    spec:
      containers:
        - name: release-agent
          image: your-registry/release-agent:latest
          ports:
            - containerPort: 3000
          envFrom:
            - secretRef:
                name: release-agent-secrets
          livenessProbe:
            httpGet:
              path: /health
              port: 3000
            initialDelaySeconds: 10
            periodSeconds: 30
---
apiVersion: v1
kind: Service
metadata:
  name: release-agent
spec:
  selector:
    app: release-agent
  ports:
    - port: 80
      targetPort: 3000
```

### Railway / Render

1. Connect your repository.
2. Set the build command: `pip install -r requirements.txt`
3. Set the start command: `uvicorn app.main:api --host 0.0.0.0 --port $PORT`
4. Add environment variables from `.env.example`.

### Google Cloud Run

```bash
gcloud builds submit --tag gcr.io/PROJECT/release-agent
gcloud run deploy release-agent \
  --image gcr.io/PROJECT/release-agent \
  --port 3000 \
  --set-env-vars "SLACK_BOT_TOKEN=xoxb-..." \
  --allow-unauthenticated
```

### AWS ECS

1. Push the Docker image to ECR.
2. Create a task definition with the container image, port 3000, and environment variables.
3. Create a service in your ECS cluster with the task definition.
4. Attach an ALB targeting port 3000.

---

## Linting and Formatting

```bash
pip install ruff mypy
ruff check app/ tests/
ruff format app/ tests/
mypy app/
```
