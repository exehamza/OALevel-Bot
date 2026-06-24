import subprocess
import platform
import discord
from discord.ext import commands

# Define your allowed user IDs here (integers)
ALLOWED_USERS = {747007326619172924, 591206968291754006} # Replace with Main and Alt IDs

def is_allowed_user():
    """Custom check to see if the author is in the allowed list."""
    async def predicate(ctx):
        if ctx.author.id in ALLOWED_USERS:
            return True
        # Raise NotOwner to keep your existing error handler working seamlessly
        raise commands.NotOwner("You do not have permission to run this command.")
    return commands.check(predicate)

class SystemdControl(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="botstatus")
    @is_allowed_user() # <-- Swapped out @commands.is_owner() for our custom check
    async def get_system_status(self, ctx):
        """Fetches the system status dynamically depending on the OS."""
        await ctx.send("⌛ Fetching system status...")
        
        current_os = platform.system()
        
        try:
            if current_os == "Linux":
                result = subprocess.run(
                    ["systemctl", "status", "discord-bot.service"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                output = result.stdout if result.stdout else result.stderr
                
                # Sanitization
                output = output.replace("potato-Nitro-AN515-54", "linux-server")
                output = output.replace("/home/potato/OALevel-Bot/venv/bin/", "[venv]/")
                output = output.replace("/home/potato/", "~/")
                
            elif current_os == "Windows":
                result = subprocess.run(
                    ["cmd", "/c", "echo Windows Host Online && echo OS: Windows && systeminfo | findstr /B /C:\"OS Name\" /C:\"System Boot Time\""],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                output = f"⚠️ Running in Windows Environment (Local Test Mode):\n\n" + (result.stdout if result.stdout else result.stderr)
            else:
                output = f"Unsupported OS detected: {current_os}"

            if not output:
                output = "No output returned from the system."

            if len(output) > 1900:
                output = output[:1900] + "\n... [Output Truncated] ..."

            await ctx.send(f"```properties\n{output}\n```")

        except subprocess.TimeoutExpired:
            await ctx.send("❌ Error: The command timed out.")
        except Exception as e:
            await ctx.send(f"❌ An error occurred: `{str(e)}`")

    @get_system_status.error
    async def get_system_status_error(self, ctx, error):
        # This still catches the error seamlessly because we raised commands.NotOwner above
        if isinstance(error, commands.NotOwner):
            await ctx.send("⛔ You do not have permission to run this command.")

async def setup(bot):
    await bot.add_cog(SystemdControl(bot))