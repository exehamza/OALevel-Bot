import discord
from discord.ext import commands
import aiohttp
import io

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="steal", help="Steals an emoji or a replied sticker and adds it to this server.")
    @commands.has_permissions(administrator=True)
    async def steal(self, ctx, emoji: discord.PartialEmoji = None):
        
        # STICKER STEALING
        if ctx.message.reference:
            try:
                # Fetch the message that was replied to
                replied_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                
                if replied_msg.stickers:
                    sticker = replied_msg.stickers[0]
                    
                    # Guard clause: Standard built-in Discord stickers cannot be downloaded via URL
                    if sticker.url == "":
                        return await ctx.send("Cannot steal official/built-in Discord stickers. Try stealing a custom server sticker!")

                    async with ctx.typing():
                        # Download sticker image bytes
                        async with aiohttp.ClientSession() as session:
                            async with session.get(sticker.url) as resp:
                                if resp.status != 200:
                                    return await ctx.send("Failed to download the sticker.")
                                sticker_bytes = await resp.read()

                        # Determine the extension based on the sticker format type
                        file_format = sticker.format
                        if file_format == discord.StickerFormatType.gif:
                            filename = "sticker.gif"
                        elif file_format == discord.StickerFormatType.lottie:
                            return await ctx.send("Lottie (JSON-based animated) stickers are not supported for stealing.")
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

                        return await ctx.send(f"Sticker added successfully")
                
            except discord.NotFound:
                return await ctx.send("Could not find the replied message.")
            except discord.Forbidden:
                return await ctx.send("I don't have permission to manage stickers. Please check my 'Manage Expressions' permission.")
            except discord.HTTPException as e:
                print(e)  # Log error to console for debug
                return await ctx.send("Failed to add sticker. Server slots might be full, or file requirements weren't met.")

        # EMOJI STEALING
        if not emoji:
            return await ctx.send(f"Usage:\n• Reply to a sticker with `{ctx.prefix}steal` to steal a sticker.\n• Type `{ctx.prefix}steal <custom_emoji>` to steal an emoji.")

        if not emoji.id:
            return await ctx.send("Please provide a valid custom emoji. Standard emojis won't work.")

        async with ctx.typing():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(emoji.url) as resp:
                        if resp.status != 200:
                            return await ctx.send("Failed to download the emoji.")
                        emoji_bytes = await resp.read()

                new_emoji = await ctx.guild.create_custom_emoji(name=emoji.name, image=emoji_bytes)
                await ctx.send(f"Successfully added the emoji: {new_emoji} as `:{emoji.name}:`")

            except discord.Forbidden:
                await ctx.send("I don't have permission to manage emojis.")
            except discord.HTTPException:
                await ctx.send("Failed to add emoji. Check server slots or file constraints.")

    @steal.error
    async def steal_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need to be an Administrator to use this command.")

async def setup(bot):
    await bot.add_cog(Utility(bot))