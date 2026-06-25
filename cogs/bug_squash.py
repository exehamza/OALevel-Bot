import os
import json
import discord
from discord.ext import commands

class BugSquash(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.file_path = "data/bugs.json"
        self._ensure_file_exists()
        
        # Custom Emojis
        self.tick = "<:Tick:1514986183489360087>"
        self.cross = "<a:Cross:1514986232294281426>"

    def _ensure_file_exists(self):
        """Ensures the data directory and bugs.json file exist."""
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if not os.path.exists(self.file_path):
            with open(self.file_path, "w") as f:
                json.dump([], f)

    def _load_bugs(self):
        """Helper to read bugs from the JSON file."""
        with open(self.file_path, "r") as f:
            return json.load(f)

    def _save_bugs(self, bugs):
        """Helper to write bugs to the JSON file."""
        with open(self.file_path, "w") as f:
            json.dump(bugs, f, indent=4)

    @commands.command(name="bugreport")
    async def bug_report(self, ctx, *, bug_description: str):
        """Submits a new bug report."""
        bugs = self._load_bugs()
        
        new_bug = {
            "user": str(ctx.author),
            "user_id": ctx.author.id,
            "description": bug_description,
            "channel": ctx.channel.name
        }
        bugs.append(new_bug)
        self._save_bugs(bugs)
        
        embed = discord.Embed(
            description=f"{self.tick} **Bug report saved successfully!** (Index: {len(bugs)})",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.command(name="bugs")
    @commands.is_owner()
    async def list_bugs(self, ctx):
        """Lists all currently active bug reports (Dev only)."""
        bugs = self._load_bugs()
        
        if not bugs:
            embed = discord.Embed(
                description=f"{self.tick} **No active bugs reported!**",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            return

        embed = discord.Embed(
            title="🐛 Active Bug Reports", 
            color=discord.Color.dark_red()
        )
        
        for index, bug in enumerate(bugs, start=1):
            embed.add_field(
                name=f"Bug #{index}",
                value=f"**Reported by:** {bug['user']}\n**Issue:** {bug['description']}",
                inline=False
            )
            
        await ctx.send(embed=embed)

    @commands.command(name="bugremove")
    @commands.is_owner()
    async def bug_remove(self, ctx, index: int):
        """Removes a bug by its list index (Dev only)."""
        bugs = self._load_bugs()
        actual_index = index - 1
        
        if actual_index < 0 or actual_index >= len(bugs):
            embed = discord.Embed(
                description=f"{self.cross} **Invalid bug index.** Use `$bugs` to check active indices.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
            
        removed_bug = bugs.pop(actual_index)
        self._save_bugs(bugs)
        
        embed = discord.Embed(
            description=f"{self.tick} **Removed Bug #{index}:** *\"{removed_bug['description']}\"*",
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)

    # Error handling for restricted developer commands
    @list_bugs.error
    @bug_remove.error
    async def dev_commands_error(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            embed = discord.Embed(
                description=f"{self.cross} **You do not have permission to use this developer command.**",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(BugSquash(bot))