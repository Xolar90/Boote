import asyncio
import logging
import os
import re
import time
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiohttp import web
import google.generativeai as genai

# إعداد التسجيل (Logging)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# قراءة المتغيرات البيئية من Render
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# إعداد نموذج الذكاء الاصطناعي (Google Gemini)
if GEMINI_API_KEY:
  genai.configure(api_key=GEMINI_API_KEY)
  model = genai.GenerativeModel(
      model_name="gemini-1.5-flash",
      system_instruction=(
          "أنت مساعد ذكي ولطيف ترد على الرسائل الخاصة في حساب تيليجرام نيابة"
          " عن صاحب الحساب. "
          "صاحب الحساب غير متواجد حالياً. "
          "مهمتك: الرد على استفسار الشخص باختصار ولطف باللغة العربية، "
          "وتوضيح أنك رد ذكي مؤقت وأن صاحب الحساب سيتواصل معه شخصياً فور"
          " تفرغه."
      ),
  )
  logger.info("تم تهيئة نموذج الذكاء الاصطناعي بنجاح.")
else:
  model = None
  logger.warning("لم يتم تعيين GEMINI_API_KEY. سيعمل البوت بالردود الثابتة.")

# مدة خمولك لتفعيل الردود (30 دقيقة = 1800 ثانية)
OWNER_INACTIVITY_THRESHOLD = 30 * 60
LAST_OWNER_ACTIVITY = 0
KNOWN_USERS = set()
USER_CONVERSATIONS = {}

ACK_KEYWORDS = ["تمام", "خوش", "ماشي", "اوكي", "اوك", "ok", "okay"]


def is_ack_message(text: str) -> bool:
  if not text:
    return False
  cleaned = re.sub(r"[^\w\s]", "", text).strip().lower()
  words = cleaned.split()
  for word in words:
    if word in ACK_KEYWORDS:
      return True
  for kw in ACK_KEYWORDS:
    if kw in cleaned:
      return True
  return False


def generate_ai_reply(user_message: str, fallback_text: str) -> str:
  """توليد رد ذكي عبر الذكاء الاصطناعي مع نص احتياطي عند الحاجة"""
  if not model or not user_message:
    return fallback_text
  try:
    response = model.generate_content(user_message)
    return response.text.strip() if response.text else fallback_text
  except Exception as e:
    logger.error(f"خطأ أثناء توليد رد الذكاء الاصطناعي: {e}")
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
    # 1. إذا كانت الرسالة صادرة منك أنت:
    if message.chat.type == "private" and message.from_user.id != message.chat.id:
      LAST_OWNER_ACTIVITY = current_time
      KNOWN_USERS.add(chat_id)
      if chat_id in USER_CONVERSATIONS:
        del USER_CONVERSATIONS[chat_id]
      logger.info(
          f"أنت نشط الآن. تم تحديث وقت النشاط للمحادثة: {chat_id}"
      )
      return

    is_new_user = chat_id not in KNOWN_USERS

    # 2. شرط كلمات التأكيد (تمام / خوش / ماشي / اوكي مع الإيموجي):
    if is_ack_message(text):
      conv = USER_CONVERSATIONS.setdefault(
          chat_id,
          {"count": 1, "last_msg_time": current_time, "ack_sent": False},
      )
      if not conv.get("ack_sent", False):
        conv["ack_sent"] = True
        conv["last_msg_time"] = current_time
        conv["count"] = 3
        KNOWN_USERS.add(chat_id)
        reply_text = "تمام شكرا لانتضارك 🥰🫶"
        await message.reply(reply_text)
        logger.info(f"تم إرسال رد التأكيد (ACK) للمستخدم: {chat_id}")
        return
      else:
        conv["last_msg_time"] = current_time
        return

    # 3. شرط المستخدم الجديد (رد ذكي لمرة واحدة حتى وإن كنت نشطاً):
    if is_new_user:
      KNOWN_USERS.add(chat_id)
      USER_CONVERSATIONS[chat_id] = {
          "count": 1,
          "last_msg_time": current_time,
          "ack_sent": False,
      }
      fallback = "انتضر ردي انا الان غير متواجد حاليا🥰"
      reply_text = generate_ai_reply(text, fallback)
      await message.reply(reply_text)
      logger.info(
          f"مستخدم جديد {chat_id} - تم إرسال الرد الذكي الترحيبي."
      )
      return

    # 4. للمستخدمين الحاليين: التحقق من خمولك لمدة 30 دقيقة
    time_since_owner_active = current_time - LAST_OWNER_ACTIVITY
    if time_since_owner_active < OWNER_INACTIVITY_THRESHOLD:
      mins_left = int(
          (OWNER_INACTIVITY_THRESHOLD - time_since_owner_active) / 60
      )
      logger.info(
          f"أنت نشط حالياً (متبقي {mins_left} دقيقة لتفعيل الردود)."
      )
      return

    # 5. منطق الردود المتدرجة عند غيابك لأكثر من 30 دقيقة:
    conv = USER_CONVERSATIONS.get(chat_id)

    # أ) الرسالة الأولى (رد ذكي عبر AI):
    if not conv or (current_time - conv["last_msg_time"]) > 30 * 60:
      USER_CONVERSATIONS[chat_id] = {
          "count": 1,
          "last_msg_time": current_time,
          "ack_sent": False,
      }
      fallback = "انتضر ردي انا الان غير متواجد حاليا🥰"
      reply_text = generate_ai_reply(text, fallback)
      await message.reply(reply_text)
      logger.info(f"تم إرسال الرد الذكي 1 للمستخدم: {chat_id}")
      return

    diff = current_time - conv["last_msg_time"]
    count = conv["count"]

    # ب) الرسالة الثانية (في أقل من دقيقتين):
    if count == 1:
      if diff <= 120:
        conv["count"] = 2
        conv["last_msg_time"] = current_time
        reply_text = "انتضرني يا صديقي انا غير موجود 🙂🫶"
        await message.reply(reply_text)
        logger.info(f"تم إرسال الرد 2 للمستخدم: {chat_id}")
      else:
        conv["last_msg_time"] = current_time
      return

    # ج) الرسالة الثالثة (في أقل من 3 دقائق):
    elif count == 2:
      if diff <= 180:
        conv["count"] = 3
        conv["last_msg_time"] = current_time
        reply_text = "يا اخي تحلى بل صبر ماذا دهاك😑"
        await message.reply(reply_text)
        logger.info(f"تم إرسال الرد 3 للمستخدم: {chat_id}")
      else:
        conv["last_msg_time"] = current_time
      return

    # د) أكثر من 3 رسائل:
    else:
      conv["last_msg_time"] = current_time
      return

  except Exception as e:
    logger.error(f"خطأ أثناء معالجة الرسالة: {e}")


# أمر /start
@dp.message(CommandStart())
async def handle_start(message: types.Message):
  await message.answer(
      "أهلاً بك! البوت مبرمج بالذكاء الاصطناعي للردود التلقائية الذكية عبر"
      " Telegram Business."
  )


# خادم ويب لإبقاء Render نشطاً
async def health_check(request):
  return web.Response(
      text="Telegram Business AI Bot is running!", status=200
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
  logger.info("بدء الاستماع للرسائل بالذكاء الاصطناعي...")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
