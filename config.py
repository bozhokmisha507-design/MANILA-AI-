import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram Bot
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    
    # AI Tunnel
    AITUNNEL_API_KEY = os.getenv("AITUNNEL_API_KEY", "")
    AITUNNEL_IMAGE_MODEL = os.getenv("AITUNNEL_IMAGE_MODEL", "gpt-image-2")

    # ==================== ЮKassa ====================
    YKASSA_SHOP_ID = int(os.getenv("YKASSA_SHOP_ID", 0))
    YKASSA_SECRET_KEY = os.getenv("YKASSA_SECRET_KEY", "")

    # ==================== Пакетная фотосессия ====================
    PACKAGE_MODELS = {
        "gpt_image_2": {
            "name": "🎨 GPT Image 2 (Премиум, качественное сохранение лица)",
            "price_rub": 150,
            "price_tokens": 6,
            "api_model": "gpt-image-2",
            "size": "1024x1024",
            "batch_size": 1   # для теста 1 фото, потом поменять на 8
        }
        # другие модели временно отключены
    }

    PRICE_20_TOKENS = 700
    PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN", "")
    SHARED_DIR = os.getenv("SHARED_DIR", "/app/shared")
    UPLOAD_DIR = os.path.join(SHARED_DIR, "uploads")
    OUTPUT_DIR = os.path.join(SHARED_DIR, "outputs")
    MIN_PHOTOS = 2
    MAX_PHOTOS = 5
    RECOMMENDED_PHOTOS = 4
    ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "955206480,5063386675").split(",") if x.strip()]

    # ==================== СТИЛИ С ГЕНДЕРНЫМИ ПРОМПТАМИ ====================
    STYLES = {
        "luxury_interior": {
            "name": "🏠 Интерьерная съемка",
            "prompt_male": "professional real estate photography style, this man in a spacious luxury apartment with panoramic windows, minimalist decor, soft natural light, elegant furniture, high ceiling, wearing a stylish casual outfit (dark jeans and a light sweater), 8k, photorealistic, face clearly visible, different angles: full body, medium shot, close-up, sitting on sofa, standing by the window, looking at bookshelf, confident masculine pose",
            "prompt_female": "professional real estate photography style, this woman in a spacious luxury apartment with panoramic windows, minimalist decor, soft natural light, elegant furniture, high ceiling, wearing a chic casual dress or blouse, 8k, photorealistic, face clearly visible, different angles: full body, medium shot, close-up, sitting on sofa, standing by the window, looking at bookshelf, graceful feminine pose",
            "count": 8
        },
        "park_bench": {
            "name": "🌳 На лавочке в парке",
            "prompt_male": "lifestyle photoshoot of this man sitting on a wooden park bench, surrounded by green trees and autumn leaves, warm sunlight filtering through branches, casual outfit (hoodie and jeans), 8k, photorealistic, face clearly visible, variety of poses: looking ahead, smiling, reading a book, looking away, natural masculine expressions",
            "prompt_female": "lifestyle photoshoot of this woman sitting on a wooden park bench, surrounded by green trees and autumn leaves, warm sunlight filtering through branches, casual outfit (sweater and skirt or jeans), 8k, photorealistic, face clearly visible, variety of poses: looking ahead, smiling, reading a book, looking away, natural feminine expressions",
            "count": 8
        },
        "embankment": {
            "name": "🏞️ Набережная",
            "prompt_male": "this man walking along a beautiful riverside embankment with city skyline in background, sunset golden hour, elegant casual clothes (jacket and trousers), 8k, photorealistic, face clearly visible, different perspectives: walking towards camera, leaning on railing, looking at view, sitting on steps, laughing, confident masculine gestures",
            "prompt_female": "this woman walking along a beautiful riverside embankment with city skyline in background, sunset golden hour, elegant casual clothes (light dress or blouse and skirt), 8k, photorealistic, face clearly visible, different perspectives: walking towards camera, leaning on railing, looking at view, sitting on steps, laughing, graceful feminine gestures",
            "count": 8
        },
        "cafe_terrace": {
            "name": "☕ Кафе / ресторан",
            "prompt_male": "this man at a cozy café terrace with small round table and coffee cup, background of city street, soft bokeh, relaxed sophisticated atmosphere, wearing a smart casual shirt, 8k, photorealistic, face clearly visible, various poses: sipping coffee, smiling, looking to the side, talking on phone, checking watch, masculine candid style",
            "prompt_female": "this woman at a cozy café terrace with small round table and coffee cup, background of city street, soft bokeh, relaxed sophisticated atmosphere, wearing a stylish blouse or summer dress, 8k, photorealistic, face clearly visible, various poses: sipping coffee, smiling, looking to the side, talking on phone, checking watch, feminine candid style",
            "count": 8
        },
        "studio_minimal": {
            "name": "⭐ Минималистичная студия",
            "prompt_male": "this man in a bright minimalist photo studio with white walls and soft diffused light, high fashion editorial style, clean background, wearing a simple t-shirt and jeans or a suit, 8k, photorealistic, face clearly visible, multiple poses: standing portrait, leaning against wall, sitting on a stool, looking over shoulder, hands in pockets, full body and close-ups, masculine strong poses",
            "prompt_female": "this woman in a bright minimalist photo studio with white walls and soft diffused light, high fashion editorial style, clean background, wearing a simple elegant dress or top, 8k, photorealistic, face clearly visible, multiple poses: standing portrait, leaning against wall, sitting on a stool, looking over shoulder, hands in pockets, full body and close-ups, feminine elegant poses",
            "count": 8
        },
        "city_square": {
            "name": "🏙️ Городской сквер",
            "prompt_male": "this man in a modern city square with fountains and greenery, urban casual style, afternoon light, wearing jeans and a casual jacket, 8k, photorealistic, face clearly visible, variety: walking, sitting on bench edge, checking phone, laughing with friends, looking at architecture, dynamic masculine poses",
            "prompt_female": "this woman in a modern city square with fountains and greenery, urban casual style, afternoon light, wearing a casual dress or chic pantsuit, 8k, photorealistic, face clearly visible, variety: walking, sitting on bench edge, checking phone, laughing with friends, looking at architecture, dynamic feminine poses",
            "count": 8
        }
    }

    @classmethod
    def ensure_dirs(cls):
        os.makedirs(cls.UPLOAD_DIR, exist_ok=True)
        os.makedirs(cls.OUTPUT_DIR, exist_ok=True)