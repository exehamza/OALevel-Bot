import discord
from discord.ext import commands
import sqlite3
from datetime import datetime, timedelta

class RepCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "database.sqlite"
        self.init_db()
        # In-memory cooldown tracking: {(author_id, replied_user_id): expiry_datetime}
        self.cooldowns = {}

    def init_db(self):
        """Ensures the reputation table exists in the database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_rep (
                    user_id INTEGER PRIMARY KEY,
                    rep_count INTEGER DEFAULT 0
                )
            """)
            conn.commit()

    def update_rep(self, user_id: int) -> int:
        """Increments a user's reputation and returns their new total."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Insert if new, or increment if they already exist
            cursor.execute("""
                INSERT INTO user_rep (user_id, rep_count)
                VALUES (?, 1)
                ON CONFLICT(user_id) DO UPDATE SET rep_count = rep_count + 1
            """, (user_id,))
            conn.commit()
            
            # Fetch new total
            cursor.execute("SELECT rep_count FROM user_rep WHERE user_id = ?", (user_id,))
            return cursor.fetchone()[0]

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bots and messages that aren't replies
        if message.author.bot or not message.reference:
            return

        # Check if the message content starts with or matches thank you phrases
        content_clean = message.content.lower().strip()
        triggers = ["thank", "ty", "thx", "thnks"]
        
        # Matches if the text starts with any trigger word/phrase
        if not any(content_clean.startswith(trigger) for trigger in triggers):
            return

        try:
            # Fetch the actual message being replied to
            if message.reference.cached_message:
                replied_message = message.reference.cached_message
            else:
                replied_message = await message.channel.fetch_message(message.reference.message_id)
        except (discord.NotFound, discord.HTTPException):
            return

        # Prevent thanking yourself or a bot
        if replied_message.author.id == message.author.id or replied_message.author.bot:
            return

        # Cooldown check: Has this user thanked the same person in the last 5 minutes?
        cooldown_key = (message.author.id, replied_message.author.id)
        now = datetime.utcnow()

        if cooldown_key in self.cooldowns:
            expiry = self.cooldowns[cooldown_key]
            if now < expiry:
                return

        # Update cooldown and database
        self.cooldowns[cooldown_key] = now + timedelta(minutes=5)
        new_rep = self.update_rep(replied_message.author.id)

        embed = discord.Embed(description=f"🌟 {replied_message.author.mention} gained +1 Rep!\nTotal Rep(s): **{new_rep}**", color=0xFFD700)

        await message.channel.send(embed=embed)

async def setup(bot):
    await bot.add_cog(RepCog(bot))