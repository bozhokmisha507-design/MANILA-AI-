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
    TIMEOUT_PRO = 150   # аналогично flash

    def __init__(self, model_key: str = "flash"):
        self.api_key = Config.AITUNNEL_API_KEY
        self.base_url = "https://api.aitunnel.ru/v1"
        self.model_key = model_key
        info = Config.PACKAGE_MODELS.get(model_key, Config.PACKAGE_MODELS["flash"])
        self.model_name = info["api_model"]
        self.quality = info.get("quality", "standard")
        self.size = info.get("size", "1024x1024")
        # таймауты для разных моделей
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
        logger.info(f"AITunnelService инициализирован: model_key={model_key}, model={self.model_name}, size={self.size}, quality={self.quality}")

    async def generate_package_photos(self, user_photo_paths: list, style_key: str, gender: str = None) -> list:
        logger.info(f"=== НАЧАЛО ГЕНЕРАЦИИ ПАКЕТА === model={self.model_key}, style={style_key}, gender={gender}, photo_paths={user_photo_paths}")

        style = Config.STYLES.get(style_key)
        if not style:
            logger.error(f"Стиль не найден: {style_key}")
            raise ValueError(f"Неизвестный стиль: {style_key}")

        base_prompt = style["prompt"]
        if gender == 'male':
            subject = "this man"
        elif gender == 'female':
            subject = "this woman"
        else:
            subject = "this person"
        prompt = base_prompt.replace("{token}", subject)
        logger.info(f"Сформирован промпт: {prompt[:200]}...")

        ref_photo = next((p for p in user_photo_paths if os.path.exists(p)), None)
        if not ref_photo:
            logger.error("Нет доступных фото пользователя. Проверенные пути: %s", user_photo_paths)
            return []
        logger.info(f"Используем референсное фото: {ref_photo}")

        try:
            with open(ref_photo, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("utf-8")
                logger.info(f"Base64 длина: {len(image_b64)} символов")
        except Exception as e:
            logger.error(f"Ошибка кодирования фото: {e}", exc_info=True)
            return []

        url = f"{self.base_url}/images/generations"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        timeout = aiohttp.ClientTimeout(total=self.timeout)
        images = []
        TOTAL_NEEDED = 2   # ВРЕМЕННО: 2 фото для теста. После отладки заменить на 8

        async with aiohttp.ClientSession() as session:
            # Модели, которые НЕ поддерживают n>1 (делаем отдельные запросы)
            if self.model_key in ("flash", "pro"):
                logger.info(f"Режим SINGLE: делаем {TOTAL_NEEDED} отдельных запросов с n=1")
                for i in range(TOTAL_NEEDED):
                    payload = {
                        "model": self.model_name,
                        "prompt": prompt,
                        "n": 1,
                        "size": self.size,
                        "response_format": "b64_json",
                        "image": image_b64   # чистый base64 (без префикса)
                    }
                    # quality добавляем только для GPT, для flash/pro не нужно
                    # if self.model_key in ("medium", "high"):
                    #     payload["quality"] = self.quality

                    logger.info(f"Запрос {i+1}/{TOTAL_NEEDED}: payload (image обрезан) = { {k: v if k != 'image' else v[:50]+'...' for k,v in payload.items()} }")
                    success = False
                    for attempt in range(3):
                        try:
                            logger.info(f"Попытка {attempt+1} для фото {i+1}")
                            async with session.post(url, headers=headers, json=payload, timeout=timeout) as resp:
                                resp_text = await resp.text()
                                logger.info(f"Статус ответа: {resp.status}")
                                logger.info(f"Тело ответа (первые 500 символов): {resp_text[:500]}")
                                if resp.status == 200:
                                    data = await resp.json()
                                    if 'data' in data and isinstance(data['data'], list):
                                        for item in data['data']:
                                            b64 = item.get('b64_json')
                                            if b64 and isinstance(b64, str) and len(b64) > 100:
                                                images.append(b64)
                                                success = True
                                                logger.info(f"Фото {i+1} получено через b64_json")
                                                break
                                            url_data = item.get('url')
                                            if url_data and url_data.startswith('data:image/'):
                                                parts = url_data.split(',', 1)
                                                if len(parts) == 2:
                                                    b64 = parts[1]
                                                    images.append(b64)
                                                    success = True
                                                    logger.info(f"Фото {i+1} получено из url (data URL)")
                                                    break
                                            logger.warning(f"Не удалось извлечь изображение из item: {item.keys() if item else None}")
                                        if success:
                                            break
                                    else:
                                        logger.warning(f"Нет 'data' или data не список: {data}")
                                else:
                                    logger.error(f"Ошибка HTTP {resp.status}: {resp_text}")
                        except asyncio.TimeoutError:
                            logger.error(f"Таймаут при запросе (фото {i+1}, попытка {attempt+1})")
                        except aiohttp.ClientError as e:
                            logger.error(f"Клиентская ошибка: {e}", exc_info=True)
                        except Exception as e:
                            logger.error(f"Неожиданное исключение: {e}", exc_info=True)
                        await asyncio.sleep(1.5 * (2 ** attempt))
                    if not success:
                        logger.warning(f"Не удалось получить фото {i+1} после 3 попыток")
                    await asyncio.sleep(0.5)

            else:   # medium / high (GPT Image 2) – поддерживают n>1
                logger.info("Режим GPT: делаем один запрос с n=TOTAL_NEEDED")
                payload = {
                    "model": self.model_name,
                    "prompt": prompt,
                    "n": TOTAL_NEEDED,
                    "size": self.size,
                    "response_format": "b64_json",
                    "image": image_b64
                }
                if self.model_key in ("medium", "high") and self.quality:
                    payload["quality"] = self.quality
                    logger.info(f"Добавлен параметр quality={self.quality}")

                logger.info(f"GPT payload (без image): { {k:v for k,v in payload.items() if k != 'image'} }")
                for attempt in range(3):
                    try:
                        logger.info(f"Попытка {attempt+1} для GPT")
                        async with session.post(url, headers=headers, json=payload, timeout=timeout) as resp:
                            resp_text = await resp.text()
                            logger.info(f"Статус ответа: {resp.status}")
                            logger.info(f"Тело ответа (первые 500 символов): {resp_text[:500]}")
                            if resp.status == 200:
                                data = await resp.json()
                                if 'data' in data and isinstance(data['data'], list):
                                    for idx, item in enumerate(data['data']):
                                        b64 = item.get('b64_json')
                                        if b64 and isinstance(b64, str) and len(b64) > 100:
                                            images.append(b64)
                                            logger.info(f"GPT: фото {idx+1} добавлено через b64_json")
                                            continue
                                        url_data = item.get('url')
                                        if url_data and url_data.startswith('data:image/'):
                                            parts = url_data.split(',', 1)
                                            if len(parts) == 2:
                                                b64 = parts[1]
                                                images.append(b64)
                                                logger.info(f"GPT: фото {idx+1} добавлено из url (data URL)")
                                                continue
                                        logger.warning(f"GPT: не удалось извлечь фото {idx+1} из item")
                                    if images:
                                        logger.info(f"GPT: итого получено {len(images)} фото")
                                        return images
                                else:
                                    logger.warning(f"Нет 'data' в ответе: {data}")
                            else:
                                logger.error(f"Ошибка HTTP {resp.status}: {resp_text}")
                    except asyncio.TimeoutError:
                        logger.error(f"Таймаут GPT (попытка {attempt+1})")
                    except Exception as e:
                        logger.error(f"Исключение при GPT запросе: {e}", exc_info=True)
                    await asyncio.sleep(1.5 * (2 ** attempt))

        logger.info(f"=== ИТОГО СГЕНЕРИРОВАНО {len(images)} ФОТО ===")
        return images