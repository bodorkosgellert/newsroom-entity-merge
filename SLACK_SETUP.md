# Real Slack bot (Socket Mode — no ngrok required for events)

## 1. Create the Slack app

1. Open https://api.slack.com/apps → **Create New App** → **From scratch**
2. Name: `Newsroom Desk` → pick your workspace (use a **dev** workspace, not necessarily HackNight if installs are restricted)

## 2. Socket Mode

1. **Settings → Socket Mode** → Enable
2. **Token name** e.g. `newsroom` → Generate → copy **`xapp-...`**
3. Put in `.env`:
   ```
   SLACK_APP_TOKEN=xapp-...
   ```

## 3. Bot token + scopes

**OAuth & Permissions → Bot Token Scopes** add:

- `chat:write`
- `channels:history`
- `channels:read`
- `files:read`
- `commands`
- `app_mentions:read`

**Install to Workspace** → copy **`xoxb-...`** into `.env`:

```
SLACK_BOT_TOKEN=xoxb-...
```

## 4. Events

**Event Subscriptions** → Enable → Subscribe to bot events:

- `file_shared`

(Socket Mode: no Request URL / ngrok needed.)

## 5. Slash command (optional)

**Slash Commands** → Create `/newsroom`

## 6. Invite the bot

In Slack:

```
/invite @Newsroom Desk
```

## 7. Run

```bat
cd /d "c:\Users\galla\OneDrive\Documents\New project\newsroom-entity-merge"
pip install slack-bolt requests python-dotenv twelvelabs
python slack_bot.py
```

Then **upload an mp4** in that channel (try Mona Lisa, then a Flaco clip).
Bot replies with ticket routing. Indexing can take 30–90 seconds.

## About ngrok

You have ngrok installed. **You do not need it for Socket Mode.**

Use ngrok only if you prefer HTTP mode later (Event Request URL = `https://xxxx.ngrok-free.app/slack/events`). Socket Mode is simpler on a laptop.

## Simulated UI (no Slack account needed)

```bat
python demo.py
python view_slack.py
```

Opens `out\slack_view.html` with channel chat + **video previews** + tickets.
