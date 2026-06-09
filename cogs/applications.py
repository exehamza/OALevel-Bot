import discord
from discord.ext import commands
from config import Config

# --- THE APPLICATION FORM (MODAL FOR USER) ---
class StaffApplyModal(discord.ui.Modal, title="Staff Application Form"):
    mod_role = discord.ui.TextInput(label="Moderator Role", style=discord.TextStyle.paragraph, placeholder="What is the role of a moderator in a server", required=False, max_length=500)
    rules_knowlege = discord.ui.TextInput(label="Rules Knowledge", style=discord.TextStyle.paragraph, placeholder="How familiar are you with our server rules", required=False, max_length=500)
    member_assist = discord.ui.TextInput(label="New member assistance", style=discord.TextStyle.paragraph, placeholder="A new member joins but seems confused about how to navigate the server. How can you assist them?", required=False, max_length=500)
    spam_response = discord.ui.TextInput(label="Spam Response", style=discord.TextStyle.paragraph, placeholder="A member is spamming the chat with inappropriate content. How would you respond?", required=False, max_length=500)
    bias_response = discord.ui.TextInput(label="Bias Response", style=discord.TextStyle.paragraph, placeholder="A member accuses you of biasness. How would you address this allegation?", required=False, max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("⏳ Submitting your application...", ephemeral=True)

        target_channel = interaction.guild.get_channel(Config.STAFF_APPLICATIONS_ID)
        if not target_channel:
            return await interaction.edit_original_response(content="❌ Error: Could not find the staff applications logging channel.")

        embed_color = discord.Color.from_rgb(52, 152, 219)
        embed = discord.Embed(title="📥 New Staff Application", color=embed_color, timestamp=interaction.created_at)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="Applicant", value=f"{interaction.user.mention} ({interaction.user.name})", inline=False)
        embed.add_field(name="Applicant ID", value=str(interaction.user.id), inline=False) # Storing ID to track user
        embed.add_field(name="Moderator Role", value=self.mod_role.value or "None specified.", inline=False)
        embed.add_field(name="Rules Knowledge", value=self.rules_knowlege.value or "None specified.", inline=False)
        embed.add_field(name="New Member Assistance", value=self.member_assist.value or "None specified.", inline=False)
        embed.add_field(name="Spam Response", value=self.spam_response.value or "None specified.", inline=False)
        embed.add_field(name="Bias Response", value=self.bias_response.value or "None specified.", inline=False)

        # Send the embed WITH the AdminReviewView attached to it
        await target_channel.send(embed=embed, view=AdminReviewView())
        await interaction.edit_original_response(content="✅ Your application has been successfully submitted!")


# REJECTION REASON MODAL (FOR ADMINS)
class RejectionReasonModal(discord.ui.Modal, title="Application Rejection Reason"):
    reason = discord.ui.TextInput(
        label="Reason for Rejection",
        style=discord.TextStyle.paragraph,
        placeholder="Type the reason why this application was rejected...",
        required=True,
        max_length=500
    )

    def __init__(self, applicant: discord.User, message: discord.Message):
        super().__init__()
        self.applicant = applicant
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # 1. DM the user about the rejection
        try:
            await self.applicant.send(
                f"Thank you for applying to join our staff team. Unfortunately, your application has been declined for the following reason:\n\n> **{self.reason.value}**"
            )
            dm_status = "✅ Applicant DM'd successfully."
        except discord.Forbidden:
            dm_status = "⚠️ Could not DM applicant (DMs closed)."

        # 2. Edit the original staff-applications log embed to look "Rejected"
        embed = self.message.embeds[0]
        embed.color = discord.Color.red()
        embed.title = "❌ Staff Application [REJECTED]"
        embed.add_field(name="Status Action", value=f"Rejected by {interaction.user.mention}\n**Reason:** {self.reason.value}", inline=False)

        # 3. Update the log message and remove the buttons so they can't be clicked again
        await self.message.edit(embed=embed, view=None)
        await interaction.followup.send(f"Application rejected. {dm_status}", ephemeral=True)


# ADMIN ACTIONS BUTTON VIEW
class AdminReviewView(discord.ui.View):
    def __init__(self):
        # Persistent layout
        super().__init__(timeout=None)

    # Helper function to grab the applicant object using the ID saved inside the embed fields
    def get_applicant_from_embed(self, guild: discord.Guild, embed: discord.Embed):
        for field in embed.fields:
            if field.name == "Applicant ID":
                return guild.get_member(int(field.value))
        return None

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, custom_id="admin_accept_btn")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        embed = interaction.message.embeds[0]
        applicant = self.get_applicant_from_embed(interaction.guild, embed)

        if not applicant:
            return await interaction.followup.send("❌ Could not find that user in the server anymore.", ephemeral=True)
        
        # Assign the Moderator role automatically
        role = interaction.guild.get_role(Config.MODERATOR_ROLE_ID)
        if role:
            try:
                await applicant.add_roles(role)
                role_status = "✅ Role assigned."
            except discord.Forbidden:
                role_status = "⚠️ Failed to assign role (Bot permissions layout missing)."
        else:
            role_status = "❌ Role ID not found in server."

        # DM the user the congratulations message
        try:
            await applicant.send(f"🎉 **Congratulations!** Your staff application has been accepted. Welcome to the team!")
            dm_status = "✅ Applicant DM'd successfully."
        except discord.Forbidden:
            dm_status = "⚠️ Could not DM applicant (DMs closed)."

        # Update the layout of the log embed to look "Accepted"
        embed.color = discord.Color.green()
        embed.title = "✅ Staff Application [ACCEPTED]"
        embed.add_field(name="Status Action", value=f"Accepted by {interaction.user.mention}", inline=False)

        # Commit changes to log channel and strip out the action buttons
        await interaction.message.edit(embed=embed, view=None)
        await interaction.followup.send(f"Application accepted. {dm_status}", ephemeral=True)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger, custom_id="admin_reject_btn")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = interaction.message.embeds[0]
        applicant = self.get_applicant_from_embed(interaction.guild, embed)

        if not applicant:
            return await interaction.response.send_message("❌ Could not find that user in the server anymore.", ephemeral=True)

        # Open up the rejection input modal form directly on the Admin's display window
        await interaction.response.send_modal(RejectionReasonModal(applicant, interaction.message))


# THE COG INTERFACE
class Applications(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # Make sure both the setup button and review dashboard views register for persistence
        self.bot.add_view(ApplicationButtonView())
        self.bot.add_view(AdminReviewView())

    @commands.command(name="setupapps", help="Spawns the official setup embed message with the Application button.")
    @commands.has_permissions(administrator=True)
    async def setup_apps(self, ctx):
        if ctx.channel.id != Config.STAFF_APPLY_ID:
            return await ctx.send(f"❌ This setup command should only be executed inside the designated setup channel (<#{Config.STAFF_APPLY_ID}>).")

        embed = discord.Embed(
            title="🤝 Join the Staff Team!",
            description="Click the button below to fill out your application form.",
            color=0x2ecc71
        )
        await ctx.send(embed=embed, view=ApplicationButtonView())
        await ctx.message.delete()


class ApplicationButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Apply for Staff", style=discord.ButtonStyle.success, custom_id="persistent_apply_btn")
    async def apply_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(StaffApplyModal())

async def setup(bot):
    await bot.add_cog(Applications(bot))