import datetime
import re
import discord
from discord.ext import commands
from config import Config

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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
        embed.timestamp = datetime.datetime.utcnow()

        try:
            await log_channel.send(embed=embed)
        except discord.Forbidden:
            print(f"Moderation log failed: I cannot send messages/embeds in #{getattr(log_channel, 'name', Config.LOG_CHANNEL_ID)}.")
        except discord.HTTPException as error:
            print(f"Moderation log failed: Discord rejected the log message. Error: {error}")

    @commands.Cog.listener()
    async def on_ready(self):
        print("Moderation module loaded successfully.")

    # --- PURGE COMMAND ---
    @commands.command(name="purge", help="Purges a set number of messages from the channel.")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge(self, ctx, amount: int):
        if amount < 1:
            return await ctx.send("Please provide a number greater than 0.", delete_after=5)

        if amount > 100:
            return await ctx.send("Please purge 100 messages or fewer at a time.", delete_after=5)

        try:
            deleted = await ctx.channel.purge(limit=amount + 1)
        except discord.Forbidden:
            return await ctx.send("I need Manage Messages and Read Message History permissions in this channel.", delete_after=7)
        except discord.HTTPException:
            return await ctx.send("Discord refused the purge. This can happen with very old messages or too many messages.", delete_after=7)

        embed_color = getattr(Config, "EMBED_COLOR", discord.Color.blue())
        embed = discord.Embed(
            description=f"Successfully deleted **{len(deleted) - 1}** messages.",
            color=embed_color
        )
        await ctx.send(embed=embed, delete_after=5)
        await self.send_mod_log(
            ctx,
            "Messages Purged",
            0x3498db,
            [
                ("Channel", ctx.channel.mention, True),
                ("Deleted Messages", str(len(deleted) - 1), True),
                ("Moderator", ctx.author.mention, False),
            ],
        )

    # --- KICK COMMAND ---
    @commands.command(name="kick", help="Kicks a member from the server.")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send("You cannot kick someone with an equal or higher administrative role than yourself.")

        # NEW: DM the user FIRST before kicking
        dm_embed = discord.Embed(
            title=f"👟 You have been kicked from {ctx.guild.name}",
            color=0xe67e22,
            timestamp=datetime.datetime.utcnow()
        )
        dm_embed.add_field(name="Reason", value=reason, inline=False)
        try:
            await member.send(embed=dm_embed)
        except discord.Forbidden:
            pass  # User has DMs disabled or blocked the bot

        # Perform the kick action
        await member.kick(reason=reason)

        embed = discord.Embed(title="Member Kicked", color=Config.EMBED_COLOR)
        embed.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=True)
        embed.timestamp = datetime.datetime.utcnow()

        await ctx.send(embed=embed)

        if hasattr(Config, "LOG_CHANNEL_ID") and Config.LOG_CHANNEL_ID:
            log_channel = ctx.guild.get_channel(Config.LOG_CHANNEL_ID)
            if not log_channel:
                try:
                    log_channel = await ctx.guild.fetch_channel(Config.LOG_CHANNEL_ID)
                except discord.HTTPException:
                    log_channel = None

            if log_channel:
                await log_channel.send(embed=embed)

    # --- BAN COMMAND ---
    @commands.command(name="ban", help="Bans a member from the server.")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send("You cannot ban someone with an equal or higher administrative role than yourself.")

        # NEW: DM the user FIRST before banning
        dm_embed = discord.Embed(
            title=f"🔨 You have been permanently banned from {ctx.guild.name}",
            color=0xe74c3c,
            timestamp=datetime.datetime.utcnow()
        )
        dm_embed.add_field(name="Reason", value=reason, inline=False)
        try:
            await member.send(embed=dm_embed)
        except discord.Forbidden:
            pass

        await member.ban(reason=reason)

        embed = discord.Embed(title="Member Banned", color=Config.EMBED_COLOR)
        embed.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=True)
        embed.timestamp = datetime.datetime.utcnow()

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
        async for ban_entry in ctx.guild.bans(limit=1000):
            user = ban_entry.user

            if user_spec == str(user) or user_spec == str(user.id):
                await ctx.guild.unban(user)

                embed = discord.Embed(title="User Unbanned", color=Config.EMBED_COLOR)
                embed.add_field(name="User", value=f"{user.name} ({user.id})", inline=False)
                embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)
                embed.timestamp = datetime.datetime.utcnow()

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

        await ctx.send(f"Could not find a banned user matching `{user_spec}`.")

    # --- MUTE / TIMEOUT COMMAND ---
    @commands.command(name="mute", aliases=["timeout"], help="Mutes a member using Discord's native timeout.")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def mute(self, ctx, member: discord.Member, duration: str, *, reason: str = "No reason provided"):
        minutes = self.parse_duration(duration)
        if minutes is None:
            return await ctx.send("Invalid duration. Use minutes like `10`, `10m`, `2h`, or `1d`.")

        if minutes < 1:
            return await ctx.send("Please provide a mute duration greater than 0 minutes.")

        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send("You cannot mute someone with an equal or higher administrative role than yourself.")

        if minutes > 40320:
            return await ctx.send("You cannot mute someone for more than 28 days (40,320 minutes).")

        # NEW: DM the user before applying the timeout
        dm_embed = discord.Embed(
            title=f"🔇 You have been muted in {ctx.guild.name}",
            color=0xf39c12,
            timestamp=datetime.datetime.utcnow()
        )
        dm_embed.add_field(name="Duration", value=f"{duration} ({minutes} minutes)", inline=True)
        dm_embed.add_field(name="Reason", value=reason, inline=True)
        try:
            await member.send(embed=dm_embed)
        except discord.Forbidden:
            pass

        duration_delta = datetime.timedelta(minutes=minutes)
        await member.timeout(duration_delta, reason=reason)

        embed = discord.Embed(title="Member Muted", color=Config.EMBED_COLOR)
        embed.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
        embed.add_field(name="Duration", value=f"{minutes} minutes", inline=True)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.timestamp = datetime.datetime.utcnow()

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
        if not member.is_timed_out():
            return await ctx.send(f"{member.mention} is not currently muted.")

        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send("You cannot unmute someone with an equal or higher administrative role than yourself.")

        # NEW: DM the user that they have been unmuted
        dm_embed = discord.Embed(
            title=f"🔊 Your mute has been removed in {ctx.guild.name}",
            color=0x2ecc71,
            timestamp=datetime.datetime.utcnow()
        )
        dm_embed.add_field(name="Reason", value=reason, inline=False)
        try:
            await member.send(embed=dm_embed)
        except discord.Forbidden:
            pass

        await member.timeout(None, reason=reason)

        embed = discord.Embed(title="Member Unmuted", color=Config.EMBED_COLOR)
        embed.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=True)
        embed.timestamp = datetime.datetime.utcnow()

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
            await ctx.send("Error: Could not find a message with that ID in this channel.", delete_after=5)
        except discord.HTTPException:
            await ctx.send("Failed to send reply due to a Discord API error.", delete_after=5)

    # --- ERROR HANDLING ---
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
            await ctx.send("You do not have the required staff permissions to execute this command.")
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send("I need the correct administrative permissions (Kick, Ban, Manage Messages, Moderate Members) to execute this command.")
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("This command can only be used inside a server channel.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing parameters! Target a user or specify a value. Use `{Config.PREFIX}help {ctx.command.name}` for syntax guidelines.")
        elif isinstance(error, commands.BadArgument):
            if ctx.command and ctx.command.name in ("mute", "timeout"):
                await ctx.send("Invalid mute command. Use a valid member and duration, like `!mute @user 10m reason`.")
            else:
                await ctx.send("Invalid argument provided. Ensure you are targeting a valid user ID or mention.")
        else:
            raise error

async def setup(bot):
    await bot.add_cog(Moderation(bot))