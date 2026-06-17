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
    @commands.command(name="purge", aliases=["clear"], help="Purges a set number of messages from the channel, optionally filtered by user.")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge(self, ctx, arg1: discord.Member | int = None, arg2: int = None):
        """
        Handles arguments:
        - $purge <amount>
        - $purge <member> <amount>
        """
        target_member = None
        amount = 0

        # Case 1: $purge <member> <amount>
        if isinstance(arg1, discord.Member) and isinstance(arg2, int):
            target_member = arg1
            amount = arg2

        # Case 2: $purge <amount>
        elif isinstance(arg1, int):
            amount = arg1

        # Check if the arguments match any valid usage style
        if amount <= 0:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **Invalid format or amount.** Use one of the following:\n"
                            "`$purge [amount]`\n"
                            "`$purge [@user] [amount]`",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed, delete_after=5)

        if amount > 100:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **Please purge 100 messages or fewer at a time.**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed, delete_after=5)

        # Define a check filter if filtering by a specific user
        def check_filter(message):
            return message.author == target_member

        try:
            # If a user is targeted, we look back deeper (up to 500 messages) to find the requested quantity of their messages.
            if target_member:
                deleted = await ctx.channel.purge(limit=500, check=check_filter, bulk=True)
                # Trim list if we found more user messages than they asked to delete
                if len(deleted) > amount:
                    deleted = deleted[:amount]
            else:
                # Include the command invocation message itself (+1)
                deleted = await ctx.channel.purge(limit=amount + 1)

        except discord.Forbidden:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **I need Manage Messages and Read Message History permissions in this channel.**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed, delete_after=7)
        except discord.HTTPException:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **Discord refused the purge.** This can happen with messages older than 14 days.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed, delete_after=7)

        # Calculate exact count (disregard your command invocation message from the total count if user wasn't targeted)
        actual_deleted = len(deleted)
        if not target_member:
            actual_deleted = max(0, actual_deleted - 1)

        embed_color = getattr(Config, "EMBED_COLOR", discord.Color.blue())
        user_str = f" sent by {target_member.mention}" if target_member else ""
        
        embed = discord.Embed(
            description=f"Successfully deleted **{actual_deleted}** messages{user_str}.",
            color=embed_color
        )
        await ctx.send(embed=embed, delete_after=5)

        # Setup logging info
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
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **You cannot kick someone with an equal or higher administrative role than yourself.**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        # DM the user FIRST before kicking
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
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **You cannot ban someone with an equal or higher administrative role than yourself.**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        # DM the user FIRST before banning
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

        # DM the user before applying the timeout
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

        # DM the user that they have been unmuted
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