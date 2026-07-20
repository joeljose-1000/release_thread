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
| `TEAM_MEMBERS` | No | `""` | Comma-separated team member names for assignee matching (e.g. `Joel Jose,Sharooq Farzeen A K`) |

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
    parser_utils.py       # Shared patterns, date helpers, ticket/item extraction
    initial_parser.py     # Initial thread parsing (release metadata, ETAs)
    update_parser.py      # Live edit parsing (add/remove, PIC, date/ETA updates)
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
  test_parser_utils.py
  test_initial_parser.py
  test_update_parser.py
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

Feature:

1. <https://linear.app/company/issue/ENG-333|Add dark mode> - @raj

Bugs and Improvements:

1. <https://linear.app/company/issue/ENG-101|Fix onboarding crash> - @raj
2. <https://linear.app/company/issue/ENG-222|Improve retry handling> - @john

Dev ETA : TBD
Prod ETA : TBD
```

Ticket titles are clickable Slack hyperlinks. Raw URLs are never visible. Each category has its own independent numbering. All items default to "Bugs and Improvements" and can be moved to other categories (e.g. Feature) via thread commands. The release/hotfix date in the header is always kept in sync with the Prod ETA date.

---

## Live Thread Updates

After a release summary is posted, you can update it by sending messages in the same thread. The bot parses the message, updates the summary in place, and reacts with ✅.

### Change PIC

| Format | Example |
|--------|---------|
| `PIC: @name` | `PIC: @sharooq` |
| `PIC is @name` | `PIC is @javad` |
| `change PIC to @name` | `change PIC to @sharooq` |
| `update PIC to @name` | `update PIC to @javad` |
| `set PIC to @name` | `set PIC to @alexander` |
| `PIC changed to @name` | `PIC changed to @sharooq` |

### Change Release Date

| Format | Example |
|--------|---------|
| `release date is <date>` | `release date is 22nd June` |
| `release date: <date>` | `release date: Thursday` |
| `change release date to <date>` | `change release date to next Friday` |
| `release moved to <date>` | `release moved to 20th May` |
| `release planned for <date>` | `release planned for June 22` |
| `release date changed to <date>` | `release date changed to Thursday` |

### Update Dev ETA

| Format | Example |
|--------|---------|
| `dev eta: <date/time>` | `dev eta: Monday 9am` |
| `dev eta <date/time>` | `dev eta May 20 12pm` |
| `dev eta is <date/time>` | `dev eta is TBD` |
| `change dev eta to <date/time>` | `change dev eta to 15 May 9am` |
| `update dev eta to <date/time>` | `update dev eta to 20 May` |
| `dev eta changed to <date/time>` | `dev eta changed to Monday 3pm` |

### Update Prod ETA

Same patterns as Dev ETA, using `prod eta` or `production eta`:

| Format | Example |
|--------|---------|
| `prod eta: <date/time>` | `prod eta: Wednesday 3pm` |
| `production eta updated to <date/time>` | `production eta updated to 16 May 4pm` |
| `set prod eta to <date/time>` | `set prod eta to TBD` |

### Add Tickets

| Format | Example |
|--------|---------|
| Ticket ID | `ENG-123` |
| Multiple IDs | `ENG-123 and PLAT-456` |
| Linear URL | `https://linear.app/team/issue/ENG-789/fix-something` |

### Add Plain Items

| Format | Example |
|--------|---------|
| Bulleted | `- Fix caching layer` |
| Numbered | `1. Fix caching layer` |

### Add Items with Category Headers

You can post items under explicit category headers. The bot recognises `Feature:`, `Features:`, `Bug:`, `Fixes:`, `Improvements:`, and `Bugs and Improvements:` as headers and assigns items below them to the matching category. Items before any header default to "Bugs and Improvements".

```
Feature:
Agent mode - candidate assistant

Fixes:
Questions changed for paused interview
Candidate Assistant Issue
```

This also works with Linear URLs:

```
feature:
https://linear.app/team/issue/WHA-2524/interview-reschedule

bug:
https://linear.app/team/issue/WHA-2564/proctoring-tab-missing
```

Category headers are supported both in the initial thread messages (parsed by `/release`) and in live thread replies.

### Categorize Items as Features

All items start under **Bugs and Improvements**. You can move items to **Features** using these formats. Item numbers refer to the position within the Bugs and Improvements list. Each category gets its own independent numbering in the summary. Only "Feature" / "Features" is supported as a target category.

**By item number:**

| Format | Example |
|--------|---------|
| `item <N> as Feature` | `item 7 as Feature` |
| `move item <N> to Feature` | `move item 2 to Feature` |
| `items <N>, <N> as Feature` | `items 1, 3, 5 as Feature` |
| `#<N> as Feature` | `#7 as Feature` |

**By ticket ID:**

| Format | Example |
|--------|---------|
| `<ID> as Feature` | `ENG-123 as Feature` |
| `mark <ID> as Feature` | `mark ENG-123 as Feature` |
| `<ID>, <ID> as Feature` | `ENG-123, PLAT-456 as Feature` |

### Mark as Hotfix

If the release is a hotfix, the header changes from **RELEASE** to **HOTFIX**. This is detected automatically if the initial thread message contains the word "hotfix", or can be set via a thread reply:

| Format | Example |
|--------|---------|
| `hotfix` | `hotfix` |
| `this is a hotfix` | `this is a hotfix` |
| `mark as hotfix` | `mark as hotfix` |
| `change to hotfix` | `change to hotfix` |

### Remove Items

**By ticket ID:**

| Format | Example |
|--------|---------|
| `remove <ID>` | `remove ENG-123` |
| `drop <ID>` | `drop ENG-123 and ENG-456` |
| `delete <ID>` | `delete ENG-200` |
| `exclude <ID>` | `exclude ENG-300` |
| `take out <ID>` | `take out ENG-400` |

**By item number:**

| Format | Example |
|--------|---------|
| `remove item <N>` | `remove item 2` |
| `remove item <N> and <N>` | `remove item 2 and 3` |
| `remove items <N>, <N>, <N>` | `remove items 1, 4, 5` |
| `remove #<N> and #<N>` | `remove #2 and #3` |
| `drop item <N>` | `drop item 3 from the release` |

**By description:**

| Format | Example |
|--------|---------|
| `remove <text>` | `remove fix login page` |
| `drop <text>` | `drop the admin whitelist fix` |

### Supported Date Formats

All date fields (release date, dev/prod ETA) accept:

| Format | Example |
|--------|---------|
| Day name | `Monday`, `Thursday` |
| With prefix | `next Friday`, `this Wednesday` |
| Fuzzy day name | `thrusday` → Thursday |
| Ordinal only | `12th`, `22nd` (current or next month) |
| Day + month | `27th May`, `May 21`, `June 22` |
| Date + time | `15 May 9am`, `Monday 3pm` |
| TBD | `TBD` |

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
