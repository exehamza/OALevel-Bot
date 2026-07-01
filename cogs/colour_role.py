import discord
from discord.ext import commands

# Dictionary mapping the Role ID (int) to its Name and Emoji
COLOR_ROLES = {
    1521157457223880867: {"name": "Pastel Pink", "emoji": "🌸"},
    1521157572864901150: {"name": "Lavender", "emoji": "💜"},
    1521157673754558584: {"name": "Mint", "emoji": "🍃"},
    1521157779040243883: {"name": "Peach", "emoji": "🍑"},
    1521157866327642202: {"name": "Crimson", "emoji": "🍁"},
    1521156274887065682: {"name": "Red", "emoji": "❤️"},
    1521156385906360370: {"name": "Orange", "emoji": "🧡"},
    1521156521470328943: {"name": "Yellow", "emoji": "💛"},
    1521156622997782528: {"name": "Lime", "emoji": "💚"},
    1521156709735989328: {"name": "Green", "emoji": "🌿"},
    1521156801230405742: {"name": "Cyan", "emoji": "🩵"},
    1521156860244136181: {"name": "Blue", "emoji": "💙"},
    1521156932755390614: {"name": "Purple", "emoji": "💜"},
    1521157020802220082: {"name": "Pink", "emoji": "🩷"},
    1521157098556096644: {"name": "White", "emoji": "🤍"},
    1521157168454172764: {"name": "Black", "emoji": "🖤"},
    1521157322745839717: {"name": "Brown", "emoji": "🤎"}
}

class ColorDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=data["name"], 
                value=str(role_id), 
                emoji=data["emoji"]
            )
            for role_id, data in COLOR_ROLES.items()
        ]
        super().__init__(placeholder="Choose your color role...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        selected_role_id = int(self.values[0])
        guild = interaction.guild
        member = interaction.user
        
        # 1. Find all color roles the user currently has from our list
        roles_to_remove = [
            guild.get_role(role_id) 
            for role_id in COLOR_ROLES.keys() 
            if member.get_role(role_id) is not None and role_id != selected_role_id
        ]
        
        # Remove valid roles (filtering out None just in case a role was deleted from the server)
        roles_to_remove = [r for r in roles_to_remove if r is not None]
        if roles_to_remove:
            await member.remove_roles(*roles_to_remove, reason="Changing color role")

        # 2. Add the new color role
        new_role = guild.get_role(selected_role_id)
        if new_role:
            if member.get_role(selected_role_id) is None:
                await member.add_roles(new_role, reason="Selected new color role")
                await interaction.followup.send(f"Success! Your color has been updated to **{COLOR_ROLES[selected_role_id]['name']}**.", ephemeral=True)
            else:
                await interaction.followup.send(f"You already have the **{COLOR_ROLES[selected_role_id]['name']}** role!", ephemeral=True)
        else:
            await interaction.followup.send("Error: Could not find that role on the server. Please contact an admin.", ephemeral=True)


class ColorDropdownView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180) # Dropdown expires after 3 minutes
        self.add_item(ColorDropdown())


class ColorCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="colour", aliases=["color"])
    async def color_command(self, ctx):
        embed = discord.Embed(
            title="Select Your Custom Color",
            description="Use the dropdown menu below to choose your name color!",
            color=0x2f3136
        )
        embed.set_footer(text="Only you can see the result of your selection.")
        
        view = ColorDropdownView()
        await ctx.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(ColorCog(bot))