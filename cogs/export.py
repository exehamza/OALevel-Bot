from pathlib import Path
import discord
from discord.ext import commands, tasks
from config import Config

# Everything here is anchored to the project folder, so it works no matter
# which directory the bot is started from (cogs/export.py -> cogs -> project root).
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = (PROJECT_ROOT / "data").resolve()


def is_secret_name(name: str) -> bool:
    """Never allow .env-style files (.env, .env.bak, .env.local, ...) to be sent."""
    return name.lower().startswith(".env")


class ExportCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Priority: Config.BACKUP_CHANNEL_ID -> fallback ID
        self.backup_channel_id = getattr(Config, "BACKUP_CHANNEL_ID", 1529530646244888720)

    async def cog_load(self):
        """Starts the background loop when the cog is loaded."""
        self.auto_backup_task.start()

    async def cog_unload(self):
        """Cancels the background loop when the cog is unloaded."""
        self.auto_backup_task.cancel()

    # --- 24-HOUR AUTOMATED BACKUP TASK ---
    @tasks.loop(hours=24)
    async def auto_backup_task(self):
        """Automated task that sends all files in the data/ folder to the backup channel every 24h."""
        channel = self.bot.get_channel(self.backup_channel_id)
        if channel is None:
            print(f"[AutoBackup] Could not find channel with ID {self.backup_channel_id}. Skipping automatic backup.")
            return

        if not DATA_DIR.exists() or not any(DATA_DIR.iterdir()):
            print("[AutoBackup] 'data/' directory is missing or empty. Nothing to export.")
            return

        attachments = []
        file_names = []

        for file_path in DATA_DIR.glob("*"):
            # Exclude directories, temporary export files, and .env-style files
            if (
                file_path.is_file()
                and not file_path.name.startswith("export_")
                and not is_secret_name(file_path.name)
            ):
                attachments.append(discord.File(str(file_path), filename=file_path.name))
                file_names.append(f"`{file_path.name}`")

        if not attachments:
            return

        embed = discord.Embed(
            title="📦 Daily Automated Data Backup",
            description=f"Successfully backed up **{len(attachments)}** system file(s):\n" + "\n".join(file_names),
            color=discord.Color.blue()
        )
        embed.set_footer(text="Automated 24-hour backup sequence")

        try:
            await channel.send(embed=embed, files=attachments)
            print(f"[AutoBackup] Daily backup sent successfully to #{channel.name}.")
        except discord.HTTPException as e:
            print(f"[AutoBackup] Failed to send backup files: {e}")

    @auto_backup_task.before_loop
    async def before_auto_backup(self):
        """Waits until the bot is fully logged in before starting the loop."""
        await self.bot.wait_until_ready()

    # --- MANUAL EXPORT COMMAND ---
    @commands.command(name="export", help="Exports internal configuration or database files manually. Usage: $export economy.db")
    @commands.has_permissions(administrator=True)
    async def export_file(self, ctx, filename: str = None):
        """Manually exports a specific file from data/ on demand."""
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        if not filename:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **Please specify a file to export.**\n\n"
                            "**Examples:**\n"
                            "`$export blocked_words.json`\n"
                            "`$export economy.db`",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        filename_clean = filename.strip()

        # Only plain file names inside data/ are allowed: no folders, no ../ tricks,
        # and never .env-style files.
        if (
            not filename_clean
            or Path(filename_clean).name != filename_clean
            or is_secret_name(filename_clean)
        ):
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **That file can't be exported.** Only plain file names from `data/` are allowed.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        # resolve() follows symlinks, so the parent check below also stops sneaky links
        file_path = (DATA_DIR / filename_clean).resolve()

        if file_path.parent != DATA_DIR or not file_path.is_file():
            embed = discord.Embed(
                description=f"<a:Cross:1514986232294281426> **Could not locate** `{filename_clean}` in `data/`.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        try:
            discord_file = discord.File(str(file_path), filename=file_path.name)
            embed = discord.Embed(
                description=f"<:Tick:1514986183489360087> **Successfully exported** `{file_path.name}`.",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed, file=discord_file)
        except discord.HTTPException as e:
            embed = discord.Embed(
                description=f"<a:Cross:1514986232294281426> **Failed to transmit file via Discord:**\n`{e}`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

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
