import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram Bot
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    
    # AI Tunnel
    AITUNNEL_API_KEY = os.getenv("AITUNNEL_API_KEY", "")
    AITUNNEL_IMAGE_MODEL = os.getenv("AITUNNEL_IMAGE_MODEL", "gemini-3.1-flash-image-preview")

    # ==================== ЮKassa ====================
    YKASSA_SHOP_ID = int(os.getenv("YKASSA_SHOP_ID", 0))
    YKASSA_SECRET_KEY = os.getenv("YKASSA_SECRET_KEY", "")

    # ==================== Пакетная фотосессия (8 фото) ====================
    PACKAGE_MODELS = {
        "flash": {
            "name": "✨ Gemini 3.1 Flash (базовая, быстро)",
            "price_rub": 140,
            "price_tokens": 4,
            "api_model": "gemini-3.1-flash-image-preview",
            "quality": "standard",
            "size": "1024x1024"
        },
        "medium": {
            "name": "🎨 GPT Image 2 Medium (отличное качество)",
            "price_rub": 245,
            "price_tokens": 7,
            "api_model": "gpt-image-2",
            "quality": "medium",
            "size": "1536x1024"
        },
        "high": {
            "name": "💎 GPT Image 2 High (максимальное качество)",
            "price_rub": 525,
            "price_tokens": 15,
            "api_model": "gpt-image-2",
            "quality": "high",
            "size": "1536x1024"
        },
        "pro": {
            "name": "✨ Gemini 3 Pro (реалистичные лица, высокое качество)",
            "price_rub": 144,          # 18₽ × 8 фото, можно изменить
            "price_tokens": 8,         # стоимость в жетонах (за 8 фото)
            "api_model": "gemini-3-pro-image-preview",
            "quality": "standard",
            "size": "1024x1024"
        }
    }

    # Цена пакета жетонов (20 шт)
    PRICE_20_TOKENS = 700

    # Telegram Payments (не используется)
    PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN", "")

    # Папки
    SHARED_DIR = os.getenv("SHARED_DIR", "/app/shared")
    UPLOAD_DIR = os.path.join(SHARED_DIR, "uploads")
    OUTPUT_DIR = os.path.join(SHARED_DIR, "outputs")

    MIN_PHOTOS = 2
    MAX_PHOTOS = 5
    RECOMMENDED_PHOTOS = 4

    # Список администраторов
    ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "955206480,5063386675").split(",") if x.strip()]

    # ==================== СТИЛИ ДЛЯ ПАКЕТНОЙ ФОТОСЕССИИ ====================
    STYLES = {
        "luxury_interior": {
            "name": "🏠 Интерьерная съемка",
            "prompt": "professional real estate photography style, this person in a spacious luxury apartment with panoramic windows, minimalist decor, soft natural light, elegant furniture, high ceiling, 8k, photorealistic, face clearly visible, different angles: full body, medium shot, close-up, sitting on sofa, standing by the window, looking at bookshelf, casual pose, professional real estate photographer",
            "count": 8
        },
        "park_bench": {
            "name": "🌳 На лавочке в парке",
            "prompt": "lifestyle photoshoot of this person sitting on a wooden park bench, surrounded by green trees and autumn leaves, warm sunlight filtering through branches, casual outfit, 8k, photorealistic, face clearly visible, variety of poses: looking ahead, smiling, reading a book, looking away, natural expressions, professional outdoor photography",
            "count": 8
        },
        "embankment": {
            "name": "🏞️ Набережная",
            "prompt": "this person walking along a beautiful riverside embankment with city skyline in background, sunset golden hour, elegant casual clothes, 8k, photorealistic, face clearly visible, different perspectives: walking towards camera, leaning on railing, looking at view, sitting on steps, laughing, professional travel photography",
            "count": 8
        },
        "cafe_terrace": {
            "name": "☕ Кафе / ресторан",
            "prompt": "this person at a cozy café terrace with small round table and coffee cup, background of city street, soft bokeh, relaxed sophisticated atmosphere, 8k, photorealistic, face clearly visible, various poses: sipping coffee, smiling, looking to the side, talking on phone, checking watch, candid style",
            "count": 8
        },
        "studio_minimal": {
            "name": "⭐ Минималистичная студия",
            "prompt": "this person in a bright minimalist photo studio with white walls and soft diffused light, high fashion editorial style, clean background, 8k, photorealistic, face clearly visible, multiple poses: standing portrait, leaning against wall, sitting on a stool, looking over shoulder, hands in pockets, full body and close-ups",
            "count": 8
        },
        "city_square": {
            "name": "🏙️ Городской сквер",
            "prompt": "this person in a modern city square with fountains and greenery, urban casual style, afternoon light, 8k, photorealistic, face clearly visible, variety: walking, sitting on bench edge, checking phone, laughing with friends, looking at architecture, dynamic poses",
            "count": 8
        }
    }

    @classmethod
    def ensure_dirs(cls):
        os.makedirs(cls.UPLOAD_DIR, exist_ok=True)
        os.makedirs(cls.OUTPUT_DIR, exist_ok=True)