import datetime
import re
import sqlite3
import discord
from discord.ext import commands
from config import Config

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "database.sqlite"
        self.init_db()

    def init_db(self):
        """Initializes the moderation cases table in database.sqlite if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mod_cases (
                case_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                user_id INTEGER,
                mod_id INTEGER,
                action_type TEXT,
                reason TEXT,
                duration TEXT,
                timestamp INTEGER
            )
        """)
        conn.commit()
        conn.close()

    def log_case(self, guild_id, user_id, mod_id, action_type, reason, duration=None):
        """Helper function to insert a history record into the database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        timestamp = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        cursor.execute("""
            INSERT INTO mod_cases (guild_id, user_id, mod_id, action_type, reason, duration, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (guild_id, user_id, mod_id, action_type, reason, duration, timestamp))
        conn.commit()
        conn.close()

    def parse_duration(self, duration_text):
        match = re.fullmatch(r"(\d+)([mhd]?)", duration_text.strip().lower())
        if not match:
            return None

        amount = int(match.group(1))
        unit = match.group(2) or "m"

        if unit == "m":
            return amount
        if unit == "h":
            return amount * 60
        if unit == "d":
            return amount * 1440
        return None

    async def send_mod_log(self, ctx, title, color, fields):
        if ctx.guild is None:
            return

        log_channel = ctx.guild.get_channel(Config.LOG_CHANNEL_ID)
        if log_channel is None:
            try:
                log_channel = await self.bot.fetch_channel(Config.LOG_CHANNEL_ID)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as error:
                print(f"Moderation log failed: could not fetch LOG_CHANNEL_ID {Config.LOG_CHANNEL_ID}. Error: {error}")
                return

        if getattr(log_channel, "guild", None) != ctx.guild:
            print(
                f"Moderation log failed: LOG_CHANNEL_ID {Config.LOG_CHANNEL_ID} "
                f"is not in the server '{ctx.guild.name}'."
            )
            return

        embed = discord.Embed(title=title, color=color)
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
        embed.set_footer(text=f"Command used in #{ctx.channel.name}")
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

        try:
            await log_channel.send(embed=embed)
        except discord.Forbidden:
            print(f"Moderation log failed: I cannot send messages/embeds in #{getattr(log_channel, 'name', Config.LOG_CHANNEL_ID)}.")
        except discord.HTTPException as error:
            print(f"Moderation log failed: Discord rejected the log message. Error: {error}")

    @commands.Cog.listener()
    async def on_ready(self):
        print("Moderation module loaded successfully.")

    # --- LOGS / HISTORY COMMAND ---
    @commands.command(name="logs", aliases=["history", "cases"], help="Shows moderation history for a specific user.")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def logs(self, ctx, target: discord.User | discord.Member):
        try: await ctx.message.delete()
        except discord.HTTPException: pass

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT case_id, mod_id, action_type, reason, duration, timestamp 
            FROM mod_cases 
            WHERE guild_id = ? AND user_id = ? 
            ORDER BY case_id DESC
        """, (ctx.guild.id, target.id))
        rows = cursor.fetchall()
        conn.close()

        embed = discord.Embed(
            title=f"Mod Logs for {target.name}",
            color=getattr(Config, "EMBED_COLOR", discord.Color.blue())
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        if not rows:
            embed.description = f"✨ {target.mention} has a completely clean record."
            return await ctx.send(embed=embed)

        embed.description = f"Found **{len(rows)}** total infraction record(s) for {target.mention}:\n\n"
        
        for case_id, mod_id, action_type, reason, duration, timestamp in rows:
            duration_str = f" ({duration})" if duration else ""
            case_details = (
                f"**Case #{case_id} — {action_type.upper()}{duration_str}**\n"
                f"**Moderator:** <@{mod_id}>\n"
                f"**Reason:** {reason}\n"
                f"**Date:** <t:{timestamp}:F> (<t:{timestamp}:R>)\n"
                f"{"—" * 20}"
            )
            # Avoid breaking embed limits (max 4096 characters in descriptions)
            if len(embed.description) + len(case_details) > 4000:
                embed.description += "*...and older records truncated due to character limits.*"
                break
            embed.description += case_details + "\n"

        await ctx.send(embed=embed)

    # --- PURGE COMMAND ---
    @commands.command(name="purge", aliases=["clear"], help="Purges a set number of messages from the channel, optionally filtered by user.")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge(self, ctx, arg1: discord.Member | int = None, arg2: int = None):
        target_member = None
        amount = 0

        if isinstance(arg1, discord.Member) and isinstance(arg2, int):
            target_member = arg1
            amount = arg2
        elif isinstance(arg1, int):
            amount = arg1

        # Validation checks
        if amount <= 0:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **Invalid format or amount.** Use one of the following:\n"
                            "`$purge [amount]`\n"
                            "`$purge [@user] [amount]`",
                color=discord.Color.red()
            )
            try: await ctx.message.delete()
            except discord.HTTPException: pass
            return await ctx.send(embed=embed, delete_after=5)

        if amount > 100:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **Please purge 100 messages or fewer at a time.**",
                color=discord.Color.red()
            )
            try: await ctx.message.delete()
            except discord.HTTPException: pass
            return await ctx.send(embed=embed, delete_after=5)

        # Delete the command invoking message first
        try: 
            await ctx.message.delete()
        except discord.HTTPException: 
            pass

        try:
            # If targeting a member, we look deeper into history to find their messages
            search_limit = 1000 if target_member else amount
            
            # Modern discord.py v2 way to flatten history instantly into memory
            messages = [msg async for msg in ctx.channel.history(limit=search_limit)]
            
            # Filter down to what we actually need to delete
            if target_member:
                to_delete = [msg for msg in messages if msg.author == target_member][:amount]
            else:
                to_delete = messages[:amount]

            actual_deleted = len(to_delete)

            # Bulk delete the list in one single API drop
            if actual_deleted > 0:
                await ctx.channel.delete_messages(to_delete)

        except discord.Forbidden:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **I need Manage Messages and Read Message History permissions.**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        except discord.HTTPException as e:
            embed = discord.Embed(
                description=f"<a:Cross:1514986232294281426> **Discord refused the purge.**\n*Error: {e.text}*",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed, delete_after=5)

        # Logging and Response Output
        embed_color = getattr(Config, "EMBED_COLOR", discord.Color.blue())
        user_str = f" sent by {target_member.mention}" if target_member else ""
        
        embed = discord.Embed(
            description=f"Successfully deleted **{actual_deleted}** messages{user_str}.",
            color=embed_color
        )
        await ctx.send(embed=embed, delete_after=5)

        log_fields = [
            ("Channel", ctx.channel.mention, True),
            ("Deleted Messages", str(actual_deleted), True),
            ("Moderator", ctx.author.mention, False)
        ]
        if target_member:
            log_fields.insert(1, ("Target User", target_member.mention, True))

        await self.send_mod_log(ctx, "Messages Purged", 0x3498db, log_fields)

    # --- KICK COMMAND ---
    @commands.command(name="kick", help="Kicks a member from the server.")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        try: await ctx.message.delete()
        except discord.HTTPException: pass

        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **You cannot kick someone with an equal or higher administrative role than yourself.**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        dm_embed = discord.Embed(
            title=f"👟 You have been kicked from {ctx.guild.name}",
            color=0xe67e22,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        dm_embed.add_field(name="Reason", value=reason, inline=False)
        try:
            await member.send(embed=dm_embed)
        except discord.Forbidden:
            pass

        await member.kick(reason=reason)
        self.log_case(ctx.guild.id, member.id, ctx.author.id, "kick", reason)

        embed = discord.Embed(title="Member Kicked", color=Config.EMBED_COLOR)
        embed.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=True)
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

        await ctx.send(embed=embed)
        
        await self.send_mod_log(
            ctx, 
            "Member Kicked", 
            0xe67e22, 
            [
                ("User", f"{member.mention} ({member.id})", False),
                ("Moderator", ctx.author.mention, True),
                ("Reason", reason, True)
            ]
        )

    # --- BAN COMMAND ---
    @commands.command(name="ban", help="Bans a member from the server.")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        try: await ctx.message.delete()
        except discord.HTTPException: pass

        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **You cannot ban someone with an equal or higher administrative role than yourself.**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        dm_embed = discord.Embed(
            title=f"🔨 You have been permanently banned from {ctx.guild.name}",
            color=0xe74c3c,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        dm_embed.add_field(name="Reason", value=reason, inline=False)
        try:
            await member.send(embed=dm_embed)
        except discord.Forbidden:
            pass

        await member.ban(reason=reason, delete_message_seconds=0)
        self.log_case(ctx.guild.id, member.id, ctx.author.id, "ban", reason)

        embed = discord.Embed(title="Member Banned", color=Config.EMBED_COLOR)
        embed.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=True)
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

        await ctx.send(embed=embed)
        await self.send_mod_log(
            ctx,
            "Member Banned",
            0xe74c3c,
            [
                ("User", f"{member.mention} ({member.id})", False),
                ("Moderator", ctx.author.mention, True),
                ("Reason", reason, True),
            ],
        )

    # --- UNBAN COMMAND ---
    @commands.command(name="unban", help="Unbans a user using their username#discriminator or ID.")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx, *, user_spec: str):
        try: await ctx.message.delete()
        except discord.HTTPException: pass

        async for ban_entry in ctx.guild.bans(limit=1000):
            user = ban_entry.user

            if user_spec == str(user) or user_spec == str(user.id):
                await ctx.guild.unban(user)
                self.log_case(ctx.guild.id, user.id, ctx.author.id, "unban", "No reason provided")

                embed = discord.Embed(title="User Unbanned", color=Config.EMBED_COLOR)
                embed.add_field(name="User", value=f"{user.name} ({user.id})", inline=False)
                embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)
                embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

                await ctx.send(embed=embed)
                await self.send_mod_log(
                    ctx,
                    "User Unbanned",
                    0x2ecc71,
                    [
                        ("User", f"{user.name} ({user.id})", False),
                        ("Moderator", ctx.author.mention, True),
                        ("Reason", "No reason provided", True),
                    ],
                )
                return

        embed = discord.Embed(
            description=f"<a:Cross:1514986232294281426> **Could not find a banned user matching** `{user_spec}`.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

    # --- MUTE / TIMEOUT COMMAND ---
    @commands.command(name="mute", aliases=["timeout"], help="Mutes a member using Discord's native timeout.")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def mute(self, ctx, member: discord.Member, duration: str, *, reason: str = "No reason provided"):
        try: await ctx.message.delete()
        except discord.HTTPException: pass

        minutes = self.parse_duration(duration)
        if minutes is None:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **Invalid duration.** Use formats like `10`, `10m`, `2h`, or `1d`.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        if minutes < 1:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **Please provide a mute duration greater than 0 minutes.**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **You cannot mute someone with an equal or higher administrative role than yourself.**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        if minutes > 40320:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **You cannot mute someone for more than 28 days (40,320 minutes).**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        dm_embed = discord.Embed(
            title=f"🔇 You have been muted in {ctx.guild.name}",
            color=0xf39c12,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        dm_embed.add_field(name="Duration", value=f"{duration} ({minutes} minutes)", inline=True)
        dm_embed.add_field(name="Reason", value=reason, inline=True)
        try:
            await member.send(embed=dm_embed)
        except discord.Forbidden:
            pass

        duration_delta = datetime.timedelta(minutes=minutes)
        await member.timeout(duration_delta, reason=reason)
        self.log_case(ctx.guild.id, member.id, ctx.author.id, "mute", reason, duration=f"{minutes}m")

        embed = discord.Embed(title="Member Muted", color=Config.EMBED_COLOR)
        embed.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
        embed.add_field(name="Duration", value=f"{minutes} minutes", inline=True)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

        await ctx.send(embed=embed)
        await self.send_mod_log(
            ctx,
            "Member Muted",
            0xf39c12,
            [
                ("User", f"{member.mention} ({member.id})", False),
                ("Duration", f"{minutes} minutes", True),
                ("Moderator", ctx.author.mention, True),
                ("Reason", reason, False),
            ],
        )

    # --- UNMUTE / REMOVE TIMEOUT COMMAND ---
    @commands.command(name="unmute", aliases=["untimeout"], help="Unmutes a member by removing their timeout.")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def unmute(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        try: await ctx.message.delete()
        except discord.HTTPException: pass

        if not member.is_timed_out():
            embed = discord.Embed(
                description=f"<a:Cross:1514986232294281426> {member.mention} **is not currently muted.**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **You cannot unmute someone with an equal or higher administrative role than yourself.**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        dm_embed = discord.Embed(
            title=f"🔊 Your mute has been removed in {ctx.guild.name}",
            color=0x2ecc71,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        dm_embed.add_field(name="Reason", value=reason, inline=False)
        try:
            await member.send(embed=dm_embed)
        except discord.Forbidden:
            pass

        await member.timeout(None, reason=reason)
        self.log_case(ctx.guild.id, member.id, ctx.author.id, "unmute", reason)

        embed = discord.Embed(title="Member Unmuted", color=Config.EMBED_COLOR)
        embed.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=True)
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

        await ctx.send(embed=embed)
        await self.send_mod_log(
            ctx,
            "Member Unmuted",
            0x2ecc71,
            [
                ("User", f"{member.mention} ({member.id})", False),
                ("Moderator", ctx.author.mention, True),
                ("Reason", reason, True),
            ],
        )
        
    # --- WARN COMMAND ---
    @commands.command(name="warn", help="Warns a member and logs the infraction.")
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        try: await ctx.message.delete()
        except discord.HTTPException: pass

        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **You cannot warn someone with an equal or higher administrative role than yourself.**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        if member.bot:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **You cannot warn a bot.**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        dm_embed = discord.Embed(
            title=f"⚠️ You have been warned in {ctx.guild.name}",
            color=0xf39c12, # A nice warning orange/yellow
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        dm_embed.add_field(name="Reason", value=reason, inline=False)
        try:
            await member.send(embed=dm_embed)
        except discord.Forbidden:
            pass

        # Database insertion using your existing internal method structure
        self.log_case(ctx.guild.id, member.id, ctx.author.id, "warn", reason)

        # Response embed sent back to the channel matching your tick/cross style
        embed = discord.Embed(
            description=f"<:Tick:1514986183489360087> **{member.mention}** has been warned.",
            color=Config.EMBED_COLOR
        )
        await ctx.send(embed=embed)

        # Logging sent to your moderation channel layout
        await self.send_mod_log(
            ctx,
            "Member Warned",
            0xf39c12,
            [
                ("User", f"{member.mention} ({member.id})", False),
                ("Moderator", ctx.author.mention, True),
                ("Reason", reason, True),
            ],
        )    

    # --- SAY / BROADCAST COMMAND ---
    @commands.command(name="say", help="Makes the bot say a message. Staff only.")
    @commands.has_permissions(administrator=True)
    async def say(self, ctx, *, message: str):
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        await ctx.send(message)

    # --- REPLY TO MESSAGE ID COMMAND ---
    @commands.command(name="reply", help="Makes the bot reply to a specific message ID. Staff only.")
    @commands.has_permissions(administrator=True)
    async def reply(self, ctx, message_id: int, *, message: str):
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        try:
            target_message = await ctx.channel.fetch_message(message_id)
            await target_message.reply(message)
        except discord.NotFound:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **Error: Could not find a message with that ID in this channel.**",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, delete_after=5)
        except discord.HTTPException:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **Failed to send reply due to a Discord API error.**",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, delete_after=5)

    # --- ERROR HANDLING ---
    @logs.error
    @purge.error
    @kick.error
    @ban.error
    @unban.error
    @mute.error
    @unmute.error
    @say.error
    @reply.error
    async def mod_errors(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **You do not have the required staff permissions to execute this command.**",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.BotMissingPermissions):
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **I need the correct administrative permissions (Kick, Ban, Manage Messages, Moderate Members) to execute this command.**",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.NoPrivateMessage):
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **This command can only be used inside a server channel.**",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                description=f"<a:Cross:1514986232294281426> **Missing parameters!** Target a user or specify a value. Use `{Config.PREFIX}help {ctx.command.name}` for syntax guidelines.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.BadArgument):
            if ctx.command and ctx.command.name in ("mute", "timeout"):
                embed = discord.Embed(
                    description=f"<a:Cross:1514986232294281426> **Invalid mute command syntax.** Use a valid member and duration, like `{Config.PREFIX}mute @user 10m reason`.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
            else:
                embed = discord.Embed(
                    description="<a:Cross:1514986232294281426> **Invalid argument provided.** Ensure you are targeting a valid user ID or mention.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
        else:
            raise error

async def setup(bot):
    await bot.add_cog(Moderation(bot))