import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
BOT_TOKEN = os.environ["BOT_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

# Brand
BRAND_NAME = "CHANGER CLUB"
LOGO_TEXT = "CHANGER CLUB"

# Instagram format
SLIDE_WIDTH = 1080
SLIDE_HEIGHT = 1350

# Paths
PHOTOS_DIR = "photos"
TRANSCRIPTIONS_DIR = "transcriptions"
OUTPUT_DIR = "output"
FONTS_DIR = "fonts"

# OpenAI model (vision capable)
OPENAI_MODEL = "gpt-4o"

# Max slides per carousel
MAX_SLIDES = 10

# Knowledge base
KNOWLEDGE_CONTEXT_CHARS = 3000
