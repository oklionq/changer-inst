# Changer Club — AI Content Factory

Telegram bot that turns event photos + a topic into branded Instagram carousel slides.

Built for **Changer Club** — a private wealth club for ultra-high-net-worth entrepreneurs and investors (5M+ liquid assets). Geography: Dubai, Monaco.

---

## How It Works

1. Send photos from an event (or pick from the on-disk library via `/gallery`)
2. Type a topic or theme
3. The bot calls **Claude** with the photos + event transcription context
4. Claude generates headline / subtitle / caption for each slide
5. **Pillow** renders each slide: dark gradient overlay, serif typography, brand logo
6. Bot sends the finished carousel back as a Telegram media group

---

## Project Structure

```
changer_bot/
├── bot.py               # Telegram bot entry point (aiogram 3.x)
├── generator.py          # Claude API — slide text generation
├── image_maker.py        # Pillow — photo + text overlay rendering
├── knowledge_base.py     # Loads transcriptions for context injection
├── config.py             # Settings, paths, constants
├── prompts.py            # All LLM prompts (edit without touching logic)
├── fonts/                # Auto-downloaded Playfair Display fonts
├── photos/               # Event photo library
├── transcriptions/       # Event transcription .txt files
├── output/               # Temporary rendered slides
├── requirements.txt
├── .env.example
└── README.md
```

---

## Installation

### Prerequisites

- Python 3.10+
- A Telegram Bot Token (get from [@BotFather](https://t.me/BotFather))
- An Anthropic API key (https://console.anthropic.com)

### Step by step

```bash
# 1. Clone or copy the project
cd changer_bot

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate      # Linux/macOS
# or: venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env file
cp .env.example .env
# Edit .env — add your BOT_TOKEN and ANTHROPIC_API_KEY

# 5. Add photos to photos/ and transcriptions to transcriptions/

# 6. Run the bot
python bot.py
```

---

## Usage

### Scenario 1 — Upload photos

1. Open the bot in Telegram
2. Send 1–10 photos (as compressed images or as file attachments)
3. Type the topic, e.g. "Family office strategies discussed at Dubai dinner"
4. Receive carousel slides + caption + hashtags

### Scenario 2 — Pick from library

1. Send `/gallery`
2. The bot lists all photos in the `photos/` directory
3. Reply with numbers: `1, 4, 7`
4. Type the topic
5. Receive carousel slides

### Other commands

| Command   | Description                  |
|-----------|------------------------------|
| `/start`  | Welcome message + help       |
| `/gallery`| Browse photo library         |
| `/reset`  | Clear current session        |
| `/help`   | Quick reference              |

---

## Adding Transcriptions

Drop `.txt` files into the `transcriptions/` directory. They are loaded on bot startup and used as context for Claude when generating slide text. The knowledge base scores documents by keyword overlap with the user's topic.

Example files:
- `Changer Dubai April.txt`
- `Changer Riga May.txt`

No special formatting required — plain text is fine.

---

## Customising Slide Design

Edit `image_maker.py` to change:

| What                 | Where                           |
|----------------------|---------------------------------|
| Slide dimensions     | `config.py` → `SLIDE_WIDTH/HEIGHT` |
| Gradient intensity   | `_apply_dark_gradient()` — alpha formula |
| Gradient start point | `start_y = int(h * 0.28)` — lower = later start |
| Logo position        | `_draw_logo()` → `ly = int(h * 0.050)` |
| Headline font size   | `_draw_text_block()` → `hl_size = int(w * 0.082)` |
| Subtitle font size   | `_draw_text_block()` → `sub_size = int(w * 0.037)` |
| Text start position  | `y = int(h * 0.595)` |
| Fonts                | Replace files in `fonts/` directory |

---

## Editing Prompts

All LLM prompts live in `prompts.py`. Edit them without touching any business logic:

- `SYSTEM_PROMPT` — brand voice, rules, examples
- `SLIDE_GENERATION_TEMPLATE` — per-request instructions with placeholders

---

## API Cost Estimate

Per carousel generation (assuming 5 slides with photos):

| Component                | Cost (approx.)     |
|--------------------------|-------------------|
| Claude Opus input (5 photos + context) | ~$0.30–0.60  |
| Claude Opus output (~1500 tokens)      | ~$0.10–0.20  |
| **Total per carousel**                 | **~$0.40–0.80** |

To reduce costs, set `USE_FAST_MODEL=true` in `.env` to use Claude Sonnet instead (~3–5x cheaper).

---

## Environment Variables

| Variable           | Required | Description                          |
|--------------------|----------|--------------------------------------|
| `BOT_TOKEN`        | Yes      | Telegram bot token from @BotFather   |
| `ANTHROPIC_API_KEY`| Yes      | Anthropic API key                    |
| `USE_FAST_MODEL`   | No       | `true` = Claude Sonnet, `false` (default) = Claude Opus |

---

## Troubleshooting

- **Font download fails**: The bot falls back to system fonts (Times New Roman on Windows, DejaVu on Linux). Slides will still render.
- **No transcriptions**: The bot works without context — Claude will generate based on the topic alone.
- **Claude returns invalid JSON**: The bot retries once automatically. If it fails again, you'll see an error message.
- **Photos too large**: Images >2048px on the long side are automatically resized before sending to Claude.
