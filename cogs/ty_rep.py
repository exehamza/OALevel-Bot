import discord
from discord.ext import commands
import sqlite3
from datetime import datetime, timedelta

class RepCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "database.sqlite"
        self.init_db()
        self.tick = "<:Tick:1514986183489360087>"
        self.cross = "<a:Cross:1514986232294281426>"
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

    @commands.command(name="rep")
    async def rep_check(self, ctx, member: discord.Member = None):
        """Checks your own reputation or another member's reputation."""
        target_member = member or ctx.author
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT rep_count FROM user_rep WHERE user_id = ?", (target_member.id,))
            result = cursor.fetchone()
            
        rep_count = result[0] if result else 0

        embed = discord.Embed(
            title="✨ Reputation Check",
            description=f"{target_member.mention} has **{rep_count}** reputation points.",
            color=0x3498db
        )
        await ctx.send(embed=embed)

    @commands.command(name="replb", aliases=["repleaderboard", "lbrep"])
    async def rep_leaderboard(self, ctx):
        """Displays the top 10 members with the most reputation."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, rep_count FROM user_rep ORDER BY rep_count DESC LIMIT 10")
            top_users = cursor.fetchall()

        if not top_users:
            embed = discord.Embed(
                description=f"{self.cross} The reputation leaderboard is currently empty! Start helping others to earn rep.",
                color=0xe74c3c
            )
            await ctx.send(embed=embed)
            return

        leaderboard_text = ""
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}

        for index, (user_id, rep_count) in enumerate(top_users, start=1):
            emoji = medals.get(index, "🔹")
            
            member = ctx.guild.get_member(user_id)
            if member:
                user_string = member.mention
            else:
                user_string = f"User ID: {user_id}"

            leaderboard_text += f"{emoji} **#{index}** | {user_string} — **{rep_count}** Rep\n"

        embed = discord.Embed(
            title="🏆 Reputation Leaderboard",
            description=leaderboard_text,
            color=0xFFD700
        )
        embed.set_footer(text="Abuse or farming of the rep system will result in consequences.")
        
        await ctx.send(embed=embed)

    @commands.command(name="setrep")
    @commands.has_permissions(administrator=True)
    async def set_rep(self, ctx, member: discord.Member, amount: int):
        """Sets a specific member's reputation amount (Admin only)."""
        if amount < 0:
            embed = discord.Embed(
                description=f"{self.cross} Reputation cannot be a negative number.",
                color=0xe74c3c
            )
            await ctx.send(embed=embed)
            return

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM user_rep WHERE user_id = ?", (member.id,))
            exists = cursor.fetchone()
            
            if exists:
                cursor.execute("UPDATE user_rep SET rep_count = ? WHERE user_id = ?", (amount, member.id))
            else:
                cursor.execute("INSERT INTO user_rep (user_id, rep_count) VALUES (?, ?)", (member.id, amount))
            conn.commit()

        # FIXED: Using self.tick correctly here
        embed = discord.Embed(
            description=f"{self.tick} Successfully set {member.mention}'s reputation to **{amount}**.",
            color=0x2ecc71
        )
        await ctx.send(embed=embed)

    @set_rep.error
    async def set_rep_error(self, ctx, error):
        color_err = 0xe74c3c
        
        # Local fallback string just in case self.cross fails
        cross_icon = getattr(self, "cross", "❌")
        
        if isinstance(error, commands.MissingPermissions):
            msg = f"{cross_icon} You do not have permission to use this command."
        elif isinstance(error, commands.MissingRequiredArgument):
            msg = f"{cross_icon} **Missing Arguments!**\nUsage: `$setrep @user [amount]`"
        elif isinstance(error, commands.BadArgument):
            msg = f"{cross_icon} **Invalid Argument!**\nMake sure you mention a valid user and provide a whole number for the amount."
        else:
            msg = f"{cross_icon} An error occurred: `{str(error)}`"
            
        embed = discord.Embed(description=msg, color=color_err)
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