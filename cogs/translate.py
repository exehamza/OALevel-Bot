import discord
from discord.ext import commands
from deep_translator import GoogleTranslator
from deep_translator.exceptions import LanguageNotSupportedException

class Translate(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Custom Emojis
        self.tick = "<:Tick:1514986183489360087>"
        self.cross = "<a:Cross:1514986232294281426>"

    @commands.command(name="tr")
    async def translate_message(self, ctx, *, target_lang: str):
        """Translates a replied-to message using deep-translator."""
        
        # 1. Check if the user actually replied to a message
        if not ctx.message.reference:
            embed = discord.Embed(
                description=f"{self.cross} You need to **reply** to the message you want to translate!",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        # 2. Fetch the original message that was replied to
        try:
            original_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        except (discord.NotFound, discord.HTTPException):
            embed = discord.Embed(
                description=f"{self.cross} Could not fetch the original message.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        # Ensure there is text content to translate
        if not original_msg.content:
            embed = discord.Embed(
                description=f"{self.cross} There is no text in that message to translate.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        # 3. Perform the translation
        async with ctx.typing():
            try:
                # Translate text (auto-detects source language)
                translated_text = GoogleTranslator(
                    source='auto', 
                    target=target_lang.lower().strip()
                ).translate(original_msg.content)
                
                # 4. Send successful translation in an embed
                embed = discord.Embed(
                    title=f"{self.tick} Translation Successful",
                    description=translated_text,
                    color=discord.Color.green()
                )
                embed.add_field(name="Target Language", value=target_lang.title(), inline=True)
                embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
                
                await ctx.send(embed=embed)

            except LanguageNotSupportedException:
                embed = discord.Embed(
                    description=f"{self.cross} `{target_lang}` is not a supported language.\n*Try 'urdu', 'es', 'french', etc.*",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                
            except Exception as e:
                embed = discord.Embed(
                    description=f"{self.cross} An error occurred during translation.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                print(f"Translation Error: {e}")
    
    @commands.command(name="langs")
    async def show_languages(self, ctx):
        """Displays a few common language keywords and their abbreviations."""
        common_langs = (
            "**Urdu:** `urdu` or `ur`\n"
            "**English:** `english` or `en`\n"
            "**Spanish:** `spanish` or `es`\n"
            "**French:** `french` or `fr`\n"
            "**Arabic:** `arabic` or `ar`\n"
            "**Japanese:** `japanese` or `ja`\n"
            "**German:** `german` or `de`"
        )
        
        embed = discord.Embed(
            title="🌐 Supported Languages (Examples)",
            description=f"You can use either the full name or the code short-hand!\n\n{common_langs}",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Translate(bot))