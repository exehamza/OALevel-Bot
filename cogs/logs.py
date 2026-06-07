import asyncio
from collections import defaultdict, deque

import discord
from discord.ext import commands

from config import Config

# PURGE LOGS
# BAN LOGS
# MUTE/UNMUTE/KICK/BAN/UNBAN
# SNIPE
# WELCOME MSG

class Logs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.snipe_storage = defaultdict(lambda: deque(maxlen=5))

    @commands.Cog.listener()
    async def on_ready(self):
        print("Logging engine and Snipe system are fully functional.")

    # Helper function to get the log channel securely
    async def get_log_channel(self, guild):
        if guild is None:
            return None

        log_channel = guild.get_channel(Config.LOG_CHANNEL_ID)
        if log_channel is not None:
            return log_channel

        try:
            log_channel = await self.bot.fetch_channel(Config.LOG_CHANNEL_ID)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as error:
            print(f"Log failed: could not fetch LOG_CHANNEL_ID {Config.LOG_CHANNEL_ID}. Error: {error}")
            return None

        if getattr(log_channel, "guild", None) != guild:
            print(
                f"Log failed: LOG_CHANNEL_ID {Config.LOG_CHANNEL_ID} "
                f"is not in the server '{guild.name}'."
            )
            return None

        return log_channel

    # --- 1. PURGE LOGGING ---
    # Triggered automatically when messages are bulk deleted via our clear command
    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages):
        if not messages:
            return

        guild = messages[0].guild
        log_channel = await self.get_log_channel(guild)
        if not log_channel:
            return

        embed = discord.Embed(
            title="Messages Purged",
            description=f"**{len(messages)}** messages were bulk deleted in {messages[0].channel.mention}.",
            color=Config.EMBED_COLOR
        )
        embed.set_timestamp()
        await log_channel.send(embed=embed)

    # --- 2. BAN LOGGING ---
    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        log_channel = await self.get_log_channel(guild)
        if not log_channel:
            return

        moderator = "Unknown (Manual or external)"
        reason = "No reason specified"

        # Fetch the latest audit log entry to see who actually performed the ban
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.ban, limit=1):
                if entry.target.id == user.id:
                    moderator = entry.user.mention
                    reason = entry.reason or reason
                    break
        except discord.Forbidden:
            pass

        embed = discord.Embed(title="Member Banned", color=0xe74c3c)
        embed.add_field(name="User Info", value=f"{user.mention} ({user.name})\nID: {user.id}", inline=False)
        embed.add_field(name="Responsible Moderator", value=moderator, inline=True)
        embed.add_field(name="Reason", value=reason, inline=True)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_timestamp()
        await log_channel.send(embed=embed)

    # --- 3. UNBAN LOGGING ---
    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        log_channel = await self.get_log_channel(guild)
        if not log_channel:
            return

        moderator = "Unknown"
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.unban, limit=1):
                if entry.target.id == user.id:
                    moderator = entry.user.mention
                    break
        except discord.Forbidden:
            pass

        embed = discord.Embed(title="Member Unbanned", color=0x2ecc71)
        embed.add_field(name="User Info", value=f"{user.name}\nID: {user.id}", inline=False)
        embed.add_field(name="Responsible Moderator", value=moderator, inline=False)
        embed.set_timestamp()
        await log_channel.send(embed=embed)

    # --- 4. KICK, MUTE & UNMUTE LOGGING ---
    # These all happen inside Discord's member update audit log
    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        log_channel = await self.get_log_channel(after.guild)
        if not log_channel:
            return

        # Handle MUTE (Timeout applied) and UNMUTE (Timeout removed)
        if before.timed_out_until != after.timed_out_until:
            moderator = "Unknown"
            reason = "No reason specified"

            try:
                async for entry in after.guild.audit_logs(action=discord.AuditLogAction.member_update, limit=1):
                    if entry.target.id == after.id:
                        moderator = entry.user.mention
                        reason = entry.reason or reason
                        break
            except discord.Forbidden:
                pass

            if after.is_timed_out():
                # A timeout was added
                embed = discord.Embed(title="Member Muted (Timed Out)", color=0xf39c12)
                embed.add_field(name="User", value=after.mention, inline=False)
                embed.add_field(name="Moderator", value=moderator, inline=True)
                embed.add_field(name="Reason", value=reason, inline=True)
                embed.set_timestamp()
                await log_channel.send(embed=embed)
            else:
                # A timeout was removed/expired
                embed = discord.Embed(title="Member Unmuted (Timeout Removed)", color=0x2ecc71)
                embed.add_field(name="User", value=after.mention, inline=False)
                embed.add_field(name="Moderator", value=moderator, inline=False)
                embed.set_timestamp()
                await log_channel.send(embed=embed)

    # Kicks don't have a direct on_member_kick event listener,
    # instead we monitor members leaving the server and cross-reference the audit log!
    @commands.Cog.listener()
    async def on_member_remove(self, member):
        log_channel = await self.get_log_channel(member.guild)
        if not log_channel:
            return

        # Wait a tiny fraction of a second to allow Discord to write the audit log entry
        await asyncio.sleep(0.5)

        try:
            async for entry in member.guild.audit_logs(action=discord.AuditLogAction.kick, limit=1):
                # Check if the kicked user matches the member who just left, and check timing
                if entry.target.id == member.id:
                    embed = discord.Embed(title="Member Kicked", color=0xe67e22)
                    embed.add_field(name="User Info", value=f"{member.mention} ({member.name})\nID: {member.id}", inline=False)
                    embed.add_field(name="Responsible Moderator", value=entry.user.mention, inline=True)
                    embed.add_field(name="Reason", value=entry.reason or "No reason specified", inline=True)
                    embed.set_timestamp()
                    await log_channel.send(embed=embed)
                    return
        except discord.Forbidden:
            return

    # --- 5. SNIPE MODULE RETENTION ---
    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot or message.guild is None:
            return
        self.snipe_storage[message.channel.id].appendleft({
            "content": message.content,
            "author": message.author,
            "timestamp": message.created_at
        })

    @commands.command(name="snipe", help="Snipe up to the last 5 deleted messages in this channel. Staff only.")
    @commands.check_any(
        commands.has_permissions(administrator=True))
    async def snipe(self, ctx, index: int = 1):
        if index < 1 or index > 5:
            return await ctx.send("You can only snipe historical messages between 1 and 5!")

        channel_history = self.snipe_storage[ctx.channel.id]
        if not channel_history:
            return await ctx.send("There are no recently deleted messages recorded in this channel.")

        if index > len(channel_history):
            return await ctx.send(f"Only **{len(channel_history)}** deleted messages are currently cached in this channel.")

        target_message = channel_history[index - 1]
        embed = discord.Embed(
            description=target_message["content"] or "*[Message contained no text content]*",
            color=Config.EMBED_COLOR,
            timestamp=target_message["timestamp"]
        )
        author = target_message["author"]
        embed.set_author(name=f"{author.name}", icon_url=author.display_avatar.url)
        embed.set_footer(text=f"Sniped position: {index}/{len(channel_history)}")
        await ctx.send(embed=embed)

    # --- 6. WELCOME SYSTEM ---
    @commands.Cog.listener()
    async def on_member_join(self, member):
        # Fetch the welcome channel using the ID from config.py
        welcome_channel = member.guild.get_channel(Config.WELCOME_CHANNEL_ID)

        # Safety guard: if the channel doesn't exist or isn't configured, do nothing
        if not welcome_channel:
            print(f"Warning: Welcome channel ID {Config.WELCOME_CHANNEL_ID} not found.")
            return

        # Construct the rich embed card based on your exact text structure
        embed = discord.Embed(
            title="WELCOME TO O/A LEVEL COMMUNITY",
            description=(
                f"Hello {member.mention} and welcome to our community of dedicated O and A Level students. "
                "We are pleased to have you join us. This server is designed to be a supportive environment "
                "where you can find resources, ask questions, and connect with peers as you prepare for your O and A Level exams.\n\n"
                "Please do make sure to head on over to #general and introduce yourself in order to verify "
                "yourselves so you can access the rest of the server!!"
            ),
            color=Config.EMBED_COLOR
        )

        # Add their profile picture as the right-side thumbnail image
        embed.set_thumbnail(url=member.display_avatar.url)

        # Add your custom footnote text
        embed.set_footer(text="Have A Good Time!!")

        # Send the welcome message, explicitly pinging them outside the embed so they get notified
        await welcome_channel.send(content=member.mention, embed=embed)

    @snipe.error
    async def snipe_error(self, ctx, error):
        if isinstance(error, (commands.MissingPermissions, commands.MissingAnyRole)):
            await ctx.send("This command is classified. Only Admins and Moderators can snipe deleted messages.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"Invalid syntax! Use `{Config.PREFIX}snipe` for the most recent message, or `{Config.PREFIX}snipe 2` for older ones.")
        else:
            raise error


async def setup(bot):
    await bot.add_cog(Logs(bot))
