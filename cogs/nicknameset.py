import discord
from discord.ext import commands

class NicknameCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sn")
    @commands.has_permissions(manage_nicknames=True)
    async def set_nickname(self, ctx, member: discord.Member, *, nickname: str = None):
        """
        Changes a user's nickname. 
        Usage: $sn @user New Nickname
        To reset nickname: $sn @user
        """
        # Delete the trigger message right away
        try: 
            await ctx.message.delete()
        except discord.HTTPException: 
            pass

        # Prevent the bot from trying to change the server owner's nickname
        if member == ctx.guild.owner:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **I cannot change the server owner's nickname.**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        # Check if the bot's highest role is lower than the target member's highest role
        if ctx.guild.me.top_role <= member.top_role:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **I don't have a high enough role to change this user's nickname.**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        try:
            old_name = member.display_name
            await member.edit(nick=nickname)
            
            if nickname:
                embed = discord.Embed(
                    description=f"<:Tick:1514986183489360087> Changed **{old_name}**'s nickname to **{nickname}**.",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    description=f"<:Tick:1514986183489360087> Reset **{old_name}**'s nickname back to default.",
                    color=discord.Color.green()
                )
            await ctx.send(embed=embed)
                
        except discord.Forbidden:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **I do not have permission to change this user's nickname.**",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        except discord.HTTPException:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **Something went wrong while updating the nickname.**",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    # Error handling for the command
    @set_nickname.error
    async def nickname_error(self, ctx, error):
        # Even on errors, try to clear the command trigger 
        try: 
            await ctx.message.delete()
        except discord.HTTPException: 
            pass

        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **You do not have the Manage Nicknames permission to use this command.**",
                color=discord.Color.red()
            )
        elif isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **Missing arguments.** Usage: `$sn @user <New Nickname>`",
                color=discord.Color.red()
            )
        elif isinstance(error, commands.BadArgument):
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **Could not find that user.** Make sure you are mentioning them or using their ID.",
                color=discord.Color.red()
            )
        else:
            embed = discord.Embed(
                description=f"<a:Cross:1514986232294281426> **An unexpected error occurred:**\n`{error}`",
                color=discord.Color.red()
            )
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(NicknameCog(bot))