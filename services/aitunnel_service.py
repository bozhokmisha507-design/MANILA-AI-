import os
import base64
import logging
import aiohttp
import asyncio
import random
from config import Config

logger = logging.getLogger(__name__)

class AITunnelService:
    TIMEOUT = 300  # увеличен до 5 минут
    RETRIES = 3

    def __init__(self, model_key: str = "gemini"):
        info = Config.PACKAGE_MODELS.get(model_key, Config.PACKAGE_MODELS["gemini"])
        self.api_key = Config.AITUNNEL_API_KEY
        self.base_url = "https://api.aitunnel.ru/v1"
        self.model_name = info["api_model"]
        self.size = info.get("size", "1024x1024")
        self.batch_size = info.get("batch_size", 8)
        self.model_type = info.get("type", "chat")  # "chat" или "edits"
        logger.info(f"AITunnelService: model={self.model_name}, type={self.model_type}, batch={self.batch_size}")

    async def generate_package_photos(self, user_photo_paths: list, style_key: str, gender: str = None) -> list:
        style = Config.STYLES.get(style_key)
        if not style:
            raise ValueError(f"Неизвестный стиль: {style_key}")

        # Формируем промпт
        prompt = style.get('prompt', '')
        if gender == 'male':
            prompt = prompt.replace("{token}", "this man")
        elif gender == 'female':
            prompt = prompt.replace("{token}", "this woman")
        else:
            prompt = prompt.replace("{token}", "this person")

        # Общие инструкции
        prompt += " Landscape orientation, horizontal composition, aspect ratio 16:9, wide format."
        prompt += " Face clearly visible, exact facial features as in the reference image."
        prompt += " One single image, no collages, no grids, no multiple frames. Single photograph."
        if self.model_type == "edits":
            prompt += " Change only the background, lighting, and scene. Preserve the subject's face, pose, appearance, and clothing."

        logger.info(f"Промпт: {prompt[:300]}...")

        # Референсное фото
        ref_photo = next((p for p in user_photo_paths if os.path.exists(p)), None)
        if not ref_photo:
            logger.error("Нет доступных фото пользователя")
            return []

        with open(ref_photo, "rb") as f:
            image_bytes = f.read()
        logger.info(f"Референс фото: {len(image_bytes)} байт")

        images = []
        async with aiohttp.ClientSession() as session:
            if self.model_type == "chat":
                # ---------- Gemini 3 Pro через /chat/completions ----------
                data_url = f"data:image/jpeg;base64,{base64.b64encode(image_bytes).decode()}"
                headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
                for i in range(self.batch_size):
                    payload = {
                        "model": self.model_name,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "image_url", "image_url": {"url": data_url}},
                                    {"type": "text", "text": f"Сгенерируй фото на основе этого человека: {prompt}"}
                                ]
                            }
                        ],
                        "modalities": ["image", "text"],
                        "max_tokens": 1000,
                        "seed": random.randint(1, 1000000),
                        "candidate_count": 1
                    }
                    logger.info(f"Gemini запрос {i+1}/{self.batch_size}")
                    success = False
                    for attempt in range(self.RETRIES):
                        try:
                            async with session.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=self.TIMEOUT) as resp:
                                if resp.status == 200:
                                    data = await resp.json()
                                    if 'choices' in data and data['choices']:
                                        msg = data['choices'][0].get('message', {})
                                        if 'images' in msg and msg['images']:
                                            img_url = msg['images'][0].get('image_url', {}).get('url')
                                            if img_url and img_url.startswith('data:image/'):
                                                b64 = img_url.split(',')[1]
                                                images.append(b64)
                                                success = True
                                                logger.info(f"Фото {i+1} получено (images)")
                                                break
                                        if 'content' in msg and isinstance(msg['content'], str) and msg['content'].startswith('data:image'):
                                            b64 = msg['content'].split(',')[1]
                                            images.append(b64)
                                            success = True
                                            logger.info(f"Фото {i+1} получено (content)")
                                            break
                                else:
                                    text = await resp.text()
                                    logger.error(f"Ошибка {resp.status}: {text[:200]}")
                        except Exception as e:
                            logger.error(f"Попытка {attempt+1}: {e}")
                        await asyncio.sleep(1.5 * (2 ** attempt))
                    if not success:
                        logger.warning(f"Фото {i+1} не получено")
                    await asyncio.sleep(0.3)

            else:
                # ---------- GPT Image 2 через /images/edits ----------
                url = f"{self.base_url}/images/edits"
                headers = {"Authorization": f"Bearer {self.api_key}"}
                for i in range(self.batch_size):
                    form_data = aiohttp.FormData()
                    form_data.add_field('model', self.model_name)
                    form_data.add_field('image', image_bytes, filename='photo.jpg', content_type='image/jpeg')
                    form_data.add_field('prompt', prompt)
                    form_data.add_field('n', '1')
                    form_data.add_field('size', self.size)
                    # quality и response_format удалены
                    logger.info(f"GPT запрос {i+1}/{self.batch_size}")
                    success = False
                    for attempt in range(self.RETRIES):
                        try:
                            async with session.post(url, headers=headers, data=form_data, timeout=self.TIMEOUT) as resp:
                                if resp.status == 200:
                                    data = await resp.json()
                                    if 'data' in data and data['data']:
                                        item = data['data'][0]
                                        if 'url' in item:
                                            img_url = item['url']
                                            if img_url.startswith('data:image/'):
                                                b64 = img_url.split(',')[1]
                                                images.append(b64)
                                                success = True
                                                logger.info(f"Фото {i+1} получено (data URL)")
                                                break
                                            else:
                                                async with session.get(img_url) as img_resp:
                                                    if img_resp.status == 200:
                                                        img_bytes = await img_resp.read()
                                                        images.append(base64.b64encode(img_bytes).decode())
                                                        success = True
                                                        logger.info(f"Фото {i+1} получено (скачано)")
                                                        break
                                else:
                                    text = await resp.text()
                                    logger.error(f"Ошибка {resp.status}: {text[:300]}")
                        except asyncio.TimeoutError:
                            logger.error(f"Таймаут при попытке {attempt+1} для фото {i+1}. Увеличьте TIMEOUT в коде, если ошибка повторяется.")
                        except Exception as e:
                            logger.error(f"Попытка {attempt+1} не удалась: {e}", exc_info=True)
                        await asyncio.sleep(1.5 * (2 ** attempt))
                    if not success:
                        logger.warning(f"Фото {i+1} не получено после {self.RETRIES} попыток")
                    await asyncio.sleep(0.3)

        logger.info(f"Сгенерировано {len(images)} фото")
        return images