
import io
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from config import (
    BG_COLOR, HEADER_BG, GRID_LINE_COLOR, TEXT_COLOR, TEXT_DIM,
    NOW_LINE_COLOR, AXIS_TEXT_COLOR,
    IMAGE_WIDTH, BAR_HEIGHT, BAR_GAP, HEADER_HEIGHT,
    PADDING_LEFT, PADDING_RIGHT, PADDING_TOP, PADDING_BOTTOM,
    DAYS_PER_VIEW,
)

logger = logging.getLogger("wuwa.renderer")

# English month names
MONTH_NAMES = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Cache ảnh event đã load
_image_cache: dict[str, Image.Image] = {}


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    font_candidates = []
    if bold:
        font_candidates = [
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/tahomabd.ttf",
        ]
    else:
        font_candidates = [
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/tahoma.ttf",
        ]
    for path in font_candidates:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _lighten_color(color: tuple[int, int, int], factor: float = 0.3) -> tuple[int, int, int]:
    r, g, b = color
    return (
        min(255, int(r + (255 - r) * factor)),
        min(255, int(g + (255 - g) * factor)),
        min(255, int(b + (255 - b) * factor)),
    )


def _ensure_readable_color(color: tuple[int, int, int]) -> tuple[int, int, int]:
    r, g, b = color
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    if luminance < 40:
        return _lighten_color(color, 0.4)
    return color


def _load_event_image(image_path: str, target_height: int) -> Image.Image | None:
    if not image_path:
        return None

    # Dùng cache
    cache_key = f"{image_path}_{target_height}"
    if cache_key in _image_cache:
        return _image_cache[cache_key]

    try:
        path = Path(image_path)
        if not path.exists():
            return None

        img = Image.open(path).convert("RGBA")

        # Resize giữ tỷ lệ, fit vào chiều cao bar
        ratio = target_height / img.height
        new_width = int(img.width * ratio)
        img = img.resize((new_width, target_height), Image.Resampling.LANCZOS)

        _image_cache[cache_key] = img
        return img
    except Exception as e:
        logger.debug("Không load được ảnh %s: %s", image_path, e)
        return None


def _create_gradient_mask(width: int, height: int, fade_width: int = 30) -> Image.Image:
    mask = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(mask)

    # Fade bên trái
    for x in range(min(fade_width, width)):
        alpha = int(255 * (x / fade_width))
        draw.line([(x, 0), (x, height)], fill=alpha)

    return mask


