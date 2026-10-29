import asyncio
import os
import aiohttp
import discord
from discord.ext import commands
from deep_translator import GoogleTranslator
from deep_translator.exceptions import LanguageNotSupportedException
from groq import AsyncGroq

# Map common names & codes so both Engines validate cleanly
LANGUAGE_ALIASES = {
    "en": "english", "eng": "english", "english": "english",
    "bn": "bengali", "bangla": "bengali", "bengali": "bengali",
    "ur": "urdu", "urdu": "urdu",
    "hi": "hindi", "hindi": "hindi",
    "es": "spanish", "spanish": "spanish",
    "fr": "french", "french": "french",
    "ar": "arabic", "arabic": "arabic",
    "ja": "japanese", "jp": "japanese", "japanese": "japanese",
    "de": "german", "german": "german",
    "zh": "chinese (simplified)", "chinese": "chinese (simplified)",
    "ru": "russian", "russian": "russian",
    "pt": "portuguese", "portuguese": "portuguese",
    "tr": "turkish", "turkish": "turkish",
    "ko": "korean", "korean": "korean",
    "it": "italian", "italian": "italian",
}


class Translate(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tick = "<:Tick:1514986183489360087>"
        self.cross = "<a:Cross:1514986232294281426>"

        api_key = os.getenv("GROQ_API_KEY")
        self.ai_client = AsyncGroq(api_key=api_key) if api_key else None
        self.model_name = "openai/gpt-oss-20b"

        try:
            self.supported_langs = GoogleTranslator().get_supported_languages(as_dict=True)
        except Exception:
            self.supported_langs = {}

    def resolve_language(self, target_lang: str) -> tuple[str | None, str | None]:
        """Returns (display_name, google_code) if valid, or (None, None) if unsupported."""
        cleaned = target_lang.lower().strip()
        normalized = LANGUAGE_ALIASES.get(cleaned, cleaned)

        if self.supported_langs:
            if normalized in self.supported_langs:
                return normalized.title(), self.supported_langs[normalized]
            for name, code in self.supported_langs.items():
                if normalized == code.lower():
                    return name.title(), code
            return None, None

        # Fallback if supported_langs dict couldn't be fetched on init
        if cleaned in LANGUAGE_ALIASES:
            return normalized.title(), cleaned
        return None, None

    async def translate_via_groq(self, text: str, target_display: str) -> str | None:
        """Uses Groq AI to accurately translate text (including Banglish & Roman Urdu)."""
        if not self.ai_client:
            return None

        response = await self.ai_client.chat.completions.create(
            model=self.model_name,
            temperature=0.1,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a precise translation engine. Translate the user's message into {target_display}. "
                        "The source text may be in any language, including phonetic/romanized scripts such as "
                        "Banglish (Romanized Bengali), Roman Urdu, Hinglish, or internet slang. "
                        "Output ONLY the translated text and nothing else—no quotes, no explanations, and no notes."
                    ),
                },
                {"role": "user", "content": text},
            ],
        )
        output = response.choices[0].message.content
        return output.strip() if output else None

    async def translate_via_google(self, text: str, lang_code: str) -> str | None:
        """Fallback async translator using Google's gtx endpoint and deep-translator."""
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": lang_code,
            "dt": "t",
            "q": text,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        if data and isinstance(data[0], list):
                            translated = "".join(segment[0] for segment in data[0] if segment and segment[0])
                            if translated.strip():
                                return translated.strip()
        except Exception:
            pass

        # Secondary fallback to deep-translator in a non-blocking thread
        return await asyncio.to_thread(
            lambda: GoogleTranslator(source="auto", target=lang_code).translate(text)
        )

    @commands.command(name="tr")
    async def translate_message(self, ctx, *, target_lang: str):
        """Translates a replied-to message using Groq AI + Google Translate fallback."""
        # 1. Check if the user actually replied to a message
        if not ctx.message.reference:
            embed = discord.Embed(
                description=f"{self.cross} You need to **reply** to the message you want to translate!",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        # 2. Validate target language
        display_lang, lang_code = self.resolve_language(target_lang)
        if not display_lang:
            embed = discord.Embed(
                description=f"{self.cross} `{target_lang}` is not a supported language.\n*Try 'english', 'bangla', 'urdu', 'es', 'french', etc.*",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        # 3. Fetch the original message that was replied to
        try:
            original_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        except (discord.NotFound, discord.HTTPException):
            embed = discord.Embed(
                description=f"{self.cross} Could not fetch the original message.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        if not original_msg.content or not original_msg.content.strip():
            embed = discord.Embed(
                description=f"{self.cross} There is no text in that message to translate.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        # 4. Perform the translation (Groq primary -> Google fallback)
        async with ctx.typing():
            translated_text = None

            try:
                translated_text = await self.translate_via_groq(original_msg.content, display_lang)
            except Exception as groq_err:
                print(f"[Translate] Groq fallback triggered: {groq_err}")

            if not translated_text:
                try:
                    translated_text = await self.translate_via_google(original_msg.content, lang_code)
                except LanguageNotSupportedException:
                    embed = discord.Embed(
                        description=f"{self.cross} `{target_lang}` is not a supported language.\n*Try 'english', 'bangla', 'urdu', 'es', 'french', etc.*",
                        color=discord.Color.red()
                    )
                    return await ctx.send(embed=embed)
                except Exception as google_err:
                    print(f"[Translate] Google fallback error: {google_err}")

            if not translated_text:
                embed = discord.Embed(
                    description=f"{self.cross} An error occurred during translation.",
                    color=discord.Color.red()
                )
                return await ctx.send(embed=embed)

            embed = discord.Embed(
                title=f"{self.tick} Translation Successful",
                description=translated_text,
                color=discord.Color.green()
            )
            embed.add_field(name="Target Language", value=display_lang, inline=True)
            embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)

    @commands.command(name="langs")
    async def show_languages(self, ctx):
        """Displays a few common language keywords and their abbreviations."""
        common_langs = (
            "**English:** `english` or `en`\n"
            "**Bangla:** `bangla`, `bengali`, or `bn`\n"
            "**Urdu:** `urdu` or `ur`\n"
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
