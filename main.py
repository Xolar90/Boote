import asyncio
import logging
import os
import time
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiohttp import web
import google.generativeai as genai

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# قراءة التوكنات من المتغيرات البيئية في Render
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
GEMINI_API_KEY = (
    os.getenv("GEMINI_API_KEY")
    or os.getenv("AI_API_KEY")
    or os.getenv("OPENROUTER_API_KEY")
    or ""
).strip()

# إعداد نموذج Google Gemini الرسمي
if GEMINI_API_KEY:
  try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction=(
            "أنت سكرتير ومساعد ذكي جداً ترد على الرسائل الخاصة في حساب تيليجرام"
            " نيابة عن صاحب الحساب. صاحب الحساب غير متواجد حالياً وغائب عن"
            " التيليجرام.\n"
            "قواعد الرد:\n"
            "1. تحدث دائماً بلهجة عراقية محترمة ولطيفة وودودة جداً (مثل: هلا"
            " بيك عيوني، تدلل، ان شاء الله، حبيبي، صاحب الحساب ما متواجد"
            " هسه).\n"
            "2. جاوب مباشرة وبذكاء على كلام الشخص أو سؤاله مهما كان (إذا سأل"
            " وين راح خبره إنه مشغول أو طالع هسه، وإذا سأل سؤال عام جاوبه عليه"
            " باختصار ولطف).\n"
            "3. ذكره بلباقة في نهاية جوابك إنه ينتظر رد صاحب الحساب أول ما"
            " يفرغ يتواصل وياه.\n"
            "4. اجعل الرد متفاعلاً وممتعاً حسب سياق كل رسالة بدون تكرار نفس"
            " العبارة أبداً."
        ),
    )
    logger.info("✅ تم تهيئة نموذج Google Gemini الرسمي بنجاح!")
  except Exception as e:
    logger.error(f"خطأ أثناء تهيئة Gemini: {e}")
    model = None
else:
  model = None
  logger.warning(
      "⚠️ تنبيه: لم يتم العثور على GEMINI_API_KEY في إعدادات Render!"
  )

# مدة خمولك لتفعيل الرد الذكي (1 دقيقة = 60 ثانية)
OWNER_INACTIVITY_THRESHOLD = 60
LAST_OWNER_ACTIVITY = 0

# الحد الأقصى للردود لكل مستخدم (10 رسائل)
MAX_REPLIES_PER_USER = 10
USER_CONVERSATIONS = {}


async def generate_ai_reply(user_message: str) -> str:
  """توليد الرد الذكي العراقي مباشرة عبر Google Gemini"""
  fallback_text = (
      "هلا بيك عيوني، صاحب الحساب ما متواجد حالياً، انتظر رده وأول ما يفرغ"
      " يتواصل وياك إن شاء الله 🥰"
  )

  if not model or not user_message:
    return fallback_text

  try:
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None, model.generate_content, user_message
    )
    if response and response.text:
      logger.info("✅ تم توليد الرد بنجاح عبر Google Gemini.")
      return response.text.strip()
  except Exception as e:
    logger.error(f"خطأ أثناء استدعاء Google Gemini: {e}")

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

    if (current_time - conv["last_msg_time"]) > 3600:
      conv["count"] = 0

    if conv["count"] >= MAX_REPLIES_PER_USER:
      logger.info(
          f"المستخدم {chat_id} وصل للحد الأقصى (10 رسائل). تم التخطي."
      )
      return

    # 4. توليد الرد الذكي المخصص لكل رسالة عبر Google Gemini:
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
      "أهلاً بك! البوت مبرمج بـ Google Gemini الرسمي للردود التلقائية الذكية"
      " باللهجة العراقية."
  )


# خادم ويب لإبقاء Render نشطاً
async def health_check(request):
  return web.Response(
      text="Telegram Business Gemini AI Bot is running!", status=200
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
  logger.info("بدء الاستماع للرسائل بالذكاء الاصطناعي من Google Gemini...")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
