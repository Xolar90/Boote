import asyncio
import logging
import os
import time
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
import aiohttp
from aiohttp import web

# إعداد التسجيل (Logging)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# قراءة التوكنات من المتغيرات البيئية في Render
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
AI_API_KEY = (
    os.getenv("AI_API_KEY") or os.getenv("GEMINI_API_KEY") or ""
).strip()

if not AI_API_KEY:
  logger.warning("⚠️ تنبيه: لم يتم ضبط AI_API_KEY في إعدادات Render!")
else:
  logger.info("✅ تم تحميل مفتاح الذكاء الاصطناعي بنجاح.")

# إعدادات مزود الذكاء الاصطناعي (Bluesminds)
AI_BASE_URL = "https://api.bluesminds.com/v1/chat/completions"
AI_MODELS = ["gpt-4o-mini", "gpt-3.5-turbo", "gemini-1.5-flash", "deepseek-chat"]

# مدة خمولك لتفعيل الردود الذكية (1 دقيقة = 60 ثانية)
OWNER_INACTIVITY_THRESHOLD = 60
LAST_OWNER_ACTIVITY = 0

# الحد الأقصى للردود لكل مستخدم (10 رسائل)
MAX_REPLIES_PER_USER = 10

# تتبع رسائل المستخدمين: {chat_id: {"count": int, "last_msg_time": float}}
USER_CONVERSATIONS = {}

# تعليمات شخصية الذكاء الاصطناعي باللهجة العراقية المحترمة
SYSTEM_PROMPT = (
    "أنت سكرتير ومساعد ذكي مؤدب ترد على الرسائل الخاصة في حساب تيليجرام نيابة"
    " عن صاحب الحساب. صاحب الحساب ما متواجد حالياً وغائب عن التيليجرام."
    " قواعد الرد:\n"
    "1. تحدث بلهجة عراقية محترمة ولطيفة ومهذبة جداً (مثل: هلا بيك، عيوني، تدلل،"
    " ان شاء الله، حبيبي/أخي العزيز).\n"
    "2. جاوب على كلام الشخص أو سؤاله بذكاء واختصار، وخبره بلباقة إنك رد آلي مؤقت"
    " وصاحب الحساب ما متواجد هسه وأول ما يفرغ راح يجاوبه بنفسه.\n"
    "3. خلك متجاوب وودود لكن مختصر وبدون إطالة."
)


async def generate_ai_reply(user_message: str) -> str:
  """توليد الرد الذكي باللهجة العراقية عبر مزود Bluesminds"""
  fallback_text = (
      "هلا بيك عيوني، صاحب الحساب ما متواجد حالياً، انتظر رده وأول ما يفرغ"
      " يتواصل وياك إن شاء الله 🥰"
  )

  if not AI_API_KEY or not user_message:
    return fallback_text

  headers = {
      "Authorization": f"Bearer {AI_API_KEY}",
      "Content-Type": "application/json",
  }

  for model_name in AI_MODELS:
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": 160,
    }

    try:
      async with aiohttp.ClientSession() as session:
        async with session.post(
            AI_BASE_URL, headers=headers, json=payload, timeout=12
        ) as resp:
          if resp.status == 200:
            data = await resp.json()
            ai_text = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            if ai_text:
              logger.info(f"✅ تم الرد بالذكاء الاصطناعي ({model_name})")
              return ai_text
          else:
            err_text = await resp.text()
            logger.error(f"خطأ {model_name} ({resp.status}): {err_text}")
    except Exception as e:
      logger.error(f"استثناء أثناء طلب الذكاء الاصطناعي: {e}")

  return fallback_text


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
    # 1. إذا كانت الرسالة صادرة منك أنت (أنت نشط حالياً):
    if message.chat.type == "private" and message.from_user.id != message.chat.id:
      LAST_OWNER_ACTIVITY = current_time
      # تصفير عداد الردود لهذا المستخدم لأنك تحدثت معه
      if chat_id in USER_CONVERSATIONS:
        del USER_CONVERSATIONS[chat_id]
      logger.info(
          f"أنت نشط الآن. تم تحديث وقت النشاط وتصفير عداد المحادثة لـ: {chat_id}"
      )
      return

    # 2. التحقق من خمولك لمدة 1 دقيقة (60 ثانية):
    time_since_owner_active = current_time - LAST_OWNER_ACTIVITY
    if time_since_owner_active < OWNER_INACTIVITY_THRESHOLD:
      secs_left = int(OWNER_INACTIVITY_THRESHOLD - time_since_owner_active)
      logger.info(
          f"أنت نشط حالياً (متبقي {secs_left} ثانية لتفعيل الرد الذكي)."
      )
      return

    # 3. التحقق من حد الـ 10 رسائل لكل مستخدم:
    conv = USER_CONVERSATIONS.setdefault(
        chat_id, {"count": 0, "last_msg_time": current_time}
    )

    # إذا مرت أكثر من ساعة كاملة على آخر محادثة، نصفّر العداد
    if (current_time - conv["last_msg_time"]) > 3600:
      conv["count"] = 0

    # إذا تجاوز المستخدم 10 رسائل يتوقف البوت عن الرد
    if conv["count"] >= MAX_REPLIES_PER_USER:
      logger.info(
          f"المستخدم {chat_id} وصل للحد الأقصى (10 رسائل). تم التخطي."
      )
      return

    # 4. توليد الرد الذكي بالذكاء الاصطناعي باللهجة العراقية:
    conv["count"] += 1
    conv["last_msg_time"] = current_time

    reply_text = await generate_ai_reply(text)
    await message.reply(reply_text)
    logger.info(
        f"تم إرسال الرد الذكي رقم ({conv['count']}/{MAX_REPLIES_PER_USER})"
        f" للمستخدم: {chat_id}"
    )

  except Exception as e:
    logger.error(f"خطأ أثناء معالجة الرسالة: {e}")


# أمر /start
@dp.message(CommandStart())
async def handle_start(message: types.Message):
  await message.answer(
      "أهلاً بك! البوت مبرمج بالذكاء الاصطناعي للردود التلقائية الذكية باللهجة"
      " العراقية."
  )


# خادم ويب لإبقاء Render نشطاً
async def health_check(request):
  return web.Response(
      text="Telegram Business Iraqi AI Bot is running!", status=200
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
  logger.info("بدء الاستماع للرسائل بالذكاء الاصطناعي العراقي...")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
