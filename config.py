#config
import os
from dotenv import load_dotenv

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = os.getenv("GUILD_ID", "")
WUWA_TIMELINE_URL = "https://wuwatracker.com/vi/timeline"
CACHE_TTL_SECONDS = 600  # 10 phút
SCRAPE_TIMEOUT_MS = 60000

# Renderer
BG_COLOR = (17, 17, 21)          # #111115 - nền chính
HEADER_BG = (25, 25, 32)        # header area
GRID_LINE_COLOR = (40, 40, 50)  # đường kẻ grid
TEXT_COLOR = (255, 255, 255)     # chữ trắng
TEXT_DIM = (160, 160, 170)       # chữ mờ
NOW_LINE_COLOR = (255, 200, 50) # đường "hiện tại" màu vàng
AXIS_TEXT_COLOR = (180, 180, 190)

# Kích thước ảnh
IMAGE_WIDTH = 1200
BAR_HEIGHT = 32
BAR_GAP = 6
HEADER_HEIGHT = 70
PADDING_LEFT = 20
PADDING_RIGHT = 20
PADDING_TOP = 15
PADDING_BOTTOM = 30

# Số ngày hiển thị mỗi trang
DAYS_PER_VIEW = 21
