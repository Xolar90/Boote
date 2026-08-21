import asyncio
import logging
import os
import random
import time
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
import aiohttp
from aiohttp import web

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# قراءة المفاتيح من المتغيرات البيئية في Render
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
OPENROUTER_API_KEY = (os.getenv("OPENROUTER_API_KEY") or "").strip()

# مدة الخمول لتفعيل الردود (1 دقيقة = 60 ثانية)
OWNER_INACTIVITY_THRESHOLD = 60
LAST_OWNER_ACTIVITY = 0

# الحد الأقصى للردود لكل مستخدم (10 رسائل)
MAX_REPLIES_PER_USER = 10
USER_CONVERSATIONS = {}

# شخصية الذكاء الاصطناعي: إنسان عراقي واقعي ولطيف يتحدث في محادثة تيليجرام
SYSTEM_PROMPT = (
    "أنت شخص عراقي واقعي ولطيف جداً تجاوب في التليجرام نيابة عن صاحب الحساب"
    " (هو طالع أو مشغول مو يم التلفون هسه).\n"
    "قواعد الحديث:\n"
    "1. تحدث مثل شاب عراقي طبيعي جداً وواقعي بلهجة بغدادية/عراقية عفوية ومحترمة"
    " (استخدم: هلا بيك عيوني، حبيبي، شخبارك، شكو ماكو، تدلل، ههههه، فدوه"
    " لعينك، هسه هو مو يمه التلفون، بس يرجع يراسلك).\n"
    "2. لا تتكلم كأنك روبوت أو بوت أو نظام رسمي أبداً! تكلم كأنك صديقه أو"
    " أخوه اللي ماسك تلفونه ودا يجاوب عنه.\n"
    "3. جاوب على قد السؤال وبشكل ذكي ومختصر وممتع، وكل رسالة جاوبها بأسلوب"
    " مختلف تماماً عن اللي قبلها حسب كلام الشخص."
)

# ردود عراقية واقعية متنوعة للاحتياط الذكي
FALLBACK_VARIATIONS = [
    "هلا بيك عيوني، صاحب الحساب مو يمه التلفون هسه، بس يفرغ يرجعلك خبر إن"
    " شاء الله ❤️",
    "حبيبي تدلل، اول ما يرجع يشوف رسالتك ويجاوبك باسرع وقت 👍",
    "هلا والله، شكو ماكو؟ تره هو شوي مشغول، بس يفتح نت يراسلك عيوني 🥰",
    "وصلت رسالتك يعمري، لا تاكل هم بس يفرغ يجاوبك بنفسه 🌹",
]


async def query_gemini_direct(user_message: str) -> str:
  """الاتصال المباشر بخوادم Google Gemini REST API"""
  if not GEMINI_API_KEY:
    return ""

  models_to_try = [
      "gemini-1.5-flash",
      "gemini-2.0-flash",
      "gemini-1.5-flash-latest",
  ]
  for m in models_to_try:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{
            "parts": [
                {"text": f"التعليمات: {SYSTEM_PROMPT}\n\nرسالة المتصل:"
                 f" {user_message}"}
            ]
        }],
        "generationConfig": {"temperature": 0.85, "maxOutputTokens": 150},
    }
    try:
      async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, timeout=8) as resp:
          if resp.status == 200:
            data = await resp.json()
            parts = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [])
            )
            if parts and "text" in parts[0]:
              text = parts[0]["text"].strip()
              logger.info(f"✅ تم توليد الرد بنجاح عبر Gemini ({m})")
              return text
          else:
            err = await resp.text()
            logger.error(f"خطأ Gemini ({m} - {resp.status}): {err}")
    except Exception as e:
      logger.error(f"استثناء Gemini ({m}): {e}")
  return ""


async def query_openrouter_direct(user_message: str) -> str:
  """الاتصال الاحتياطي بخوادم OpenRouter"""
  if not OPENROUTER_API_KEY:
    return ""

  url = "https://openrouter.ai/api/v1/chat/completions"
  headers = {
      "Authorization": f"Bearer {OPENROUTER_API_KEY}",
      "HTTP-Referer": "https://render.com",
      "X-Title": "Telegram Iraqi AI Bot",
      "Content-Type": "application/json",
  }
  models = [
      "meta-llama/llama-3.3-70b-instruct:free",
      "google/gemini-2.0-flash-exp:free",
  ]
  for m in models:
    payload = {
        "model": m,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": 150,
        "temperature": 0.8,
    }
    try:
      async with aiohttp.ClientSession() as session:
        async with session.post(
            url, headers=headers, json=payload, timeout=8
        ) as resp:
          if resp.status == 200:
            data = await resp.json()
            text = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            if text:
              logger.info(f"✅ تم توليد الرد بنجاح عبر OpenRouter ({m})")
              return text
    except Exception as e:
      logger.error(f"استثناء OpenRouter: {e}")
  return ""


