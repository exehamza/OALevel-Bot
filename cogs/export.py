import discord
from discord.ext import commands
import os


class ExportCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="export", help="Exports internal configuration or database files. Usage: $export keywords.json")
    @commands.has_permissions(administrator=True)  # High security restriction to protect your database/sensitive data
    async def export_file(self, ctx, filename: str = None):
        # Delete the trigger message right away
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        # If no filename is provided
        if not filename:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **Please specify a file to export.**\n"
                            "Examples:\n"
                            "`$export keywords.json`\n"
                            "`$export blocked_words.json`\n"
                            "`$export database.sqlite`",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        filename_clean = filename.strip().lower()

        # Determine path mapping based on file extension rules provided
        if filename_clean.endswith(".json"):
            # JSON files are located inside the 'data/' directory
            file_path = os.path.join("data", filename)
        elif filename_clean.endswith(".sqlite") or filename_clean.endswith(".db"):
            # SQLite files are located in the root directory
            file_path = filename
        else:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **Unsupported file format.** You can only export `.json` or `.sqlite` files.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        # Check if the requested file actually exists on the host machine
        if not os.path.exists(file_path):
            embed = discord.Embed(
                description=f"<a:Cross:1514986232294281426> **The system could not locate** `{filename}` in the expected path.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        try:
            # Prepare the file as a Discord Attachment object
            discord_file = discord.File(file_path, filename=filename)
            
            embed = discord.Embed(
                description=f"<:Tick:1514986183489360087> **Successfully generated export for** `{filename}`.",
                color=discord.Color.green()
            )
            
            # Send the confirmation embed along with the file attachment
            await ctx.send(embed=embed, file=discord_file)

        except discord.HTTPException as e:
            embed = discord.Embed(
                description=f"<a:Cross:1514986232294281426> **Failed to transmit file via Discord:**\n`{e}`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    # Error handling specific to this command
    @export_file.error
    async def export_error(self, ctx, error):
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **You must be an Administrator to backup/export internal bot data.**",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                description=f"<a:Cross:1514986232294281426> **An unexpected error occurred:**\n`{error}`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(ExportCog(bot))