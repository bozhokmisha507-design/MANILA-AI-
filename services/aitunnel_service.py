import os
import base64
import logging
import aiohttp
import asyncio
from config import Config

logger = logging.getLogger(__name__)

class AITunnelService:
    TIMEOUT = 120

    def __init__(self, model_key: str = "gpt_image_2"):
        info = Config.PACKAGE_MODELS.get(model_key, Config.PACKAGE_MODELS["gpt_image_2"])
        self.api_key = Config.AITUNNEL_API_KEY
        self.base_url = "https://api.aitunnel.ru/v1"
        self.model_name = info["api_model"]
        self.size = info.get("size", "1024x1024")
        self.batch_size = info.get("batch_size", 8)
        logger.info(f"AITunnelService init: model={self.model_name}, batch={self.batch_size}")

    async def generate_package_photos(self, user_photo_paths: list, style_key: str, gender: str = None) -> list:
        logger.info(f"Генерация пакета: style={style_key}, gender={gender}, batch={self.batch_size}")

        style = Config.STYLES.get(style_key)
        if not style:
            raise ValueError(f"Неизвестный стиль: {style_key}")

        # Выбираем промпт для мужчин/женщин
        if gender == 'male':
            prompt = style.get('prompt_male', style.get('prompt', ''))
            if '{token}' in prompt:
                prompt = prompt.replace("{token}", "this man")
        elif gender == 'female':
            prompt = style.get('prompt_female', style.get('prompt', ''))
            if '{token}' in prompt:
                prompt = prompt.replace("{token}", "this woman")
        else:
            prompt = style.get('prompt', '')
            if '{token}' in prompt:
                prompt = prompt.replace("{token}", "this person")

        # Добавляем ориентацию и требование лица
        if "Landscape" not in prompt:
            prompt += " Landscape orientation, horizontal composition, aspect ratio 16:9, wide format."
        if "face clearly visible" not in prompt:
            prompt += " Face clearly visible, exact facial features as in the reference image."

        logger.info(f"Промпт (первые 200 символов): {prompt[:200]}...")

        # Референсное фото
        ref_photo = next((p for p in user_photo_paths if os.path.exists(p)), None)
        if not ref_photo:
            logger.error("Нет доступных фото пользователя")
            return []

        with open(ref_photo, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
            data_url = f"data:image/jpeg;base64,{image_b64}"

        url = f"{self.base_url}/images/generations"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        images = []
        async with aiohttp.ClientSession() as session:
            for i in range(self.batch_size):
                payload = {
                    "model": self.model_name,
                    "prompt": prompt,
                    "image": data_url,          # data URL (префикс)
                    "n": 1,
                    "size": self.size
                    # response_format не передаём
                }
                logger.info(f"Запрос {i+1}/{self.batch_size} (generations)")
                success = False
                for attempt in range(3):
                    try:
                        async with session.post(url, headers=headers, json=payload, timeout=self.TIMEOUT) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                if 'data' in data and len(data['data']):
                                    item = data['data'][0]
                                    # Получаем URL изображения
                                    img_url = item.get('url')
                                    if img_url:
                                        # Если это data URL, извлекаем base64
                                        if img_url.startswith('data:image/'):
                                            b64 = img_url.split(',')[1]
                                            images.append(b64)
                                            success = True
                                            logger.info(f"Фото {i+1} получено (data URL)")
                                            break
                                        else:
                                            # Обычный URL – скачиваем
                                            async with session.get(img_url) as img_resp:
                                                if img_resp.status == 200:
                                                    img_bytes = await img_resp.read()
                                                    b64 = base64.b64encode(img_bytes).decode()
                                                    images.append(b64)
                                                    success = True
                                                    logger.info(f"Фото {i+1} получено (скачано)")
                                                    break
                            else:
                                text = await resp.text()
                                logger.error(f"Ошибка {resp.status}: {text[:300]}")
                    except Exception as e:
                        logger.error(f"Попытка {attempt+1}: {e}")
                    await asyncio.sleep(1.5 * (2 ** attempt))
                if not success:
                    logger.warning(f"Фото {i+1} не получено")
                await asyncio.sleep(0.3)

        logger.info(f"Сгенерировано {len(images)} фото")
        return images