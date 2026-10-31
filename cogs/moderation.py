import asyncio
import datetime
import os
import re
import sqlite3
from typing import Optional
import discord
from discord.ext import commands
from config import Config

ROLE_MODERATOR = 1256124924356071463
ROLE_LEAD_MOD = 1376227143545000056
ROLE_MANAGEMENT = 1272244827693650034


def is_mod_or_higher():
    """Allows Moderator, Lead Moderator, Management, or Administrator."""
    async def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild:
            return False
        role_ids = {r.id for r in ctx.author.roles}
        if (
            ROLE_MODERATOR in role_ids
            or ROLE_LEAD_MOD in role_ids
            or ROLE_MANAGEMENT in role_ids
            or ctx.author.guild_permissions.administrator
            or ctx.author == ctx.guild.owner
        ):
            return True
        raise commands.MissingPermissions(["manage_messages"])
    return commands.check(predicate)


def is_lead_mod_or_higher():
    """Allows ONLY Lead Moderator, Management, or Administrator (blocks regular Moderators)."""
    async def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild:
            return False
        role_ids = {r.id for r in ctx.author.roles}
        if (
            ROLE_LEAD_MOD in role_ids
            or ROLE_MANAGEMENT in role_ids
            or ctx.author.guild_permissions.administrator
            or ctx.author == ctx.guild.owner
        ):
            return True
        raise commands.MissingPermissions(["ban_members"])
    return commands.check(predicate)


