import discord
from discord.ext import commands
import aiohttp
import io
import asyncio
import platform
import subprocess

# STEAL

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ping", help="Pings Discord's gateway or an external host like google.com.")
    async def ping(self, ctx, host: str = None):
        # Case 1: Standard $ping without arguments (Checks Discord Latency)
        if not host:
            discord_ping = round(self.bot.latency * 1000)
            return await ctx.send(f"🏓 Pong! Discord API latency is `{discord_ping}ms`.")

        # Case 2: $ping google.com (Checks external website latency)
        # Clean up the input to prevent malicious command injections
        host = host.replace("http://", "").replace("https://", "").split("/")[0].strip()

        await ctx.send(f"Sending packets to `{host}`... please wait.")

        # Determine command flags based on host operating system (Windows uses -n, Linux uses -c)
        param = "-n" if platform.system().lower() == "windows" else "-c"
        command = ["ping", param, "3", host]

        try:
            # Run the system terminal ping asynchronously so it doesn't block the bot
            loop = asyncio.get_event_loop()
            process = await loop.run_in_executor(
                None, 
                lambda: subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            )

            if process.returncode == 0:
                # Successfully got a response from the host
                await ctx.send(f"Successfully reached `{host}`!\n```text\n{process.stdout}\n```")
            else:
                # Request timed out or host didn't respond
                await ctx.send(f"Failed to ping `{host}`. The host might be down, or blocking ICMP packets.")
                
        except asyncio.TimeoutError:
            await ctx.send(f"⏱️ Connection to `{host}` timed out after 5 seconds.")
        except Exception as e:
            await ctx.send(f"⚠️ An internal system error occurred: `{str(e)}`")

    @commands.command(name="steal", help="Steals an emoji or a replied sticker and adds it to this server.")
    @commands.has_permissions(administrator=True)
    async def steal(self, ctx, emoji: discord.PartialEmoji = None):
        
        # --- CONFIGURATION ---
        # Paste your exact extracted emoji strings here:
        TICK = "<:Tick:1514986183489360087>"   
        CROSS = "<a:Cross:1514986232294281426>" 

        EMBED_COLOR_SUCCESS = discord.Color.green()
        EMBED_COLOR_FAIL = discord.Color.red()
        # ---------------------

        # STICKER STEALING
        if ctx.message.reference:
            try:
                # Fetch the message that was replied to
                replied_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                
                if replied_msg.stickers:
                    sticker = replied_msg.stickers[0]
                    
                    # Guard clause: Standard built-in Discord stickers cannot be downloaded via URL
                    if sticker.url == "":
                        embed = discord.Embed(
                            description=f"{CROSS} Cannot steal official/built-in Discord stickers. Try stealing a custom server sticker!",
                            color=EMBED_COLOR_FAIL
                        )
                        return await ctx.send(embed=embed)

                    async with ctx.typing():
                        # Download sticker image bytes
                        async with aiohttp.ClientSession() as session:
                            async with session.get(sticker.url) as resp:
                                if resp.status != 200:
                                    embed = discord.Embed(description=f"{CROSS} Failed to download the sticker.", color=EMBED_COLOR_FAIL)
                                    return await ctx.send(embed=embed)
                                sticker_bytes = await resp.read()

                        # Determine the extension based on the sticker format type
                        file_format = sticker.format
                        if file_format == discord.StickerFormatType.gif:
                            filename = "sticker.gif"
                        elif file_format == discord.StickerFormatType.lottie:
                            embed = discord.Embed(description=f"{CROSS} Lottie (JSON-based animated) stickers are not supported for stealing.", color=EMBED_COLOR_FAIL)
                            return await ctx.send(embed=embed)
                        else:
                            filename = "sticker.png"  # Handles PNG and APNG frames safely

                        # Wrap raw bytes cleanly into a discord File object
                        sticker_file = discord.File(io.BytesIO(sticker_bytes), filename=filename)
                        
                        # Upload the sticker to the server
                        new_sticker = await ctx.guild.create_sticker(
                            name=sticker.name,
                            description=f"Stolen sticker",
                            emoji="⭐",  # The representative standard emoji required by Discord
                            file=sticker_file
                        )

                        embed = discord.Embed(
                            description=f"{TICK} Sticker **{sticker.name}** added successfully!",
                            color=EMBED_COLOR_SUCCESS
                        )
                        return await ctx.send(embed=embed)
                
            except discord.NotFound:
                embed = discord.Embed(description=f"{CROSS} Could not find the replied message.", color=EMBED_COLOR_FAIL)
                return await ctx.send(embed=embed)
            except discord.Forbidden:
                embed = discord.Embed(description=f"{CROSS} I don't have permission to manage stickers. Please check my **Manage Expressions** permission.", color=EMBED_COLOR_FAIL)
                return await ctx.send(embed=embed)
            except discord.HTTPException as e:
                print(e)  # Log error to console for debug
                embed = discord.Embed(description=f"{CROSS} Failed to add sticker. Server slots might be full, or file requirements weren't met.", color=EMBED_COLOR_FAIL)
                return await ctx.send(embed=embed)

        # EMOJI STEALING
        if not emoji:
            embed = discord.Embed(
                title="Command Usage",
                description=f"• Reply to a sticker with `{ctx.prefix}steal` to steal a sticker.\n• Type `{ctx.prefix}steal <custom_emoji>` to steal an emoji.",
                color=discord.Color.blue()
            )
            return await ctx.send(embed=embed)

        if not emoji.id:
            embed = discord.Embed(description=f"{CROSS} Please provide a valid custom emoji. Standard emojis won't work.", color=EMBED_COLOR_FAIL)
            return await ctx.send(embed=embed)

        async with ctx.typing():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(emoji.url) as resp:
                        if resp.status != 200:
                            embed = discord.Embed(description=f"{CROSS} Failed to download the emoji.", color=EMBED_COLOR_FAIL)
                            return await ctx.send(embed=embed)
                        emoji_bytes = await resp.read()

                new_emoji = await ctx.guild.create_custom_emoji(name=emoji.name, image=emoji_bytes)
                
                embed = discord.Embed(
                    description=f"{TICK} Successfully added the emoji {new_emoji} as `:{emoji.name}:`",
                    color=EMBED_COLOR_SUCCESS
                )
                await ctx.send(embed=embed)

            except discord.Forbidden:
                embed = discord.Embed(description=f"{CROSS} I don't have permission to manage emojis.", color=EMBED_COLOR_FAIL)
                await ctx.send(embed=embed)
            except discord.HTTPException:
                embed = discord.Embed(description=f"{CROSS} Failed to add emoji. Check server slots or file constraints.", color=EMBED_COLOR_FAIL)
                await ctx.send(embed=embed)

    @steal.error
    async def steal_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                # Use the CROSS variable here so it renders correctly
                description=f"<:Cross:987654321098765432> You need to be an **Administrator** to use this command.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Utility(bot))