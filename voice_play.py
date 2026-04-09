"""
Play an mp3 in a Discord voice channel.

The bot joins whichever voice channel DISCORD_USER_ID is currently in,
plays the audio, then disconnects.

Usage:
    python voice_play.py /path/to/file.mp3

Environment (via .env):
    DISCORD_BOT_TOKEN   — bot token
    DISCORD_GUILD_ID    — server (guild) ID
    DISCORD_USER_ID     — Jeff's Discord user ID (bot follows him into his vc)
"""
import os
import sys
import asyncio
import logging
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN   = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID    = int(os.getenv("DISCORD_GUILD_ID", "0"))
USER_ID     = int(os.getenv("DISCORD_USER_ID", "0"))

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING)


async def play_in_voice(mp3_path: str) -> None:
    intents = discord.Intents.default()
    intents.voice_states = True
    intents.guilds = True
    intents.members = True  # needed to look up which vc the user is in

    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready() -> None:
        guild = bot.get_guild(GUILD_ID)
        if guild is None:
            print(f"ERROR: guild {GUILD_ID} not found — check DISCORD_GUILD_ID in .env")
            await bot.close()
            return

        # Find which voice channel the target user is in
        member = guild.get_member(USER_ID)
        if member is None or member.voice is None or member.voice.channel is None:
            print("ERROR: target user is not in a voice channel")
            await bot.close()
            return

        vc_channel = member.voice.channel

        try:
            vc = await vc_channel.connect()
            source = discord.FFmpegPCMAudio(mp3_path)
            vc.play(source)

            # Wait for playback to finish
            while vc.is_playing():
                await asyncio.sleep(0.5)

            await vc.disconnect()
        except Exception as e:
            print(f"ERROR: {e}")
        finally:
            await bot.close()

    await bot.start(BOT_TOKEN)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python voice_play.py /path/to/audio.mp3")
        sys.exit(1)

    mp3_path = sys.argv[1]
    if not os.path.exists(mp3_path):
        print(f"ERROR: file not found: {mp3_path}")
        sys.exit(1)

    asyncio.run(play_in_voice(mp3_path))
