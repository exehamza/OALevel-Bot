import json
import os
import re
import asyncio
import discord
from discord.ext import commands
from config import Config

# Path to save your auto-responder keywords
KEYWORDS_FILE = "./data/keywords.json"

# Custom Emojis
TICK = "<:Tick:1514986183489360087>"
CROSS = "<a:Cross:1514986232294281426>"

class Keywords(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.keywords = {}  # Dictionary format: {"trigger": "response"}
        self.master_pattern = None  # Compiled single regex pass for speed
        self.load_keywords()

    def _sync_load(self):
        """Synchronous file reading implementation to handle via thread."""
        os.makedirs(os.path.dirname(KEYWORDS_FILE), exist_ok=True)
        if not os.path.exists(KEYWORDS_FILE):
            with open(KEYWORDS_FILE, "w", encoding="utf-8") as file:
                json.dump({}, file, indent=2, ensure_ascii=False)
            return {}
        try:
            with open(KEYWORDS_FILE, "r", encoding="utf-8") as file:
                return json.load(file)
        except (json.JSONDecodeError, OSError):
            return {}

    def _sync_save(self):
        """Synchronous file writing implementation to handle via thread."""
        os.makedirs(os.path.dirname(KEYWORDS_FILE), exist_ok=True)
        with open(KEYWORDS_FILE, "w", encoding="utf-8") as file:
            json.dump(self.keywords, file, indent=2, ensure_ascii=False)
            file.write("\n")

    def load_keywords(self):
        """Initial structural preparation (run synchronously on startup safely)."""
        raw_data = self._sync_load()
        self.keywords = {str(k).lower().strip(): str(v) for k, v in raw_data.items()}
        self.compile_master_regex()

    async def save_keywords(self):
        """Asynchronously dispatches the file writing task to prevent thread lag."""
        await asyncio.to_thread(self._sync_save)

    def compile_master_regex(self):
        """Compiles a single global search pattern for instant linear validation."""
        if not self.keywords:
            self.master_pattern = None
            return
        # Escape keywords and combine them into one structured regex group
        sorted_keys = sorted(self.keywords.keys(), key=len, reverse=True)
        joined_triggers = "|".join(re.escape(k) for k in sorted_keys)
        self.master_pattern = re.compile(rf"(?<!\w)({joined_triggers})(?!\w)")

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"Keywords Auto-Responder loaded with {len(self.keywords)} active triggers.")

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore bots, system hooks, or DM messages
        if message.author.bot or message.guild is None or not self.master_pattern:
            return

        # Perform single O(1) performance lookup step across all stored keywords
        match = self.master_pattern.search(message.content.lower())
        if match:
            triggered_keyword = match.group(0)
            response = self.keywords.get(triggered_keyword)
            if response:
                await message.channel.send(response)

    @commands.group(name="keyword", aliases=["keywords"], invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def keyword(self, ctx):
        """Root command instructions guide."""
        embed = discord.Embed(
            title="Keywords Auto-Responder Help",
            description="Setup automatic trigger responses when specific words or phrases are sent.",
            color=discord.Color.teal()
        )
        embed.add_field(name="Add Keyword", value=f"`{Config.PREFIX}keyword add [trigger] | [response]`", inline=False)
        embed.add_field(name="Remove Keyword", value=f"`{Config.PREFIX}keyword remove [trigger]`", inline=False)
        embed.add_field(name="View Keywords", value=f"`{Config.PREFIX}keyword view`", inline=False)
        await ctx.send(embed=embed)

    @keyword.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def add_keyword(self, ctx, *, raw_input: str):
        """Adds or updates a keyword trigger response using the | separator."""
        if "|" not in raw_input:
            embed = discord.Embed(
                title=f"{CROSS} Invalid Syntax!",
                description=(
                    f"You must separate the trigger and response with a `|` symbol.\n\n"
                    f"**Syntax:** `{Config.PREFIX}keyword add [trigger] | [response]`\n"
                    f"**Example:** `{Config.PREFIX}keyword add good morning | Hello! Hope you have a great day!`"
                ),
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        parts = raw_input.split("|", 1)
        trigger = parts[0].strip().lower()
        response = parts[1].strip()

        if not trigger or not response:
            embed = discord.Embed(
                description=f"{CROSS} Both the trigger text (before the `|`) and the response text (after the `|`) are required.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        self.keywords[trigger] = response
        self.compile_master_regex()
        await self.save_keywords()
        
        embed = discord.Embed(
            title=f"{TICK} Auto-Responder Updated!",
            color=discord.Color.green()
        )
        embed.add_field(name="When someone says:", value=f"`{trigger}`", inline=False)
        embed.add_field(name="I will reply with:", value=response, inline=False)
        await ctx.send(embed=embed)

    @keyword.command(name="remove", aliases=["delete"])
    @commands.has_permissions(manage_guild=True)
    async def remove_keyword(self, ctx, *, trigger: str):
        """Removes a keyword trigger configuration entirely."""
        trigger = trigger.strip().lower()

        if trigger not in self.keywords:
            embed = discord.Embed(
                description=f"{CROSS} `{trigger}` is not configured as an auto-response trigger.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        del self.keywords[trigger]
        self.compile_master_regex()
        await self.save_keywords()

        embed = discord.Embed(
            description=f"{TICK} Removed `{trigger}` from the auto-responder list.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @keyword.command(name="view", aliases=["list"])
    @commands.has_permissions(manage_guild=True)
    async def view_keywords(self, ctx):
        """Displays all running keywords configurations using interactive pages."""
        if not self.keywords:
            embed = discord.Embed(
                description="The auto-responder keywords list is currently empty.",
                color=discord.Color.orange()
            )
            return await ctx.send(embed=embed)

        lines = []
        for trigger, response in sorted(self.keywords.items()):
            display_response = response if len(response) <= 60 else f"{response[:57]}..."
            lines.append(f"**`{trigger}`** ↳ {display_response}")

        items_per_page = 10
        pages = [lines[i:i + items_per_page] for i in range(0, len(lines), items_per_page)]
        total_pages = len(pages)
        current_page = 0

        def build_embed(page_index):
            embed = discord.Embed(
                title="📋 Active Auto-Responder Keywords",
                description="\n".join(pages[page_index]),
                color=discord.Color.teal()
            )
            embed.set_footer(text=f"Page {page_index + 1} of {total_pages} • Total Keywords: {len(lines)}")
            return embed

        class PaginationView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60.0)
                self.index = current_page
                self.message = None  # Safely bind the message object after creation
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

    @keyword.error
    @add_keyword.error
    @remove_keyword.error
    @view_keywords.error
    async def keyword_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                description=f"{CROSS} You need the **Manage Server** permission to change auto-responder settings.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title=f"{CROSS} Missing Arguments!",
                description=(
                    f"**Syntax:** `{Config.PREFIX}keyword add [trigger] | [response]`\n"
                    f"**Example:** `{Config.PREFIX}keyword add help me | What do you need help with?`"
                ),
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        else:
            raise error

async def setup(bot):
    await bot.add_cog(Keywords(bot))