def is_management_or_admin():
    """Allows ONLY Management or Administrator."""
    async def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild:
            return False
        role_ids = {r.id for r in ctx.author.roles}
        if (
            ROLE_MANAGEMENT in role_ids
            or ctx.author.guild_permissions.administrator
            or ctx.author == ctx.guild.owner
        ):
            return True
        raise commands.MissingPermissions(["administrator"])
    return commands.check(predicate)


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.db_path = os.path.join(project_root, "data", "database.sqlite")
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
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
            return

        embed = discord.Embed(title=title, color=color)
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
        embed.set_footer(text=f"Command used in #{ctx.channel.name}")
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

        try:
            await log_channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException) as error:
            print(f"Moderation log failed: {error}")

    @commands.Cog.listener()
    async def on_ready(self):
        print("Moderation module loaded successfully.")
        
    @commands.command(name="removecase", aliases=["delcase", "deletecase"])
    @commands.guild_only()
    @is_management_or_admin()
    async def remove_case(self, ctx, case_id: int):
        """Removes a moderation case from the logs using its Case ID."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT user_id, mod_id, action_type, reason 
            FROM mod_cases 
            WHERE case_id = ? AND guild_id = ?
        """, (case_id, ctx.guild.id))
        case_data = cursor.fetchone()

        if not case_data:
            conn.close()
            embed = discord.Embed(
                description=f"<a:Cross:1514986232294281426> Case ID `#{case_id}` was not found for this server.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, delete_after=5)
            return

        user_id, target_mod_id, action_type, original_reason = case_data

        cursor.execute("DELETE FROM mod_cases WHERE case_id = ? AND guild_id = ?", (case_id, ctx.guild.id))
        conn.commit()
        conn.close()

        embed = discord.Embed(
            description=f"<:Tick:1514986183489360087> Successfully deleted Case ID `#{case_id}`.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

        fields = [
            ("Target User", f"<@{user_id}> (ID: {user_id})", False),
            ("Removed By", f"{ctx.author.mention} (ID: {ctx.author.id})", False),
            ("Original Action", action_type.capitalize(), True),
            ("Original Reason", original_reason or "No reason provided", False)
        ]

        await self.send_mod_log(
            ctx=ctx,
            title=f"🗑️ Moderation Case #{case_id} Removed",
            color=discord.Color.red(),
            fields=fields
        )

    # --- LOGS / HISTORY COMMAND (MOD+) ---
    @commands.command(name="logs", aliases=["history", "cases"], help="Shows moderation history for a specific user.")
    @commands.guild_only()
    @is_mod_or_higher()
    async def logs(self, ctx, target: discord.User | discord.Member):
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

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

        embed_color = getattr(Config, "EMBED_COLOR", discord.Color.blue())

        if not rows:
            embed = discord.Embed(
                title=f"Mod Logs for {target.name}",
                description=f"✨ {target.mention} has a completely clean record.",
                color=embed_color
            )
            embed.set_thumbnail(url=target.display_avatar.url)
            return await ctx.send(embed=embed)

        case_entries = []
        for case_id, mod_id, action_type, reason, duration, timestamp in rows:
            duration_str = f" ({duration})" if duration else ""
            case_details = (
                f"**Case #{case_id} — {action_type.upper()}{duration_str}**\n"
                f"**Moderator:** <@{mod_id}>\n"
                f"**Reason:** {reason}\n"
                f"**Date:** <t:{timestamp}:F> (<t:{timestamp}:R>)\n"
                f"{'—' * 18}"
            )
            case_entries.append(case_details)

        items_per_page = 5
        pages = [case_entries[i:i + items_per_page] for i in range(0, len(case_entries), items_per_page)]
        total_pages = len(pages)
        current_page = 0

        def build_embed(page_index):
            embed = discord.Embed(
                title=f"Mod Logs for {target.name}",
                description=(
                    f"Found **{len(rows)}** total infraction record(s) for {target.mention}:\n\n"
                    + "\n".join(pages[page_index])
                ),
                color=embed_color
            )
            embed.set_thumbnail(url=target.display_avatar.url)
            embed.set_footer(text=f"Page {page_index + 1} of {total_pages} • Total Cases: {len(rows)}")
            return embed

        class PaginationView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60.0)
                self.index = current_page
                self.message = None
                self.update_button_states()

            def update_button_states(self):
                self.prev_button.disabled = self.index == 0
                self.next_button.disabled = self.index == total_pages - 1

            @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.blurple)
            async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message("You can't use these buttons!", ephemeral=True)

                self.index -= 1
                self.update_button_states()
                await interaction.response.edit_message(embed=build_embed(self.index), view=self)

            @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.blurple)
            async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message("You can't use these buttons!", ephemeral=True)

                self.index += 1
                self.update_button_states()
                await interaction.response.edit_message(embed=build_embed(self.index), view=self)

            async def on_timeout(self):
                for item in self.children:
                    item.disabled = True
                if self.message:
                    try:
                        await self.message.edit(view=self)
                    except discord.HTTPException:
                        pass

        view = PaginationView() if total_pages > 1 else None
        sent_message = await ctx.send(embed=build_embed(current_page), view=view)
        if view:
            view.message = sent_message

    # --- FAST DYNO-STYLE PURGE COMMAND (MOD+) ---
    @commands.command(name="purge", aliases=["clear"], help="Purges a set number of messages from the channel, optionally filtered by user.")
    @commands.guild_only()
    @is_mod_or_higher()
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge(self, ctx, arg1: discord.Member | int = None, arg2: int = None):
        target_member = None
        amount = 0

        if isinstance(arg1, discord.Member) and isinstance(arg2, int):
            target_member = arg1
            amount = arg2
        elif isinstance(arg1, int):
            amount = arg1

        if amount <= 0:
            embed = discord.Embed(
                description=(
                    "<a:Cross:1514986232294281426> **Invalid format or amount.** Use one of the following:\n"
                    "`$purge [amount]`\n"
                    "`$purge [@user] [amount]`"
                ),
                color=discord.Color.red()
            )
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass
            return await ctx.send(embed=embed, delete_after=5)

        if amount > 100:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **Please purge 100 messages or fewer at a time.**",
                color=discord.Color.red()
            )
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass
            return await ctx.send(embed=embed, delete_after=5)

        # Discord bulk-delete only supports messages younger than 14 days
        cutoff_14d = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=14, minutes=-5)
        to_delete: list[discord.Message] = []

        try:
            if target_member is None:
                # Single-page fetch (<= 100 messages before the command trigger)
                async for msg in ctx.channel.history(limit=amount, before=ctx.message):
                    if msg.created_at < cutoff_14d:
                        break
                    to_delete.append(msg)
            else:
                # Stream history and STOP immediately once `amount` matching messages are found
                async for msg in ctx.channel.history(limit=500, before=ctx.message):
                    if msg.created_at < cutoff_14d:
                        break
                    if msg.author.id == target_member.id:
                        to_delete.append(msg)
                        if len(to_delete) >= amount:
                            break

            actual_deleted = len(to_delete)

            # Bundle ctx.message into the single bulk-delete call whenever total <= 100
            if actual_deleted == 0:
                try:
                    await ctx.message.delete()
                except discord.HTTPException:
                    pass
            elif actual_deleted < 100:
                await ctx.channel.delete_messages([ctx.message, *to_delete])
            else:
                # When purging exactly 100 messages + 1 trigger message (101 total), fire both concurrently
                await asyncio.gather(
                    ctx.channel.delete_messages(to_delete),
                    ctx.message.delete(),
                    return_exceptions=True,
                )

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

        embed_color = getattr(Config, "EMBED_COLOR", discord.Color.blue())
        user_str = f" sent by {target_member.mention}" if target_member else ""
        msg_word = "message" if actual_deleted == 1 else "messages"

        embed = discord.Embed(
            description=f"Successfully deleted **{actual_deleted}** {msg_word}{user_str}.",
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

        # Dispatch mod log in the background so confirmation is never delayed
        asyncio.create_task(self.send_mod_log(ctx, "Messages Purged", 0x3498db, log_fields))

    # --- KICK COMMAND (MOD+) ---
    @commands.command(name="kick", help="Kicks a member from the server.")
    @commands.guild_only()
    @is_mod_or_higher()
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

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

    # --- BAN COMMAND (LEAD MOD+ ONLY) ---
    @commands.command(name="ban", help="Bans a member from the server.")
    @commands.guild_only()
    @is_lead_mod_or_higher()
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

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

    # --- UNBAN COMMAND (LEAD MOD+ ONLY) ---
    @commands.command(name="unban", help="Unbans a user using their username, tag, or User ID.")
    @commands.guild_only()
    @is_lead_mod_or_higher()
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx, *, user_spec: str = None):
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        if user_spec is None:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **Please specify a user to unban.**\n\n**Usage:** `unban <username/ID>`",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        target_user = None

        if user_spec.isdigit():
            try:
                ban_entry = await ctx.guild.fetch_ban(discord.Object(id=int(user_spec)))
                target_user = ban_entry.user
            except discord.NotFound:
                pass

        if not target_user:
            async for ban_entry in ctx.guild.bans(limit=None):
                u = ban_entry.user
                if user_spec.lower() in (str(u).lower(), u.name.lower(), f"{u.name}#{u.discriminator}".lower()):
                    target_user = u
                    break

        if not target_user:
            embed = discord.Embed(
                description=f"<a:Cross:1514986232294281426> **Could not find a banned user matching** `{user_spec}`.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        await ctx.guild.unban(target_user)
        self.log_case(ctx.guild.id, target_user.id, ctx.author.id, "unban", "No reason provided")

        embed = discord.Embed(title="User Unbanned", color=Config.EMBED_COLOR)
        embed.add_field(name="User", value=f"{target_user.name} ({target_user.id})", inline=False)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

        await ctx.send(embed=embed)
        await self.send_mod_log(
            ctx,
            "User Unbanned",
            0x2ecc71,
            [
                ("User", f"{target_user.name} ({target_user.id})", False),
                ("Moderator", ctx.author.mention, True),
                ("Reason", "No reason provided", True),
            ],
        )

    # --- MUTE / TIMEOUT COMMAND (MOD+) ---
    @commands.command(name="mute", aliases=["timeout"], help="Mutes a member using Discord's native timeout.")
    @commands.guild_only()
    @is_mod_or_higher()
    @commands.bot_has_permissions(moderate_members=True)
    async def mute(self, ctx, member: discord.Member, duration: str, *, reason: str = "No reason provided"):
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

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

    # --- UNMUTE / REMOVE TIMEOUT COMMAND (MOD+) ---
    @commands.command(name="unmute", aliases=["untimeout"], help="Unmutes a member by removing their timeout.")
    @commands.guild_only()
    @is_mod_or_higher()
    @commands.bot_has_permissions(moderate_members=True)
    async def unmute(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

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
        
    # --- WARN COMMAND (MOD+) ---
    @commands.command(name="warn", help="Warns a member and logs the infraction.")
    @commands.guild_only()
    @is_mod_or_higher()
    async def warn(self, ctx, member: discord.Member = None, *, reason: str = "No reason provided"):
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        if member is None:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **Please specify a member to warn.**\n\n**Usage:** `warn <@member/ID> [reason]`",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

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
            color=0xf39c12,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        dm_embed.add_field(name="Reason", value=reason, inline=False)
        try:
            await member.send(embed=dm_embed)
        except discord.Forbidden:
            pass

        self.log_case(ctx.guild.id, member.id, ctx.author.id, "warn", reason)

        embed = discord.Embed(
            description=f"<:Tick:1514986183489360087> **{member.mention}** has been warned.",
            color=Config.EMBED_COLOR
        )
        await ctx.send(embed=embed)

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

    # --- SAY / BROADCAST COMMAND (MANAGEMENT+) ---
    @commands.command(name="say", help="Makes the bot say a message. Staff only.")
    @commands.guild_only()
    @is_management_or_admin()
    async def say(self, ctx, *, message: str):
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        await ctx.send(message)

    # --- UNIFIED REPLY COMMAND (MANAGEMENT+) ---
    @commands.command(name="reply", help="Makes the bot reply to a message in the current or specified channel.")
    @commands.guild_only()
    @is_management_or_admin()
    async def reply(self, ctx, channel: Optional[discord.TextChannel], message_id: int, *, message: str):
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        target_channel = channel or ctx.channel
        try:
            target_message = await target_channel.fetch_message(message_id)
            await target_message.reply(message)
        except discord.NotFound:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **Error: Could not find a message with that ID in the target channel.**",
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
    @remove_case.error
    @logs.error
    @purge.error
    @kick.error
    @ban.error
    @unban.error
    @mute.error
    @unmute.error
    @warn.error
    @say.error
    @reply.error
    async def mod_errors(self, ctx, error):
        if isinstance(error, (commands.MissingPermissions, commands.CheckFailure)):
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
