import datetime
import discord
from discord.ext import commands

class Avatar(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="avatar", aliases=["av", "pfp"], help="Displays a user's avatar.")
    async def avatar(self, ctx, member: discord.Member = None):
        # If no member is mentioned, default to the author of the command
        member = member or ctx.author

        # Use the member's server-specific avatar if they have one; otherwise, use their global avatar
        avatar_url = member.display_avatar.url

        embed = discord.Embed(
            title=f"{member.name}'s Avatar",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        
        # Set the main image of the embed to the avatar URL
        embed.set_image(url=avatar_url)
        
        # Optional: Adds a clean footer showing who requested it
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)

        await ctx.send(embed=embed)

# This setup function must be outside the class for the bot to load the cog
async def setup(bot):
    await bot.add_cog(Avatar(bot))