import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import io
import os

# Replace 'YOUR_BOT_TOKEN' with your actual bot token
TOKEN = 'YOUR_BOT_TOKEN'
# Replace with the URL where your Flask API is running
API_URL = "http://localhost:5000/generate_map"

class EarthMCBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

client = EarthMCBot()

@client.tree.command(name="generate_map", description="Generate an EarthMC map")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(
    nation_names="Comma-separated list of nation names (optional)",
    town_names="Comma-separated list of town names (optional)",
    show_home_blocks="Show home blocks on the map",
    color_mode="Color mode for the map",
    star_size="Size of the home block stars"
)
@app_commands.choices(color_mode=[
    app_commands.Choice(name="No Colors", value="no_colors"),
    app_commands.Choice(name="Random", value="random"),
    app_commands.Choice(name="Number of Residents", value="numResidents"),
    app_commands.Choice(name="Number of Town Blocks", value="numTownBlocks"),
    app_commands.Choice(name="Number of Outlaws", value="numOutlaws"),
    app_commands.Choice(name="Number of Trusted", value="numTrusted"),
    app_commands.Choice(name="Overclaimable", value="Overclaimable"),
    app_commands.Choice(name="Population Density", value="Population Density"),
    app_commands.Choice(name="Snipeable", value="Snipeable"),
    app_commands.Choice(name="Mayor Last Online", value="Days Since Last Online")
])
async def generate_map(
    interaction: discord.Interaction,
    nation_names: str = "",
    town_names: str = "",
    show_home_blocks: bool = True,
    color_mode: str = "random",
    star_size: int = 250
):
    # Prepare request body
    map_data = {}

    # Only add provided parameters to the request body
    if nation_names:
        map_data['nation_names'] = nation_names
    if town_names:
        map_data['town_names'] = town_names
    if show_home_blocks is not None:
        map_data['show_home_blocks'] = show_home_blocks
    if color_mode:
        map_data['color_mode'] = color_mode
    map_data['star_size'] = star_size

    await interaction.response.defer()

    async with aiohttp.ClientSession() as session:
        async with session.post(API_URL, json=map_data) as response:
            if response.status == 200:
                image_data = await response.read()
                file = discord.File(io.BytesIO(image_data), filename="earthmc_map.png")
                await interaction.followup.send(file=file)
            else:
                error_message = await response.text()
                await interaction.followup.send(f"Error generating map: {error_message}")

@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('------')

client.run(TOKEN)
