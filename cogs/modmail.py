import json
import os
import discord
from discord.ext import commands
from config import Config

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODMAIL_BLACKLIST_FILE = os.path.join(BASE_DIR, "data", "modmail_blacklist.json")


class Modmail(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tick = "<:Tick:1514986183489360087>"
        self.cross = "<a:Cross:1514986232294281426>"
        self.blacklisted_users = set()
        self.load_blacklist()

    def load_blacklist(self):
        """Loads blacklisted user IDs from data/modmail_blacklist.json."""
        os.makedirs(os.path.dirname(MODMAIL_BLACKLIST_FILE), exist_ok=True)

        if not os.path.exists(MODMAIL_BLACKLIST_FILE):
            self.blacklisted_users = set()
            self.save_blacklist()
            return

        try:
            with open(MODMAIL_BLACKLIST_FILE, "r", encoding="utf-8") as file:
                data = json.load(file)
        except (json.JSONDecodeError, OSError):
            data = {}

        if isinstance(data, dict):
            users = data.get("blacklisted_users", [])
        elif isinstance(data, list):
            users = data
        else:
            users = []

        self.blacklisted_users = {
            int(uid) for uid in users if str(uid).isdigit()
        }

    def save_blacklist(self):
        """Saves current blacklisted user IDs to data/modmail_blacklist.json."""
        os.makedirs(os.path.dirname(MODMAIL_BLACKLIST_FILE), exist_ok=True)
        with open(MODMAIL_BLACKLIST_FILE, "w", encoding="utf-8") as file:
            json.dump(
                {"blacklisted_users": sorted(self.blacklisted_users)},
                file,
                indent=2,
                ensure_ascii=False,
            )
            file.write("\n")

    async def resolve_target_id(self, ctx: commands.Context, target: str) -> tuple[int | None, str]:
        """Resolves a @mention, username, or raw User ID into (user_id, mention_str)."""
        cleaned = target.strip()
        try:
            user = await commands.UserConverter().convert(ctx, cleaned)
            return user.id, user.mention
        except commands.UserNotFound:
            raw_id = cleaned.strip("<@!>")
            if raw_id.isdigit():
                uid = int(raw_id)
                return uid, f"<@{uid}>"
            return None, ""

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 1. Ignore messages sent by bots (including itself)
        if message.author.bot:
            return

        # 2. HARD FILTER: Stop command executions from being sent to the user
        clean_content = message.content.strip().lower()
        if (
            clean_content.startswith(f"{Config.PREFIX}close")
            or clean_content.startswith(f"{Config.PREFIX}modmailblacklist")
            or clean_content.startswith(f"{Config.PREFIX}mmblacklist")
            or clean_content.startswith(f"{Config.PREFIX}mmbl")
        ):
            return

        # 3. SECONDARY FILTER: Catch any other registered prefix commands
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        # 4. HANDLE INCOMING DMS (User -> Staff)
        if message.guild is None:
            # Check if the user is blacklisted from opening a ticket
            if message.author.id in self.blacklisted_users:
                embed = discord.Embed(
                    description=f"{self.cross} **You are blacklisted from opening a ticket**",
                    color=discord.Color.red()
                )
                try:
                    await message.author.send(embed=embed)
                except (discord.Forbidden, discord.HTTPException):
                    pass
                return

            modmail_channel = self.bot.get_channel(Config.MODMAIL_CHANNEL_ID)
            if not modmail_channel:
                print("Modmail error: Channel ID not found in config.")
                return

            # Look through existing active threads to see if this user already has an open ticket
            thread_name = f"Ticket-{message.author.id}"
            active_thread = None

            for thread in modmail_channel.threads:
                if thread.name == thread_name and not thread.archived:
                    active_thread = thread
                    break

            # If no active thread exists, create a brand new one
            if not active_thread:
                init_embed = discord.Embed(
                    title="New Modmail Ticket Created",
                    description=f"User: {message.author.mention} ({message.author.name})\nID: `{message.author.id}`",
                    color=discord.Color.blue()
                )
                
                staff_msg = await modmail_channel.send(embed=init_embed)
                active_thread = await staff_msg.create_thread(
                    name=thread_name,
                    auto_archive_duration=1440  # 24 hours
                )
                
                embed = discord.Embed(
                    description=f"{self.tick} **Your modmail ticket has been opened!** Staff have been notified.",
                    color=discord.Color.green()
                )
                await message.author.send(embed=embed)

            # Forward user's content
            user_embed = discord.Embed(
                description=message.content or "*[No text content]*",
                color=discord.Color.light_gray()
            )
            user_embed.set_author(name=message.author.name, icon_url=message.author.display_avatar.url)
            
            files = []
            if message.attachments:
                for attachment in message.attachments:
                    files.append(await attachment.to_file())

            await active_thread.send(embed=user_embed, files=files)
            await message.add_reaction("📬")

        # 5. HANDLE OUTGOING REPLIES (Staff -> User)
        elif isinstance(message.channel, discord.Thread):
            if message.channel.parent_id == Config.MODMAIL_CHANNEL_ID:
                if message.channel.name.startswith("Ticket-"):
                    try:
                        user_id = int(message.channel.name.replace("Ticket-", ""))
                    except ValueError:
                        return

                    try:
                        target_user = await self.bot.fetch_user(user_id)
                    except discord.NotFound:
                        embed = discord.Embed(
                            description=f"{self.cross} **Could not find that user.** They may have left the server.",
                            color=discord.Color.red()
                        )
                        return await message.channel.send(embed=embed)

                    reply_embed = discord.Embed(
                        title="💬 Staff Reply",
                        description=message.content,
                        color=discord.Color.green()
                    )
                    
                    files = []
                    if message.attachments:
                        for attachment in message.attachments:
                            files.append(await attachment.to_file())

                    try:
                        await target_user.send(embed=reply_embed, files=files)
                        await message.add_reaction("✅")
                    except discord.Forbidden:
                        embed = discord.Embed(
                            description=f"{self.cross} **Could not send message.** The user has direct messages (DMs) closed.",
                            color=discord.Color.red()
                        )
                        await message.channel.send(embed=embed)

    # 6. UTILITY COMMAND TO CLOSE TICKETS
    @commands.command(name="close")
    @commands.guild_only()
    @commands.has_permissions(manage_threads=True)
    async def close_ticket(self, ctx):
        """Closes and archives a modmail thread."""
        if not isinstance(ctx.channel, discord.Thread) or ctx.channel.parent_id != Config.MODMAIL_CHANNEL_ID:
            embed = discord.Embed(
                description=f"{self.cross} **This command can only be used inside active modmail threads.**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        if not ctx.channel.name.startswith("Ticket-"):
            return

        user_id = int(ctx.channel.name.replace("Ticket-", ""))
        
        try:
            target_user = await self.bot.fetch_user(user_id)
            user_embed = discord.Embed(
                description="🔒 **Your modmail ticket has been closed by staff.** If you need anything else, simply message me again!",
                color=discord.Color.red()
            )
            await target_user.send(embed=user_embed)
        except discord.Forbidden:
            pass

        staff_embed = discord.Embed(
            description="🔒 **Ticket closed.** Archiving thread...",
            color=discord.Color.red()
        )
        await ctx.send(embed=staff_embed)
        await ctx.channel.edit(archived=True, locked=True)

    # 7. MODMAIL BLACKLIST COMMAND GROUP
    @commands.group(name="modmailblacklist", aliases=["mmblacklist", "mmbl"], invoke_without_command=True)
    @commands.guild_only()
    @commands.check_any(commands.has_permissions(manage_threads=True), commands.has_permissions(manage_messages=True))
    async def modmail_blacklist(self, ctx):
        """Parent command for managing the modmail blacklist."""
        embed = discord.Embed(
            title="🛡️ Modmail Blacklist Help",
            description=(
                "Manage users who are blocked from opening Modmail tickets:\n\n"
                f"• `{Config.PREFIX}modmailblacklist add <@user|userID>`\n"
                f"• `{Config.PREFIX}modmailblacklist remove <@user|userID>`\n"
                f"• `{Config.PREFIX}modmailblacklist view`"
            ),
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

    @modmail_blacklist.command(name="add")
    @commands.guild_only()
    @commands.check_any(commands.has_permissions(manage_threads=True), commands.has_permissions(manage_messages=True))
    async def modmail_blacklist_add(self, ctx, *, target: str):
        """Blacklists a user from opening modmail tickets."""
        user_id, mention_str = await self.resolve_target_id(ctx, target)
        if user_id is None:
            embed = discord.Embed(
                description=f"{self.cross} **Could not find that user.** Please provide a valid `@mention` or numeric `userID`.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        if user_id in self.blacklisted_users:
            embed = discord.Embed(
                description=f"{self.cross} {mention_str} **is already blacklisted from Modmail.**",
                color=discord.Color.orange()
            )
            return await ctx.send(embed=embed)

        self.blacklisted_users.add(user_id)
        self.save_blacklist()

        embed = discord.Embed(
            description=f"{self.tick} **Blacklisted** {mention_str} **from opening Modmail tickets.**",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @modmail_blacklist.command(name="remove", aliases=["delete"])
    @commands.guild_only()
    @commands.check_any(commands.has_permissions(manage_threads=True), commands.has_permissions(manage_messages=True))
    async def modmail_blacklist_remove(self, ctx, *, target: str):
        """Removes a user from the modmail blacklist."""
        user_id, mention_str = await self.resolve_target_id(ctx, target)
        if user_id is None:
            embed = discord.Embed(
                description=f"{self.cross} **Could not find that user.** Please provide a valid `@mention` or numeric `userID`.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        if user_id not in self.blacklisted_users:
            embed = discord.Embed(
                description=f"{self.cross} {mention_str} **is not currently in the Modmail blacklist.**",
                color=discord.Color.orange()
            )
            return await ctx.send(embed=embed)

        self.blacklisted_users.remove(user_id)
        self.save_blacklist()

        embed = discord.Embed(
            description=f"{self.tick} **Removed** {mention_str} **from the Modmail blacklist.**",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @modmail_blacklist.command(name="view", aliases=["list", "show"])
    @commands.guild_only()
    @commands.check_any(commands.has_permissions(manage_threads=True), commands.has_permissions(manage_messages=True))
    async def modmail_blacklist_view(self, ctx):
        """Lists all users currently blacklisted from Modmail with interactive pagination."""
        if not self.blacklisted_users:
            embed = discord.Embed(
                title="🛡️ Modmail Blacklist",
                description="There are currently no users blacklisted from Modmail.",
                color=discord.Color.blue()
            )
            return await ctx.send(embed=embed)

        lines = [f"• <@{uid}>" for uid in sorted(self.blacklisted_users)]
        items_per_page = 10
        pages = [lines[i:i + items_per_page] for i in range(0, len(lines), items_per_page)]
        total_pages = len(pages)
        current_page = 0

        def build_embed(page_index):
            embed = discord.Embed(
                title=f"🚫 Modmail Blacklisted Users ({len(lines)})",
                description="\n".join(pages[page_index]),
                color=discord.Color.red()
            )
            if total_pages > 1:
                embed.set_footer(text=f"Page {page_index + 1} of {total_pages} • Total Blacklisted: {len(lines)}")
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

    @close_ticket.error
    @modmail_blacklist.error
    @modmail_blacklist_add.error
    @modmail_blacklist_remove.error
    @modmail_blacklist_view.error
    async def modmail_error(self, ctx, error):
        if isinstance(error, (commands.MissingPermissions, commands.CheckAnyFailure)):
            embed = discord.Embed(
                description=f"{self.cross} **You do not have the required staff permissions to use this command.**",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                description=(
                    f"{self.cross} **Missing arguments.**\n"
                    f"Usage: `{Config.PREFIX}modmailblacklist add <@user|userID>` or `{Config.PREFIX}modmailblacklist remove <@user|userID>`"
                ),
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.NoPrivateMessage):
            embed = discord.Embed(
                description=f"{self.cross} **This command can only be used inside the server.**",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        else:
            raise error


async def setup(bot):
    await bot.add_cog(Modmail(bot))
