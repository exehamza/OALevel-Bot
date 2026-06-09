import os
from dotenv import load_dotenv

# Force load the keys out of the hidden .env file into environment memory
load_dotenv()

class Config:
    TOKEN = os.getenv("DISCORD_TOKEN")
    DATABASE_URL = os.getenv("DB_NAME", "database.db")
    PREFIX = "$"
    EMBED_COLOR = 0x3498db
    BLOCKED_WORDS_FILE = os.path.join("data", "blocked_words.json")
    
    LOG_CHANNEL_ID = 1512792484764454946
    WELCOME_CHANNEL_ID = 1512790530403340540
    STAFF_APPLY_ID = 1513845175431204864
    STAFF_APPLICATIONS_ID = 1513845219588571176
    MODERATOR_ROLE_ID = 6767676767676767