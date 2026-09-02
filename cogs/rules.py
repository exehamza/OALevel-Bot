import discord
from discord.ext import commands

class Rules(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Dictionary storing the rules data
        self.rules_dict = {
            1: {
                "title": "Rule 1. Follow Discord’s Terms of Service & Community Guidelines",
                "desc": "https://discordapp.com/terms | https://discordapp.com/guidelines"
            },
            2: {
                "title": "Rule 2. No Malpractice or Exam Security Violations",
                "desc": "Requesting, sharing, discussing, hinting at, or distributing leaked exam material is strictly forbidden. Any attempt to engage in academic dishonesty may result in an immediate and permanent ban without warning."
            },
            3: {
                "title": "Rule 3. No Malicious Content",
                "desc": "No malicious links, viruses, malware, phishing attempts, or files that could harm users, compromise accounts or disrupt the community."
            },
            4: {
                "title": "Rule 4. No Unapproved Advertising, Self-Promotion or Services",
                "desc": "No unauthorised promotion of products, services, courses, tutoring, commissions, social media accounts, websites or external servers. This includes direct messages sent to members for promotional purposes."
            },
            5: {
                "title": "Rule 5. Be Respectful & Maintain a Civil Environment",
                "desc": "No hate speech, racism, discrimination, personal attacks, threats, bullying, targeted harassment or behaviour intended to make others uncomfortable."
            },
            6: {
                "title": "Rule 6. No Controversial Discussions",
                "desc": "Discussions involving politics, ideologies, wars, religion, sexual orientations, deaths, tragedies or other sensitive subjects are not permitted. Staff may restrict any conversation deemed likely to create conflict or disrupt the community."
            },
            7: {
                "title": "Rule 7. No Inappropriate Behaviour",
                "desc": "Sexual remarks, explicit jokes, suggestive comments, or flirtatious roleplay are prohibited if they create an uncomfortable environment, even if intended as a joke. However, subjective humor and mutual jesting between consenting individuals are permitted, provided they remain within reasonable parameters and do not cross into non-consensual harassment, explicitly graphic or crude language, or compromise the comfort of the general community."
            },
            8: {
                "title": "Rule 8. No NSFW or Disturbing Content",
                "desc": "No pornography, gore, graphic content, shock content or other material considered inappropriate."
            },
            9: {
                "title": "Rule 9. Do Not Ping or DM Staff Without a Valid Reason",
                "desc": "Do not unnecessarily ping or repeatedly direct message moderators or management members. Staff are not required to respond to personal requests."
            },
            10: {
                "title": "Rule 10. No Attempting to Bypass Filters or Restricted Content",
                "desc": "No slur bypassing, alternate spellings, disguised profanity intended to evade filter."
            },
            11: {
                "title": "Rule 11. No Spamming or Flooding Channels",
                "desc": "No excessive messages, emojis, copypasta, repeated content or bot spam outside of the bot-commands channels"
            },
            12: {
                "title": "Rule 12. English is the Primary Language",
                "desc": "English should be used throughout the server. However, the use of Roman Urdu and Bengali are also allowed. Staff may ask users to switch languages if communication becomes difficult to moderate."
            },
            13: {
                "title": "Rule 13. Use Channels for Their Intended Purpose",
                "desc": "Subject-related questions should be posted in the appropriate subject channels. General conversation should remain within the designated chat channels."
            },
            14: {
                "title": "Rule 14. No Inappropriate Usernames, Profile Pictures or Banners",
                "desc": "Usernames, avatars, display names, and banners must not contain NSFW content, hate speech, impersonation, extremist symbolism or other offensive material. Users may be required to change them or face penalties"
            }
        }

    @commands.command(name="rule")
    async def rule_command(self, ctx, number: int = None):
        """Posts a specific server rule in an embed."""
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

        if number is None:
            missing_embed = discord.Embed(
                description="<a:Cross:1514986232294281426> Please specify a rule number.\n\n**Usage:** `$rule [1-14]`",
                color=discord.Color.red()
            )
            await ctx.send(embed=missing_embed, delete_after=10)
            return

        if number not in self.rules_dict:
            invalid_embed = discord.Embed(
                description=f"<a:Cross:1514986232294281426> Rule `{number}` does not exist.\n\nPlease choose a valid rule number between **1 and 14**.",
                color=discord.Color.red()
            )
            await ctx.send(embed=invalid_embed, delete_after=10)
            return

        rule_data = self.rules_dict[number]
        formatted_desc = f"<:dot:1514986489186877440> {rule_data['desc']}"

        embed = discord.Embed(
            title=rule_data["title"],
            description=formatted_desc,
            color=discord.Color.blue()
        )
        
        await ctx.send(embed=embed)

    @commands.command(name="setuprules")
    @commands.has_permissions(administrator=True)
    async def setup_rules_command(self, ctx):
        """Sends a single massive embed containing all server rules using quote blocks."""
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

        rules_embed = discord.Embed(
            title="📜 Server Rules & Community Guidelines",
            description="Welcome to the server! Please read through and respect our guidelines to ensure a clean, safe, and productive community for everyone.\n\n",
            color=discord.Color.blue()
        )

        for number, rule_data in self.rules_dict.items():
            # The > symbol creates the blockquote layout under the field header inside Discord
            formatted_desc = f"> <:dot:1514986489186877440> {rule_data['desc']}\n\n"
            
            rules_embed.add_field(
                name=rule_data["title"],
                value=formatted_desc,
                inline=False
            )

        rules_embed.set_footer(text="Compliance with these rules is mandatory. Violations will lead to administrative action.")

        await ctx.send(embed=rules_embed)

    @setup_rules_command.error
    async def setup_rules_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            error_embed = discord.Embed(
                description="<a:Cross:1514986232294281426> You do not have permission to run this setup utility.",
                color=discord.Color.red()
            )
            await ctx.send(embed=error_embed, delete_after=10)

async def setup(bot):
    await bot.add_cog(Rules(bot))
