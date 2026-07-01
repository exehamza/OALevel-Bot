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
            cursor.execute("""
                INSERT INTO user_rep (user_id, rep_count)
                VALUES (?, 1)
                ON CONFLICT(user_id) DO UPDATE SET rep_count = rep_count + 1
            """, (user_id,))
            conn.commit()
            
            cursor.execute("SELECT rep_count FROM user_rep WHERE user_id = ?", (user_id,))
            return cursor.fetchone()[0]

    @commands.command(name="rep", aliases=["replb", "repleaderboard", "lbrep"])
    async def rep_leaderboard(self, ctx):
        """Displays the top 10 members with the most reputation."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Fetch the top 10 users ordered by highest reputation
            cursor.execute("SELECT user_id, rep_count FROM user_rep ORDER BY rep_count DESC LIMIT 10")
            top_users = cursor.fetchall()

        if not top_users:
            await ctx.send("The reputation leaderboard is currently empty! Start helping others to earn rep.")
            return

        leaderboard_text = ""
        # Medal emojis for the top 3 spots, default circle for the rest
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}

        for index, (user_id, rep_count) in enumerate(top_users, start=1):
            emoji = medals.get(index, "🔹")
            
            # Look up the user object so we can show their name/mention
            member = ctx.guild.get_member(user_id)
            if member:
                user_string = member.mention
            else:
                # Fallback to plain text ID if the member left the server
                user_string = f"User ID: {user_id}"

            leaderboard_text += f"{emoji} **#{index}** | {user_string} — **{rep_count}** Rep\n"

        embed = discord.Embed(
            title="🏆 Reputation Leaderboard",
            description=leaderboard_text,
            color=0xFFD700
        )
        embed.set_footer(text="Abuse or farming of the rep system will result in consequences.")
        
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bots and messages that aren't replies
        if message.author.bot or not message.reference:
            return

        content_clean = message.content.lower().strip()
        triggers = ["thank", "thx", "thnks"]
        
        if not any(content_clean.startswith(trigger) for trigger in triggers):
            return

        try:
            if message.reference.cached_message:
                replied_message = message.reference.cached_message
            else:
                replied_message = await message.channel.fetch_message(message.reference.message_id)
        except (discord.NotFound, discord.HTTPException):
            return

        if replied_message.author.id == message.author.id or replied_message.author.bot:
            return

        cooldown_key = (message.author.id, replied_message.author.id)
        now = datetime.utcnow()

        if cooldown_key in self.cooldowns:
            expiry = self.cooldowns[cooldown_key]
            if now < expiry:
                return

        self.cooldowns[cooldown_key] = now + timedelta(minutes=5)
        new_rep = self.update_rep(replied_message.author.id)

        embed = discord.Embed(
            description=f"🌟 {replied_message.author.mention} gained +1 Rep!\nTotal Rep(s): **{new_rep}**", 
            color=0xFFD700
        )
        embed.set_footer(text="Abuse or farming of the rep system will result in consequences.")

        await message.channel.send(embed=embed)

async def setup(bot):
    await bot.add_cog(RepCog(bot))