class TimelineRenderer:

    def __init__(self):
        self.font_title = _get_font(22, bold=True)
        self.font_month = _get_font(18, bold=True)
        self.font_day_name = _get_font(11)
        self.font_day_num = _get_font(13)
        self.font_event = _get_font(13, bold=True)
        self.font_countdown = _get_font(11, bold=True)
        self.font_footer = _get_font(11)

    def render(
        self,
        events: list,
        view_start: datetime | None = None,
        days: int = DAYS_PER_VIEW,
        filter_type: str = "all",
    ) -> io.BytesIO:
        now = datetime.now(timezone.utc)
        if view_start is None:
            view_start = now - timedelta(days=3)

        view_end = view_start + timedelta(days=days)

        # Filter events
        filtered = self._filter_events(events, view_start, view_end, filter_type)

        # Tính kích thước ảnh
        chart_width = IMAGE_WIDTH - PADDING_LEFT - PADDING_RIGHT
        num_bars = len(filtered)
        chart_height = num_bars * (BAR_HEIGHT + BAR_GAP) + BAR_GAP
        total_height = HEADER_HEIGHT + chart_height + PADDING_TOP + PADDING_BOTTOM + 40

        # Tạo ảnh
        img = Image.new("RGBA", (IMAGE_WIDTH, total_height), BG_COLOR + (255,))
        draw = ImageDraw.Draw(img)

        # Vẽ header background
        draw.rectangle(
            [(0, 0), (IMAGE_WIDTH, HEADER_HEIGHT + PADDING_TOP)],
            fill=HEADER_BG + (255,),
        )

        # Vẽ trục thời gian
        self._draw_date_axis(draw, view_start, days, chart_width, now)

        # Vẽ grid lines dọc
        self._draw_grid_lines(draw, view_start, days, chart_width, total_height)

        # Vẽ các event bars (cần truyền img để paste ảnh)
        y_offset = HEADER_HEIGHT + PADDING_TOP
        for event in filtered:
            self._draw_event_bar(img, draw, event, view_start, view_end, days, chart_width, y_offset, now)
            y_offset += BAR_HEIGHT + BAR_GAP

        # Vẽ đường NOW (vẽ đè lên trên bars)
        self._draw_now_line(draw, view_start, days, chart_width, now, total_height)

        # Vẽ footer
        footer_y = total_height - PADDING_BOTTOM - 5
        footer_text = f"Updated: {now.strftime('%H:%M %d/%m/%Y')} UTC"
        draw.text(
            (IMAGE_WIDTH // 2, footer_y),
            footer_text,
            fill=TEXT_DIM,
            font=self.font_footer,
            anchor="mm",
        )

        # Xuất ảnh
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        return buf

    def _filter_events(self, events, view_start, view_end, filter_type):
        filtered = []
        for ev in events:
            if ev.end_date < view_start or ev.start_date > view_end:
                continue
            if filter_type == "banner" and not ev.is_banner:
                continue
            if filter_type == "event" and ev.is_banner:
                continue
            filtered.append(ev)
        return filtered

    def _draw_date_axis(self, draw: ImageDraw.Draw, view_start, days, chart_width, now):
        px_per_day = chart_width / days
        current_month = None

        for i in range(days + 1):
            date = view_start + timedelta(days=i)
            x = PADDING_LEFT + i * px_per_day

            if date.month != current_month:
                current_month = date.month
                month_text = MONTH_NAMES.get(date.month, f"T{date.month}")
                draw.text(
                    (x + 2, PADDING_TOP + 2),
                    month_text,
                    fill=(255, 200, 80),
                    font=self.font_month,
                )

            day_name = DAY_NAMES[date.weekday()]
            day_color = TEXT_DIM if date.weekday() < 5 else (255, 150, 100)
            draw.text(
                (x + px_per_day / 2, PADDING_TOP + 28),
                day_name,
                fill=day_color,
                font=self.font_day_name,
                anchor="mt",
            )

            is_today = date.date() == now.date()
            if is_today:
                badge_w, badge_h = 24, 18
                bx = x + px_per_day / 2
                draw.rounded_rectangle(
                    [(bx - badge_w / 2, PADDING_TOP + 40), (bx + badge_w / 2, PADDING_TOP + 40 + badge_h)],
                    radius=4,
                    fill=NOW_LINE_COLOR,
                )
                draw.text(
                    (bx, PADDING_TOP + 42),
                    str(date.day),
                    fill=(0, 0, 0),
                    font=self.font_day_num,
                    anchor="mt",
                )
            else:
                draw.text(
                    (x + px_per_day / 2, PADDING_TOP + 42),
                    str(date.day),
                    fill=AXIS_TEXT_COLOR,
                    font=self.font_day_num,
                    anchor="mt",
                )

    def _draw_grid_lines(self, draw, view_start, days, chart_width, total_height):
        px_per_day = chart_width / days
        for i in range(days + 1):
            x = PADDING_LEFT + i * px_per_day
            date = view_start + timedelta(days=i)
            color = (50, 50, 60) if date.weekday() == 6 else GRID_LINE_COLOR
            draw.line(
                [(x, HEADER_HEIGHT + PADDING_TOP), (x, total_height - PADDING_BOTTOM - 15)],
                fill=color,
                width=1,
            )

    def _draw_now_line(self, draw, view_start, days, chart_width, now, total_height):
        px_per_day = chart_width / days
        days_from_start = (now - view_start).total_seconds() / 86400
        if 0 <= days_from_start <= days:
            x = PADDING_LEFT + days_from_start * px_per_day
            draw.line(
                [(x, HEADER_HEIGHT + PADDING_TOP), (x, total_height - PADDING_BOTTOM - 15)],
                fill=NOW_LINE_COLOR,
                width=2,
            )

    def _draw_event_bar(self, img: Image.Image, draw: ImageDraw.Draw, event, view_start, view_end, days, chart_width, y, now):
        px_per_day = chart_width / days

        ev_start_days = max(0, (event.start_date - view_start).total_seconds() / 86400)
        ev_end_days = min(days, (event.end_date - view_start).total_seconds() / 86400)

        if ev_end_days <= ev_start_days:
            return

        x1 = int(PADDING_LEFT + ev_start_days * px_per_day)
        x2 = int(PADDING_LEFT + ev_end_days * px_per_day)

        cut_left = event.start_date < view_start
        cut_right = event.end_date > view_end

        bar_color = _ensure_readable_color(event.color)

        radius = 12
        r_left = 0 if cut_left else radius
        r_right = 0 if cut_right else radius

        # === Vẽ thanh chính ===
        self._draw_rounded_rect(draw, x1, y, x2, y + BAR_HEIGHT, bar_color, r_left, r_right)

        # === Overlay ảnh event bên phải bar ===
        event_img = _load_event_image(event.image_path, BAR_HEIGHT)
        if event_img:
            img_w = event_img.width
            bar_width = x2 - x1

            if img_w > 0 and bar_width > 60:
                # Vị trí ảnh: bên phải bar, nhưng trong bar
                img_x = x2 - img_w
                if cut_right:
                    img_x = x2 - img_w

                # Đảm bảo ảnh nằm trong bar
                img_x = max(x1 + 30, img_x)

                # Tạo bar mask để clip ảnh vào hình bar
                bar_mask = Image.new("L", img.size, 0)
                bar_mask_draw = ImageDraw.Draw(bar_mask)
                self._draw_rounded_rect_on(bar_mask_draw, x1, y, x2, y + BAR_HEIGHT, 255, r_left, r_right)

                # Tạo gradient fade cho ảnh (fade từ trái, rõ bên phải)
                fade_width = min(40, img_w // 2)
                gradient = _create_gradient_mask(img_w, BAR_HEIGHT, fade_width)

                # Tạo layer ảnh tạm
                img_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
                img_layer.paste(event_img, (img_x, y), event_img)

                # Apply gradient mask lên ảnh
                img_alpha = img_layer.split()[3]
                gradient_full = Image.new("L", img.size, 0)
                gradient_full.paste(gradient, (img_x, y))

                # Kết hợp: alpha = min(img_alpha, gradient, bar_mask)
                from PIL import ImageChops
                combined_alpha = ImageChops.multiply(img_alpha, gradient_full)
                combined_alpha = ImageChops.multiply(combined_alpha, bar_mask)

                # Giảm opacity ảnh xuống 60% để text vẫn đọc được
                combined_alpha = combined_alpha.point(lambda p: int(p * 0.6))

                img_layer.putalpha(combined_alpha)
                img.alpha_composite(img_layer)

                # Cần tạo lại draw vì đã modify img
                draw = ImageDraw.Draw(img)

        # === Viền trái accent ===
        if not cut_left:
            draw.rectangle(
                [(x1, y), (x1 + 3, y + BAR_HEIGHT)],
                fill=(255, 255, 255, 200),
            )

        # === Tên event ===
        text_x = max(x1 + 10, PADDING_LEFT + 5)
        bar_width = x2 - x1
        max_text_width = bar_width - 20

        name = event.name
        bbox = draw.textbbox((0, 0), name, font=self.font_event)
        text_w = bbox[2] - bbox[0]
        if text_w > max_text_width and max_text_width > 30:
            while text_w > max_text_width - 15 and len(name) > 5:
                name = name[:-1]
                bbox = draw.textbbox((0, 0), name + "...", font=self.font_event)
                text_w = bbox[2] - bbox[0]
            name += "..."

        # Text shadow cho dễ đọc (đặc biệt quan trọng khi có ảnh nền)
        for dx, dy in [(1, 1), (-1, 0), (1, 0), (0, -1), (0, 1), (2, 2)]:
            draw.text(
                (text_x + dx, y + BAR_HEIGHT // 2 + dy),
                name,
                fill=(0, 0, 0),
                font=self.font_event,
                anchor="lm",
            )
        draw.text(
            (text_x, y + BAR_HEIGHT // 2),
            name,
            fill=TEXT_COLOR,
            font=self.font_event,
            anchor="lm",
        )

        # === Countdown badge ===
        remaining = event.days_remaining
        if remaining > 0 and event.is_active:
            badge_text = f"{remaining}d"
            badge_x = x2 + 6
            badge_y = y + BAR_HEIGHT // 2

            bbox = draw.textbbox((0, 0), badge_text, font=self.font_countdown)
            bw = bbox[2] - bbox[0] + 12
            bh = bbox[3] - bbox[1] + 8
            draw.rounded_rectangle(
                [(badge_x, badge_y - bh // 2), (badge_x + bw, badge_y + bh // 2)],
                radius=8,
                fill=(60, 60, 70),
            )
            draw.text(
                (badge_x + bw // 2, badge_y),
                badge_text,
                fill=TEXT_COLOR,
                font=self.font_countdown,
                anchor="mm",
            )

    def _draw_rounded_rect(self, draw, x1, y1, x2, y2, color, r_left, r_right):
        draw.rectangle([(x1 + r_left, y1), (x2 - r_right, y2)], fill=color)
        if r_left > 0:
            draw.rounded_rectangle([(x1, y1), (x1 + r_left * 2, y2)], radius=r_left, fill=color)
        else:
            draw.rectangle([(x1, y1), (x1 + 5, y2)], fill=color)
        if r_right > 0:
            draw.rounded_rectangle([(x2 - r_right * 2, y1), (x2, y2)], radius=r_right, fill=color)
        else:
            draw.rectangle([(x2 - 5, y1), (x2, y2)], fill=color)

    def _draw_rounded_rect_on(self, draw, x1, y1, x2, y2, fill_val, r_left, r_right):
        draw.rectangle([(x1 + r_left, y1), (x2 - r_right, y2)], fill=fill_val)
        if r_left > 0:
            draw.rounded_rectangle([(x1, y1), (x1 + r_left * 2, y2)], radius=r_left, fill=fill_val)
        else:
            draw.rectangle([(x1, y1), (x1 + 5, y2)], fill=fill_val)
        if r_right > 0:
            draw.rounded_rectangle([(x2 - r_right * 2, y1), (x2, y2)], radius=r_right, fill=fill_val)
        else:
            draw.rectangle([(x2 - 5, y1), (x2, y2)], fill=fill_val)


# Singleton instance
renderer = TimelineRenderer()
