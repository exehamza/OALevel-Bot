import discord
from discord.ext import commands
from config import Config  # Ensure Config.MODMAIL_CHANNEL_ID is defined here

class Modmail(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 1. Ignore messages sent by bots (including itself)
        if message.author.bot:
            return

        # 2. HARD FILTER: Stop command executions from being sent to the user
        clean_content = message.content.strip().lower()
        if clean_content.startswith(f"{Config.PREFIX}close"):
            return

        # 3. SECONDARY FILTER: Catch any other registered prefix commands
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        # 4. HANDLE INCOMING DMS (User -> Staff)
        if message.guild is None:
            modmail_channel = self.bot.get_channel(Config.MODMAIL_CHANNEL_ID)
            if not modmail_channel:
                print("Modmail error: Channel ID not found in config.")
                return

            # Look through existing active threads to see if this user already has an open ticket
            thread_name = f"Ticket-{message.author.id}"
            active_thread = None

            for thread in modmail_channel.threads:
                if thread.name == thread_name and not thread.archived:
                    active_thread = thread
                    break

            # If no active thread exists, create a brand new one
            if not active_thread:
                init_embed = discord.Embed(
                    title="🆕 New Modmail Ticket Created",
                    description=f"User: {message.author.mention} ({message.author.name})\nID: `{message.author.id}`",
                    color=discord.Color.blue()
                )
                
                staff_msg = await modmail_channel.send(embed=init_embed)
                active_thread = await staff_msg.create_thread(
                    name=thread_name,
                    auto_archive_duration=1440  # 24 hours
                )
                
                await message.author.send("✅ Your modmail ticket has been opened! Staff have been notified.")

            # Forward user's content
            user_embed = discord.Embed(
                description=message.content or "*[No text content]*",
                color=discord.Color.light_gray()
            )
            user_embed.set_author(name=message.author.name, icon_url=message.author.display_avatar.url)
            
            files = []
            if message.attachments:
                for attachment in message.attachments:
                    files.append(await attachment.to_file())

            await active_thread.send(embed=user_embed, files=files)
            await message.add_reaction("📬")

        # 4. HANDLE OUTGOING REPLIES (Staff -> User)
        elif isinstance(message.channel, discord.Thread):
            if message.channel.parent_id == Config.MODMAIL_CHANNEL_ID:
                if message.channel.name.startswith("Ticket-"):
                    try:
                        user_id = int(message.channel.name.replace("Ticket-", ""))
                    except ValueError:
                        return

                    try:
                        target_user = await self.bot.fetch_user(user_id)
                    except discord.NotFound:
                        return await message.channel.send("❌ Could not find that user. They may have left the server.")

                    reply_embed = discord.Embed(
                        title="💬 Staff Reply",
                        description=message.content,
                        color=discord.Color.green()
                    )
                    
                    files = []
                    if message.attachments:
                        for attachment in message.attachments:
                            files.append(await attachment.to_file())

                    try:
                        await target_user.send(embed=reply_embed, files=files)
                        await message.add_reaction("✅")
                    except discord.Forbidden:
                        await message.channel.send("❌ Unable to DM user. They likely closed their direct messages.")

    # 5. UTILITY COMMAND TO CLOSE TICKETS
    @commands.command(name="close")
    @commands.guild_only()
    @commands.has_permissions(manage_threads=True) # Recommended permission safety
    async def close_ticket(self, ctx):
        """Closes and archives a modmail thread."""
        if not isinstance(ctx.channel, discord.Thread) or ctx.channel.parent_id != Config.MODMAIL_CHANNEL_ID:
            return await ctx.send("❌ This command can only be used inside active modmail threads.")

        if not ctx.channel.name.startswith("Ticket-"):
            return

        user_id = int(ctx.channel.name.replace("Ticket-", ""))
        
        try:
            target_user = await self.bot.fetch_user(user_id)
            await target_user.send("🔒 Your modmail ticket has been closed by staff. If you need anything else, simply message me again!")
        except discord.Forbidden:
            pass # User closed DMs or left

        await ctx.send("🔒 Ticket closed. Archiving thread...")
        await ctx.channel.edit(archived=True, locked=True)

async def setup(bot):
    await bot.add_cog(Modmail(bot))