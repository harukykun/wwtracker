import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from cogs.scraper import scraper
from cogs.renderer import renderer

logger = logging.getLogger("wuwa.cog")


class TimelineView(discord.ui.View):

    def __init__(self, author_id: int, view_offset: int = 0, filter_type: str = "all"):
        super().__init__(timeout=300)  # 5 phút timeout
        self.author_id = author_id
        self.view_offset = view_offset  # offset tuần (0 = hiện tại, -1 = tuần trước, +1 = tuần sau)
        self.filter_type = filter_type
        self._update_button_styles()

    def _update_button_styles(self):
        # Cập nhật filter buttons
        self.btn_all.style = discord.ButtonStyle.primary if self.filter_type == "all" else discord.ButtonStyle.secondary
        self.btn_banner.style = discord.ButtonStyle.primary if self.filter_type == "banner" else discord.ButtonStyle.secondary
        self.btn_event.style = discord.ButtonStyle.primary if self.filter_type == "event" else discord.ButtonStyle.secondary

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Only the command user can interact with this!", ephemeral=True
            )
            return False
        return True

    async def _update_message(self, interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            events = await scraper.get_events()
            now = datetime.now(timezone.utc)
            view_start = now - timedelta(days=3) + timedelta(weeks=self.view_offset)

            image_buf = renderer.render(
                events,
                view_start=view_start,
                filter_type=self.filter_type,
            )

            self._update_button_styles()

            # Tạo embed
            embed = self._build_embed(view_start)

            file = discord.File(image_buf, filename="wuwa_timeline.png")
            embed.set_image(url="attachment://wuwa_timeline.png")

            await interaction.edit_original_response(
                embed=embed, attachments=[file], view=self
            )
        except Exception as e:
            logger.error("Lỗi cập nhật: %s", e)
            await interaction.followup.send(
                f"❌ An error occurred: {e}", ephemeral=True
            )

    def _build_embed(self, view_start: datetime) -> discord.Embed:
        now = datetime.now(timezone.utc)
        view_end = view_start + timedelta(days=21)

        embed = discord.Embed(
            color=discord.Color.from_rgb(255, 200, 50),
        )
        embed.set_author(
            name="Wuthering Waves Event Timeline",
        )

        # Thông tin view
        range_text = f"📅 {view_start.strftime('%d/%m')} → {view_end.strftime('%d/%m/%Y')}"
        filter_text = {"all": "All", "banner": "Banner", "event": "Event"}
        embed.set_footer(
            text=f"{range_text}  •  {filter_text.get(self.filter_type, '')}"
        )

        return embed

    # === Navigation Buttons ===
    @discord.ui.button(label="Prev", style=discord.ButtonStyle.secondary, custom_id="prev_week", row=0)
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.view_offset -= 1
        await self._update_message(interaction)

    @discord.ui.button(label="Today", style=discord.ButtonStyle.success, custom_id="today", row=0)
    async def btn_today(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.view_offset = 0
        await self._update_message(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, custom_id="next_week", row=0)
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.view_offset += 1
        await self._update_message(interaction)

    # === Filter Buttons ===
    @discord.ui.button(label="All", style=discord.ButtonStyle.primary, custom_id="filter_all", row=1)
    async def btn_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.filter_type = "all"
        await self._update_message(interaction)

    @discord.ui.button(label="Banner", style=discord.ButtonStyle.secondary, custom_id="filter_banner", row=1)
    async def btn_banner(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.filter_type = "banner"
        await self._update_message(interaction)

    @discord.ui.button(label="Event", style=discord.ButtonStyle.secondary, custom_id="filter_event", row=1)
    async def btn_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.filter_type = "event"
        await self._update_message(interaction)

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True


class WuwaEvents(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="wuwaevt", description="Show Wuthering Waves Event Timeline")
    async def wuwaevt(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        try:
            # Scrape events
            events = await scraper.get_events()

            if not events:
                await interaction.followup.send(
                    "❌ No events found. Please try again later!",
                    ephemeral=True,
                )
                return

            # Render ảnh
            now = datetime.now(timezone.utc)
            view_start = now - timedelta(days=3)

            image_buf = renderer.render(events, view_start=view_start)

            # Tạo view với buttons
            view = TimelineView(author_id=interaction.user.id)

            # Tạo embed
            embed = view._build_embed(view_start)
            file = discord.File(image_buf, filename="wuwa_timeline.png")
            embed.set_image(url="attachment://wuwa_timeline.png")

            await interaction.followup.send(embed=embed, file=file, view=view)

            logger.info(
                "Đã gửi timeline cho %s (%d events)",
                interaction.user.name,
                len(events),
            )

        except Exception as e:
            logger.error("Lỗi xử lý /wuwaevt: %s", e, exc_info=True)
            await interaction.followup.send(
                f"❌ An error occurred while fetching data:\n```{e}```\nPlease try again later!",
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(WuwaEvents(bot))
    logger.info("WuwaEvents cog loaded")
