import json
import os
import re
import discord
from discord.ext import commands
from config import Config

# Path to save your auto-responder keywords
KEYWORDS_FILE = "./data/keywords.json"

class Keywords(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.keywords = {}  # Dictionary format: {"trigger": "response"}
        self.load_keywords()

    def load_keywords(self):
        """Loads keyword mapping from the local JSON storage."""
        os.makedirs(os.path.dirname(KEYWORDS_FILE), exist_ok=True)

        if not os.path.exists(KEYWORDS_FILE):
            self.save_keywords()
            return

        try:
            with open(KEYWORDS_FILE, "r", encoding="utf-8") as file:
                self.keywords = json.load(file)
        except (json.JSONDecodeError, OSError):
            self.keywords = {}

        # Ensure all keys stored are lowercase for matching consistency
        self.keywords = {str(k).lower().strip(): str(v) for k, v in self.keywords.items()}

    def save_keywords(self):
        """Saves current keyword mapping back to the local JSON file."""
        os.makedirs(os.path.dirname(KEYWORDS_FILE), exist_ok=True)
        with open(KEYWORDS_FILE, "w", encoding="utf-8") as file:
            json.dump(self.keywords, file, indent=2, ensure_ascii=False)
            file.write("\n")

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"Keywords Auto-Responder loaded with {len(self.keywords)} active triggers.")

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore bots and system/DM messages
        if message.author.bot or message.guild is None:
            return

        content_lower = message.content.lower()

        # Scan through your saved triggers
        for trigger, response in self.keywords.items():
            # Uses strict word boundaries so phrases match cleanly without partial-word triggers
            pattern = rf"(?<!\w){re.escape(trigger)}(?!\w)"
            if re.search(pattern, content_lower):
                # Send the response directly to the channel
                await message.channel.send(response)
                break  # Stops checking once one match is found to prevent multi-trigger spam

    @commands.group(name="keyword", aliases=["keywords"], invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def keyword(self, ctx):
        """Root command instructions guide."""
        embed = discord.Embed(
            title="🤖 Keywords Auto-Responder Help",
            description="Setup automatic trigger responses when specific words or phrases are sent.",
            color=discord.Color.teal()
        )
        embed.add_field(name="➕ Add Keyword", value=f"`{Config.PREFIX}keyword add [trigger] | [response]`", inline=False)
        embed.add_field(name="➖ Remove Keyword", value=f"`{Config.PREFIX}keyword remove [trigger]`", inline=False)
        embed.add_field(name="👁️ View Keywords", value=f"`{Config.PREFIX}keyword view`", inline=False)
        await ctx.send(embed=embed)

    @keyword.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def add_keyword(self, ctx, *, raw_input: str):
        """Adds or updates a keyword trigger response using the | separator."""
        if "|" not in raw_input:
            return await ctx.send(
                f"❌ **Invalid Syntax!** You must separate the trigger and response with a `|` symbol.\n"
                f"👉 Syntax: `{Config.PREFIX}keyword add [trigger] | [response]`\n"
                f"👉 Example: `{Config.PREFIX}keyword add good morning | Hello! Hope you have a great day!`"
            )

        # Split the input into exactly two parts based on the first pipe symbol found
        parts = raw_input.split("|", 1)
        trigger = parts[0].strip().lower()
        response = parts[1].strip()

        if not trigger or not response:
            return await ctx.send("❌ Both the trigger text (before the `|`) and the response text (after the `|`) are required.")

        # Saves or updates the trigger mapping
        self.keywords[trigger] = response
        self.save_keywords()
        
        await ctx.send(
            f"✅ **Auto-responder updated!**\n"
            f"• **When someone says:** `{trigger}`\n"
            f"• **I will reply with:** {response}"
        )

    @keyword.command(name="remove", aliases=["delete"])
    @commands.has_permissions(manage_guild=True)
    async def remove_keyword(self, ctx, *, trigger: str):
        """Removes a keyword trigger configuration entirely."""
        trigger = trigger.strip().lower()

        if trigger not in self.keywords:
            return await ctx.send(f"❌ `{trigger}` is not configured as an auto-response trigger.")

        del self.keywords[trigger]
        self.save_keywords()
        await ctx.send(f"✅ Removed `{trigger}` from the auto-responder list.")

    @keyword.command(name="view", aliases=["list"])
    @commands.has_permissions(manage_guild=True)
    async def view_keywords(self, ctx):
        """Displays all running keywords configurations."""
        if not self.keywords:
            return await ctx.send("The auto-responder keywords list is currently empty.")

        embed = discord.Embed(
            title="📋 Active Auto-Responder Keywords",
            color=discord.Color.teal()
        )

        # Build fields for each trigger pairing
        for trigger, response in sorted(self.keywords.items()):
            # Trim display response if it's too long for an embed field preview
            display_response = response if len(response) <= 100 else f"{response[:97]}..."
            embed.add_field(
                name=f"Trigger: `{trigger}`",
                value=f"↳ Responds: {display_response}",
                inline=False
            )

        await ctx.send(embed=embed)

    @keyword.error
    @add_keyword.error
    @remove_keyword.error
    @view_keywords.error
    async def keyword_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need the Manage Server permission to change auto-responder settings.")
        
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(
                f"❌ **Missing arguments!**\n"
                f"Syntax: `{Config.PREFIX}keyword add [trigger] | [response]`\n"
                f"Example: `{Config.PREFIX}keyword add help me | What do you need help with?`"
            )
        else:
            raise error


async def setup(bot):
    await bot.add_cog(Keywords(bot))