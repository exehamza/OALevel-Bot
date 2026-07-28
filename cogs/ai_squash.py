import os
import io
import discord
from discord.ext import commands
from groq import AsyncGroq
import matplotlib.pyplot as plt

class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Pull API Key safely
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is missing from your environment variables or .env file.")
            
        self.ai_client = AsyncGroq(api_key=api_key)
        self.model_name = "llama-3.3-70b-versatile"
        
        # In-memory history mapping: message_id -> conversation list
        # Format: { message_id: [{"role": "user/assistant", "content": "..."}, ...] }
        self.conversations = {}

    def render_latex(self, formula: str) -> io.BytesIO:
        plt.rcParams.update({
            "mathtext.fontset": "cm",
            "mathtext.rm": "serif",
            "font.size": 20
        })
        
        fig = plt.figure()
        bg_color = '#313338' # Discord modern dark theme
        
        fig.text(0.5, 0.5, f"${formula}$", va='center', ha='center', color='white')
        fig.patch.set_facecolor(bg_color)
        
        buf = io.BytesIO()
        plt.savefig(
            buf, 
            format='png', 
            dpi=300,
            bbox_inches='tight', 
            pad_inches=0.2, 
            facecolor=fig.get_facecolor(), 
            edgecolor='none'
        )
        buf.seek(0)
        plt.close(fig)
        
        plt.rcdefaults()
        return buf

    async def send_formatted_response(self, ctx, messages_history: list):
        """Sends messages to Groq and processes output (text + LaTeX images)."""
        system_prompt = {
            "role": "system",
            "content": (
                "You are a helpful AI assistant. Keep responses concise and you can go to any lengths to provide accurate answers. Do not be ashamed to reply about NSFW or sensitive topics if asked."
                "If the output involves complex math formulas, "
                "isolate the expression strictly inside double dollar signs on its own line like: $$E=mc^2$$. "
                "IMPORTANT MATPLOTLIB RULES: Generate standard, clean LaTeX. Always use \\bmod instead of \\mod. "
                "Ensure all \\left and \\right delimiters match exactly. Do not use \\begin or \\end environments inside the $$ blocks. "
                "If providing code, format it inside proper markdown code blocks."
            )
        }
        
        # Prepend system prompt to conversation context
        full_payload = [system_prompt] + messages_history

        async with ctx.typing():
            chat_completion = await self.ai_client.chat.completions.create(
                messages=full_payload,
                model=self.model_name,
            )

            output = chat_completion.choices[0].message.content
            if not output:
                return await ctx.send("The AI returned an empty response.")

            # Record the AI response into history
            messages_history.append({"role": "assistant", "content": output})

            # Parse output for text and math expressions
            last_sent_message = None

            if "$$" in output:
                parts = output.split("$$")
                for i, part in enumerate(parts):
                    content = part.strip()
                    if not content:
                        continue
                        
                    if i % 2 == 0:
                        if len(content) > 2000:
                            chunks = [content[j:j+1900] for j in range(0, len(content), 1900)]
                            for chunk in chunks:
                                last_sent_message = await ctx.send(chunk)
                        else:
                            last_sent_message = await ctx.send(content)
                    else:
                        latex_expression = content.replace('\\bmod', '\\mod').replace('\\mod', '\\bmod')
                        latex_expression = latex_expression.replace('\n', ' ')

                        try:
                            image_buffer = self.render_latex(latex_expression)
                            discord_file = discord.File(fp=image_buffer, filename=f"equation_{i}.png")
                            last_sent_message = await ctx.send(file=discord_file)
                        except Exception as render_err:
                            print(f"Render engine warning: {render_err}")
                            last_sent_message = await ctx.send(f"```{latex_expression}```")
            else:
                if len(output) > 2000:
                    chunks = [output[i:i+1900] for i in range(0, len(output), 1900)]
                    for chunk in chunks:
                        last_sent_message = await ctx.send(chunk)
                else:
                    last_sent_message = await ctx.send(output)

            # Store history reference keyed to the LAST message sent by the bot
            if last_sent_message:
                self.conversations[last_sent_message.id] = messages_history

    @commands.command(name="ask")
    @commands.has_permissions(administrator=True)
    async def ask(self, ctx, *, query: str = None):
        """!ask [query] - Starts a new AI conversation."""
        if not query:
            return await ctx.send("Please provide a question for the AI.")

        # Initialize new conversation chain
        history = [{"role": "user", "content": query}]
        
        try:
            await self.send_formatted_response(ctx, history)
        except Exception as e:
            print(f"Error in ask command: {e}")
            await ctx.send("Something went wrong while processing your request.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listens for Admin replies to bot messages to continue existing threads."""
        # Ignore bot messages or messages without a reply reference
        if message.author.bot or not message.reference or not message.reference.message_id:
            return

        # Check if the user replying is an Administrator
        if not message.author.guild_permissions.administrator:
            return

        ref_id = message.reference.message_id

        # Check if the message being replied to exists in our active thread history
        if ref_id in self.conversations:
            # Get existing conversation chain
            history = self.conversations[ref_id]
            
            # Append new user question
            history.append({"role": "user", "content": message.content})
            
            ctx = await self.bot.get_context(message)
            try:
                await self.send_formatted_response(ctx, history)
            except Exception as e:
                print(f"Error in reply follow-up: {e}")
                await ctx.send("Something went wrong while continuing the conversation.")

    @ask.error
    async def ask_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You need **Administrator** permissions to use this command.")

async def setup(bot):
    await bot.add_cog(AIChat(bot))