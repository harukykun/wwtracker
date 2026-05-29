#file này là check token kèm gọi cog của bot, còn các command sẽ nằm trong cogs/wuwa_events.py
import asyncio
import logging
import sys
import discord
from discord.ext import commands

from config import DISCORD_TOKEN, GUILD_ID
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("wuwa.bot")


class WuwaBot(commands.Bot):

    def __init__(self):
        intents = discord.Intents.default()

        super().__init__(
            command_prefix="!",
            intents=intents,
            description="Wuthering Waves Event Version 3.3",
        )
    async def setup_hook(self):
        cog_list = [
            "cogs.wuwa_events",
        ]
        for cog in cog_list:
            try:
                await self.load_extension(cog)
                logger.info("Loaded cog: %s", cog)
            except Exception as e:
                logger.error("Failed to load cog %s: %s", cog, e, exc_info=True)

        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info("Synced commands to guild: %s", GUILD_ID)
        else:
            await self.tree.sync()
            logger.info("Synced commands globally")

    async def on_ready(self):
        logger.info("=" * 50)
        logger.info("Bot: %s (ID: %s)", self.user.name, self.user.id)
        logger.info("Guilds: %d", len(self.guilds))
        logger.info("WuWa Event Bot is ready!")
        logger.info("=" * 50)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Wuthering Waves Events Tracker Bot",
            )
        )


def main():
    """Entry point."""
    if not DISCORD_TOKEN or DISCORD_TOKEN == "your_bot_token_here":
        logger.error("DISCORD_TOKEN chưa được cấu hình!")
        sys.exit(1)

    bot = WuwaBot()

    try:
        bot.run(DISCORD_TOKEN, log_handler=None)
    except discord.LoginFailure:
        logger.error("Sai token")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Bot đã dừng.")


if __name__ == "__main__":
    main()
