import os
import io
import discord
from discord.ext import commands
from groq import AsyncGroq, RateLimitError, GroqError
import matplotlib.pyplot as plt

class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Safely pull Groq API Key
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is missing from your environment variables or .env file.")
            
        self.ai_client = AsyncGroq(api_key=api_key)
        
        # Updated active Groq model ID (llama-3.1-8b and llama-3.3-70b deprecated Aug 16, 2026)
        self.model_name = "openai/gpt-oss-20b"
        
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
        bg_color = '#313338'  # Discord modern dark background
        
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
        plt.close(fig)  # Prevents memory accumulation
        
        plt.rcdefaults()
        return buf

    async def send_formatted_response(self, ctx, messages_history: list):
        """Sends messages to Groq and processes output (text + LaTeX images)."""
        system_prompt = {
            "role": "system",
            "content": (
                "You are a helpful AI assistant. Keep responses concise and accurate. "
                "If the output involves complex math formulas, "
                "isolate the expression strictly inside double dollar signs on its own line like: $$E=mc^2$$. "
                "IMPORTANT MATPLOTLIB RULES: Generate standard, clean LaTeX. Always use \\bmod instead of \\mod. "
                "Ensure all \\left and \\right delimiters match exactly. Do not use \\begin or \\end environments inside the $$ blocks. "
                "If providing code, format it inside proper markdown code blocks."
            )
        }
        
        full_payload = [system_prompt] + messages_history

        async with ctx.typing():
            try:
                chat_completion = await self.ai_client.chat.completions.create(
                    messages=full_payload,
                    model=self.model_name,
                )
            except RateLimitError:
                return await ctx.send("⚠️ **Rate Limit Exceeded:** The Groq API rate limit was hit. Please wait a moment before asking again.")
            except GroqError as ge:
                print(f"Groq API Error: {ge}")
                return await ctx.send(f"⚠️ **Groq API Error:** {ge.message if hasattr(ge, 'message') else str(ge)}")
            except Exception as e:
                print(f"Unexpected Error: {e}")
                return await ctx.send("Something went wrong while processing your request.")

            output = chat_completion.choices[0].message.content
            if not output:
                return await ctx.send("The AI returned an empty response.")

            # Record AI output into local conversation state
            messages_history.append({"role": "assistant", "content": output})

            # Store references for ALL messages dispatched in this turn
            sent_messages = []

            if "$$" in output:
                parts = output.split("$$")
                for i, part in enumerate(parts):
                    content = part.strip()
                    if not content:
                        continue
                        
                    if i % 2 == 0:
                        # Process text content
                        if len(content) > 2000:
                            chunks = [content[j:j+1900] for j in range(0, len(content), 1900)]
                            for chunk in chunks:
                                msg = await ctx.send(chunk)
                                sent_messages.append(msg)
                        else:
                            msg = await ctx.send(content)
                            sent_messages.append(msg)
                    else:
                        # Direct single-pass string replacement fix for Matplotlib compatibility
                        latex_expression = content.replace('\\mod', '\\bmod').replace('\n', ' ')

                        try:
                            image_buffer = self.render_latex(latex_expression)
                            discord_file = discord.File(fp=image_buffer, filename=f"equation_{i}.png")
                            msg = await ctx.send(file=discord_file)
                            sent_messages.append(msg)
                        except Exception as render_err:
                            print(f"Render engine warning: {render_err}")
                            msg = await ctx.send(f"```{latex_expression}```")
                            sent_messages.append(msg)
            else:
                # Process purely text content
                if len(output) > 2000:
                    chunks = [output[i:i+1900] for i in range(0, len(output), 1900)]
                    for chunk in chunks:
                        msg = await ctx.send(chunk)
                        sent_messages.append(msg)
                else:
                    msg = await ctx.send(output)
                    sent_messages.append(msg)

            # Map the updated thread history to EVERY message generated during this turn
            for msg in sent_messages:
                self.conversations[msg.id] = messages_history

    @commands.command(name="ask")
    @commands.has_permissions(administrator=True)
    async def ask(self, ctx, *, query: str = None):
        """!ask [query] - Starts a new AI conversation."""
        if not query:
            return await ctx.send("Please provide a question for the AI.")

        history = [{"role": "user", "content": query}]
        await self.send_formatted_response(ctx, history)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listens for Admin replies to bot messages to continue existing threads."""
        if message.author.bot or not message.reference or not message.reference.message_id:
            return

        if not message.author.guild_permissions.administrator:
            return

        ref_id = message.reference.message_id

        # Verify if the target message belongs to an active thread chain
        if ref_id in self.conversations:
            history = self.conversations[ref_id]
            history.append({"role": "user", "content": message.content})
            
            ctx = await self.bot.get_context(message)
            await self.send_formatted_response(ctx, history)

    @ask.error
    async def ask_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You need **Administrator** permissions to use this command.")

async def setup(bot):
    await bot.add_cog(AIChat(bot))