async def generate_ai_reply(user_message: str) -> str:
  """توليد الرد الذكي العراقي الواقعي"""
  # 1. المحاولة أولاً عبر Google Gemini المباشر
  reply = await query_gemini_direct(user_message)
  if reply:
    return reply

  # 2. المحاولة ثانياً عبر OpenRouter إذا كان متاحاً
  reply = await query_openrouter_direct(user_message)
  if reply:
    return reply

  # 3. رد احتياطي عراقي عفوي متنوع
  return random.choice(FALLBACK_VARIATIONS)


bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher()


# معالجة رسائل Telegram Business
@dp.business_message()
async def handle_business_message(message: types.Message):
  global LAST_OWNER_ACTIVITY
  current_time = time.time()
  chat_id = message.chat.id
  text = message.text or message.caption or ""

  try:
    # 1. إذا كنت أنت من يكتب في المحادثة (أنت نشط حالياً):
    if message.chat.type == "private" and message.from_user.id != message.chat.id:
      LAST_OWNER_ACTIVITY = current_time
      if chat_id in USER_CONVERSATIONS:
        del USER_CONVERSATIONS[chat_id]
      logger.info(f"أنت نشط الآن. تم تصفير المحادثة لـ: {chat_id}")
      return

    # 2. التحقق من خمولك لمدة دقيقة (60 ثانية):
    time_since_owner_active = current_time - LAST_OWNER_ACTIVITY
    if time_since_owner_active < OWNER_INACTIVITY_THRESHOLD:
      secs_left = int(OWNER_INACTIVITY_THRESHOLD - time_since_owner_active)
      logger.info(f"أنت نشط حالياً (متبقي {secs_left} ثانية لتفعيل الرد).")
      return

    # 3. التحقق من حد الـ 10 رسائل لكل مستخدم:
    conv = USER_CONVERSATIONS.setdefault(
        chat_id, {"count": 0, "last_msg_time": current_time}
    )

    if (current_time - conv["last_msg_time"]) > 3600:
      conv["count"] = 0

    if conv["count"] >= MAX_REPLIES_PER_USER:
      logger.info(
          f"المستخدم {chat_id} وصل للحد الأقصى (10 رسائل). تم التخطي."
      )
      return

    # 4. توليد الرد العراقي الواقعي بالذكاء الاصطناعي:
    conv["count"] += 1
    conv["last_msg_time"] = current_time

    reply_text = await generate_ai_reply(text)
    await message.reply(reply_text)
    logger.info(
        f"تم إرسال الرد الذكي ({conv['count']}/{MAX_REPLIES_PER_USER}) لـ:"
        f" {chat_id}"
    )

  except Exception as e:
    logger.error(f"خطأ أثناء معالجة الرسالة: {e}")


# أمر /start
@dp.message(CommandStart())
async def handle_start(message: types.Message):
  await message.answer(
      "أهلاً بك! البوت مبرمج بالذكاء الاصطناعي للردود التلقائية الواقعية باللهجة"
      " العراقية."
  )


# خادم ويب لإبقاء Render نشطاً
async def health_check(request):
  return web.Response(
      text="Telegram Business Iraqi AI Bot is running smoothly!", status=200
  )


async def start_web_server():
  app = web.Application()
  app.router.add_get("/", health_check)
  app.router.add_get("/health", health_check)
  runner = web.AppRunner(app)
  await runner.setup()

  port = int(os.getenv("PORT", 8080))
  site = web.TCPSite(runner, "0.0.0.0", port)
  await site.start()
  logger.info(f"سيرفر الويب يعمل على المنفذ: {port}")


async def main():
  if not bot:
    logger.error("يرجى تعيين BOT_TOKEN في إعدادات Render.")
    await start_web_server()
    while True:
      await asyncio.sleep(3600)
    return

  await start_web_server()
  await bot.delete_webhook(drop_pending_updates=True)
  logger.info("بدء الاستماع للرسائل بالذكاء الاصطناعي الواقعي...")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
