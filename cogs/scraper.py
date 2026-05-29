
import asyncio
import hashlib
import os
import time
import logging
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import aiohttp
from playwright.async_api import async_playwright

from config import WUWA_TIMELINE_URL, CACHE_TTL_SECONDS, SCRAPE_TIMEOUT_MS

logger = logging.getLogger("wuwa.scraper")

# Thư mục cache ảnh
IMAGE_CACHE_DIR = Path(__file__).parent.parent / "image_cache"
IMAGE_CACHE_DIR.mkdir(exist_ok=True)


@dataclass
class EventData:
    name: str
    color: tuple[int, int, int]  # RGB
    start_date: datetime
    end_date: datetime
    countdown_text: str = ""
    image_url: str = ""
    image_path: str = ""         # đường dẫn local đến ảnh đã tải
    is_start_cut: bool = False   # thanh bị cắt bên trái (bắt đầu trước viewport)
    is_end_cut: bool = False     # thanh bị cắt bên phải (kết thúc sau viewport)

    @property
    def is_banner(self) -> bool:
        return "banner" in self.name.lower()

    @property
    def is_active(self) -> bool:
        now = datetime.now(timezone.utc)
        return self.start_date <= now <= self.end_date

    @property
    def days_remaining(self) -> int:
        now = datetime.now(timezone.utc)
        if now > self.end_date:
            return 0
        return max(0, (self.end_date - now).days)

    @property
    def days_until_start(self) -> int:
        now = datetime.now(timezone.utc)
        if now >= self.start_date:
            return 0
        return (self.start_date - now).days


class TimelineScraper:

    def __init__(self):
        self._cache: list[EventData] = []
        self._cache_time: float = 0
        self._lock = asyncio.Lock()

    def _is_cache_valid(self) -> bool:
        return (time.time() - self._cache_time) < CACHE_TTL_SECONDS and len(self._cache) > 0

    async def get_events(self, force_refresh: bool = False) -> list[EventData]:
        async with self._lock:
            if not force_refresh and self._is_cache_valid():
                logger.info("Trả về dữ liệu từ cache (%d events)", len(self._cache))
                return self._cache

            logger.info("Bắt đầu scrape dữ liệu mới...")
            try:
                events = await self._scrape()
                self._cache = events
                self._cache_time = time.time()
                logger.info("Scrape thành công: %d events", len(events))
                return events
            except Exception as e:
                logger.error("Scrape thất bại: %s", e)
                if self._cache:
                    logger.info("Trả về cache cũ (%d events)", len(self._cache))
                    return self._cache
                raise

    async def _scrape(self) -> list[EventData]:
        import re
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page(viewport={"width": 1920, "height": 1080})
                await page.goto(WUWA_TIMELINE_URL, wait_until="networkidle", timeout=SCRAPE_TIMEOUT_MS)
                await page.wait_for_timeout(3000)

                html = await page.content()

                # Regex patterns (giống debug script)
                pattern = re.compile(
                    r'style="width:\s*([\d.]+)px;\s*left:\s*([\d.]+)px;[^"]*position:\s*absolute[^"]*">'
                    r'<div class="[^"]*"\s*style="background-color:\s*rgb\((\d+),\s*(\d+),\s*(\d+)\);">'
                    r'(?:<div[^>]*></div>)?'
                    r'<div class="[^"]*">([^<]+)</div>'
                )

                img_pattern = re.compile(
                    r'<div class="[^"]*">([^<]+)</div>'
                    r'<img alt="[^"]*"[^>]*src="([^"]+)"'
                )

                # Map event name -> image URL
                img_map = {}
                import html as html_lib
                for m in img_pattern.finditer(html):
                    name, src = m.groups()
                    name = name.strip()
                    src = html_lib.unescape(src)
                    if src and src.startswith('/_next'):
                        src = "https://wuwatracker.com" + src
                    img_map[name] = src

                raw_events = []
                for m in pattern.finditer(html):
                    w, l, r, g, b, name = m.groups()
                    name = name.strip()
                    imgSrc = img_map.get(name, "")

                    raw_events.append({
                        "name": name,
                        "r": int(r),
                        "g": int(g),
                        "b": int(b),
                        "width": float(w),
                        "left": float(l),
                        "countdown": "",
                        "imgSrc": imgSrc,
                        "isStartCut": False,
                        "isEndCut": False
                    })

                events = self._process_raw_events({"events": raw_events})

                # Tải ảnh cho tất cả events
                await self._download_images(events)

                return events
            finally:
                await browser.close()

    async def _download_images(self, events: list[EventData]):
        async with aiohttp.ClientSession() as session:
            tasks = []
            for event in events:
                if event.image_url:
                    tasks.append(self._download_single_image(session, event))
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                downloaded = sum(1 for e in events if e.image_path)
                logger.info("Đã tải %d/%d ảnh event", downloaded, len(tasks))

    async def _download_single_image(self, session: aiohttp.ClientSession, event: EventData):
        try:
            url = event.image_url
            if not url:
                return

            # Tạo tên file từ hash URL
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            ext = ".png"
            if ".webp" in url:
                ext = ".webp"
            elif ".jpg" in url or ".jpeg" in url:
                ext = ".jpg"
            cache_path = IMAGE_CACHE_DIR / f"{url_hash}{ext}"

            # Dùng cache nếu đã có
            if cache_path.exists() and cache_path.stat().st_size > 0:
                event.image_path = str(cache_path)
                return

            # Tải ảnh
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://wuwatracker.com/",
            }
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    cache_path.write_bytes(data)
                    event.image_path = str(cache_path)
                    logger.debug("Tải ảnh OK: %s", event.name[:30])
                else:
                    logger.warning("Tải ảnh thất bại (%d): %s", resp.status, url[:80])
        except Exception as e:
            logger.warning("Lỗi tải ảnh cho %s: %s", event.name[:30], e)

    def _process_raw_events(self, raw_data: dict) -> list[EventData]:
        raw_events = raw_data.get("events", [])
        if not raw_events:
            return []

        px_per_day = 56.0
        now = datetime.now(timezone.utc)
        now_px = 2870.0

        events: list[EventData] = []
        seen = set()

        for raw in raw_events:
            name = raw["name"]
            left = raw["left"]
            width = raw["width"]

            days_from_now_start = (left - now_px) / px_per_day
            days_from_now_end = (left + width - now_px) / px_per_day

            start_date = now + timedelta(days=days_from_now_start)
            end_date = now + timedelta(days=days_from_now_end)

            key = f"{name}_{start_date.strftime('%Y%m%d')}"
            if key in seen:
                continue
            seen.add(key)

            events.append(EventData(
                name=name,
                color=(raw["r"], raw["g"], raw["b"]),
                start_date=start_date,
                end_date=end_date,
                countdown_text=raw.get("countdown", ""),
                image_url=raw.get("imgSrc", ""),
                is_start_cut=raw.get("isStartCut", False),
                is_end_cut=raw.get("isEndCut", False),
            ))

        events.sort(key=lambda e: (not e.is_banner, e.start_date))
        return events


# Singleton instance
scraper = TimelineScraper()
