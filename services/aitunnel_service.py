import os
import base64
import logging
import aiohttp
import asyncio
from config import Config

logger = logging.getLogger(__name__)

class AITunnelService:
    TIMEOUT_FLASH = 150
    TIMEOUT_MEDIUM = 120
    TIMEOUT_HIGH = 180
    TIMEOUT_PRO = 150

    def __init__(self, model_key: str = "flash"):
        self.api_key = Config.AITUNNEL_API_KEY
        self.base_url = "https://api.aitunnel.ru/v1"
        self.model_key = model_key
        info = Config.PACKAGE_MODELS.get(model_key, Config.PACKAGE_MODELS["flash"])
        self.model_name = info["api_model"]
        self.quality = info.get("quality", "standard")
        self.size = info.get("size", "1024x1024")
        # Таймауты
        if model_key == "flash":
            self.timeout = self.TIMEOUT_FLASH
        elif model_key == "pro":
            self.timeout = self.TIMEOUT_PRO
        elif model_key == "medium":
            self.timeout = self.TIMEOUT_MEDIUM
        elif model_key == "high":
            self.timeout = self.TIMEOUT_HIGH
        else:
            self.timeout = self.TIMEOUT_FLASH
        logger.info(f"AITunnelService инициализирован: model_key={model_key}, model={self.model_name}, size={self.size}")

    async def generate_package_photos(self, user_photo_paths: list, style_key: str, gender: str = None) -> list:
        logger.info(f"=== НАЧАЛО ГЕНЕРАЦИИ === model={self.model_key}, style={style_key}")

        style = Config.STYLES.get(style_key)
        if not style:
            raise ValueError(f"Неизвестный стиль: {style_key}")

        base_prompt = style["prompt"]
        subject = "this man" if gender == 'male' else "this woman" if gender == 'female' else "this person"
        prompt = base_prompt.replace("{token}", subject)
        logger.info(f"Промпт: {prompt[:200]}...")

        # Берём первое существующее фото пользователя
        ref_photo = next((p for p in user_photo_paths if os.path.exists(p)), None)
        if not ref_photo:
            logger.error("Нет доступных фото пользователя")
            return []
        logger.info(f"Референс: {ref_photo}")

        try:
            with open(ref_photo, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("utf-8")
                # Формат data URL, как в PIXEL
                image_data_url = f"data:image/jpeg;base64,{image_b64}"
                logger.info(f"Base64 длина: {len(image_b64)}")
        except Exception as e:
            logger.error(f"Ошибка чтения фото: {e}")
            return []

        images = []
        TOTAL_NEEDED = 2   # временно 2 фото, потом 8

        async with aiohttp.ClientSession() as session:
            # Для Gemini используем чат-эндпоинт (как в PIXEL)
            if self.model_key in ("flash", "pro"):
                logger.info(f"Используем /v1/chat/completions для {self.model_key}, strength=0.8")
                url = f"{self.base_url}/chat/completions"
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                for i in range(TOTAL_NEEDED):
                    payload = {
                        "model": self.model_name,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": image_data_url}
                                    },
                                    {
                                        "type": "text",
                                        "text": prompt
                                    }
                                ]
                            }
                        ],
                        "modalities": ["image", "text"],
                        "max_tokens": 1000,
                        "strength": 0.8   # ключевой параметр для сохранения лица
                    }
                    logger.info(f"Запрос {i+1}/{TOTAL_NEEDED} (chat)")
                    success = False
                    for attempt in range(3):
                        try:
                            async with session.post(url, headers=headers, json=payload, timeout=self.timeout) as resp:
                                resp_text = await resp.text()
                                if resp.status == 200:
                                    data = await resp.json()
                                    # Извлекаем base64 из ответа (как в PIXEL)
                                    if 'choices' in data and data['choices']:
                                        message = data['choices'][0].get('message', {})
                                        content = message.get('content', [])
                                        for part in content:
                                            if part.get('type') == 'image_url':
                                                img_url = part.get('image_url', {}).get('url', '')
                                                if img_url.startswith('data:image/'):
                                                    parts = img_url.split(',', 1)
                                                    if len(parts) == 2:
                                                        images.append(parts[1])
                                                        success = True
                                                        logger.info(f"Фото {i+1} получено (chat)")
                                                        break
                                        if success:
                                            break
                                else:
                                    logger.error(f"Ошибка {resp.status}: {resp_text[:200]}")
                        except Exception as e:
                            logger.error(f"Попытка {attempt+1} не удалась: {e}")
                        await asyncio.sleep(1.5 * (2 ** attempt))
                    if not success:
                        logger.warning(f"Не удалось получить фото {i+1}")
                    await asyncio.sleep(0.5)

            else:
                # Для GPT Image 2: пока оставляем старый метод через /images/generations
                # Но он может не работать, как видели ранее.
                # В будущем можно перевести на /chat/completions или /edits.
                logger.warning(f"Модель {self.model_key} не оптимизирована, используем /images/generations")
                url = f"{self.base_url}/images/generations"
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": self.model_name,
                    "prompt": prompt,
                    "n": TOTAL_NEEDED,
                    "size": self.size,
                    "response_format": "b64_json",
                    "image": image_b64,
                    "strength": 0.8
                }
                for attempt in range(3):
                    try:
                        async with session.post(url, headers=headers, json=payload, timeout=self.timeout) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                for item in data.get('data', []):
                                    b64 = item.get('b64_json') or (item.get('url', '').split(',', 1)[1] if item.get('url', '').startswith('data:image/') else None)
                                    if b64:
                                        images.append(b64)
                                if images:
                                    break
                            else:
                                logger.error(f"Ошибка GPT: {resp.status} {await resp.text()}")
                    except Exception as e:
                        logger.error(f"GPT попытка {attempt+1}: {e}")
                    await asyncio.sleep(1.5 * (2 ** attempt))

        logger.info(f"Сгенерировано {len(images)} фото")
        return images