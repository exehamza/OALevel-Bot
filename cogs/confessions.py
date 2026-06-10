import discord
from discord.ext import commands
from config import Config
import random  # Used to generate a random tracking number

# A secure dictionary kept in the bot's temporary memory.
# Format: { confession_id: user_id }
# Staff cannot see this dictionary.
PENDING_CONFESSIONS = {}

# --- 1. THE MODAL ---
class ConfessionModal(discord.ui.Modal, title="Submit a Confession"):
    confession_input = discord.ui.TextInput(
        label="Your Confession",
        style=discord.TextStyle.long,
        placeholder="Type your deepest secret here... (It is completely anonymous)",
        max_length=1000,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("Thank you! Your confession has been sent for review.", ephemeral=True)
        
        approve_channel = interaction.guild.get_channel(Config.CONFESSION_APPROVE_ID)
        if not approve_channel:
            return

        # Generate a random 6-digit Confession ID to track it anonymously
        confession_id = random.randint(100000, 999999)
        
        # Save the relationship SECURELY in memory, away from staff eyes
        PENDING_CONFESSIONS[confession_id] = interaction.user.id

        approve_embed = discord.Embed(
            title="📥 New Confession Pending Approval",
            description=self.confession_input.value,
            color=discord.Color.yellow()
        )
        # Staff only see a random tracking number!
        approve_embed.set_footer(text=f"Confession ID: {confession_id}")

        await approve_channel.send(embed=approve_embed, view=ConfessionApprovalView())


# --- 2. THE SUBMIT BUTTON VIEW ---
class ConfessionSubmitView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Submit a Confession", style=discord.ButtonStyle.primary, custom_id="submit_confession_btn", emoji="🤫")
    async def callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ConfessionModal())


# --- 3. THE APPROVAL/REJECTION BUTTONS VIEW ---
# --- 3. THE APPROVAL/REJECTION BUTTONS VIEW ---
class ConfessionApprovalView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # Mandatory for persistent views

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, custom_id="approve_confession_btn", emoji="✅")
    async def approve_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1. Immediately acknowledge the interaction so Discord doesn't timeout/fail
        await interaction.response.defer()
        
        embed = interaction.message.embeds[0]
        confession_text = embed.description
        
        # 2. Extract the random tracking ID from the footer safely
        try:
            confession_id = int(embed.footer.text.replace("Confession ID: ", ""))
        except (ValueError, AttributeError):
            return await interaction.followup.send("❌ Error: Could not parse the Confession ID from this message.", ephemeral=True)

        # 3. Post to the public confessions channel
        public_channel = interaction.guild.get_channel(Config.CONFESSIONS_ID)
        if public_channel:
            public_embed = discord.Embed(
                title="🤫 Anonymous Confession",
                description=confession_text,
                color=discord.Color.purple()
            )
            public_msg = await public_channel.send(embed=public_embed)
            try:
                await public_msg.create_thread(name="Confession Discussion", auto_archive_duration=1440)
            except discord.HTTPException:
                pass # Skip if threads aren't supported or allowed in that channel

        # 4. Try to anonymously DM the user (Wrapped in a safety check)
        user_id = PENDING_CONFESSIONS.get(confession_id)
        if user_id:
            try:
                user = await interaction.client.fetch_user(user_id)
                await user.send("🎉 Your confession has been **approved** and published!")
            except discord.Forbidden:
                pass # User has DMs closed
            
            # Wipe from memory immediately for privacy
            del PENDING_CONFESSIONS[confession_id]
        else:
            # If the bot restarted, it won't find the user_id. 
            # We log it to staff quietly via an ephemeral message so they know why no DM went out.
            await interaction.followup.send("⚠️ Bot was restarted since submission. Confession approved publicly, but user could not be notified via DM.", ephemeral=True)

        # 5. Clean up and update the staff channel embed
        embed.title = f"✅ Confession #{confession_id} Approved"
        embed.color = discord.Color.green()
        embed.set_footer(text=f"Approved by {interaction.user.name}")
        await interaction.message.edit(embed=embed, view=None)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger, custom_id="reject_confession_btn", emoji="❌")
    async def reject_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        embed = interaction.message.embeds[0]
        
        try:
            confession_id = int(embed.footer.text.replace("Confession ID: ", ""))
        except (ValueError, AttributeError):
            return await interaction.followup.send("❌ Error: Could not parse the Confession ID from this message.", ephemeral=True)

        # Try to anonymously DM the user about the rejection
        user_id = PENDING_CONFESSIONS.get(confession_id)
        if user_id:
            try:
                user = await interaction.client.fetch_user(user_id)
                await user.send("❌ Sorry, your confession was **rejected** by the moderation team.")
            except discord.Forbidden:
                pass
            
            del PENDING_CONFESSIONS[confession_id]
        else:
            await interaction.followup.send("⚠️ Bot was restarted since submission. Confession rejected, but user could not be notified via DM.", ephemeral=True)

        # Clean up and update the staff channel embed
        embed.title = f"❌ Confession #{confession_id} Rejected"
        embed.color = discord.Color.red()
        embed.set_footer(text=f"Rejected by {interaction.user.name}")
        await interaction.message.edit(embed=embed, view=None)


# --- 4. THE COG & INITIAL COMMAND ---
class ConfessionCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="setupconfessions")
    @commands.has_permissions(administrator=True)
    async def setup_confessions(self, ctx):
        target_channel = ctx.guild.get_channel(Config.SUBMIT_CONFESSION_ID)
        
        if not target_channel:
            return await ctx.send("Could not find the submit channel specified in config.")

        embed = discord.Embed(
            title="🤫 Share a Confession",
            description=(
                "Got something on your mind? Share it completely anonymously!\n\n"
                "**How it works:**\n"
                "1️⃣ Click the button below.\n"
                "2️⃣ Type out your confession in the pop-up box.\n"
                "3️⃣ Submit it! It will be reviewed by staff before going public."
            ),
            color=discord.Color.blue()
        )
        
        await target_channel.send(embed=embed, view=ConfessionSubmitView())
        await ctx.send(f"Confession prompt successfully setup in {target_channel.mention}!")

async def setup(bot):
    await bot.add_cog(ConfessionCommands(bot))