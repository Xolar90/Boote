import asyncio
import logging
import os
import re
import time
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiohttp import web

# إعداد التسجيل (Logging)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# قراءة التوكن
BOT_TOKEN = os.getenv("BOT_TOKEN")

# مدة خمولك لتفعيل الردود على المحادثات القائمة (30 دقيقة = 1800 ثانية)
OWNER_INACTIVITY_THRESHOLD = 30 * 60

# وقت آخر رسالة أرسلتها أنت
LAST_OWNER_ACTIVITY = 0

# تتبع المستخدمين الجدد
KNOWN_USERS = set()

# تتبع حالات المحادثات: {chat_id: {"count": int, "last_msg_time": float, "ack_sent": bool}}
USER_CONVERSATIONS = {}

# الكلمات المفتاحية للتأكيد والتفهم
ACK_KEYWORDS = ["تمام", "خوش", "ماشي", "اوكي", "اوك", "ok", "okay"]


def is_ack_message(text: str) -> bool:
  """فحص وجود كلمات الموافقة حتى مع وجود إيموجي أو علامات ترقيم"""
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
    # 1. إذا كانت الرسالة صادرة منك أنت (أنت من كتب في المحادثة):
    if message.chat.type == "private" and message.from_user.id != message.chat.id:
      LAST_OWNER_ACTIVITY = current_time
      KNOWN_USERS.add(chat_id)
      if chat_id in USER_CONVERSATIONS:
        del USER_CONVERSATIONS[chat_id]
      logger.info(
          f"أنت نشط الآن. تم تحديث وقت النشاط للمحادثة مع: {chat_id}"
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
        conv["count"] = 3  # لمنع تكرار رسائل العتاب اللاحقة
        KNOWN_USERS.add(chat_id)
        reply_text = "تمام شكرا لانتضارك 🥰🫶"
        await message.reply(reply_text)
        logger.info(f"تم إرسال رد التأكيد (ACK) للمستخدم: {chat_id}")
        return
      else:
        conv["last_msg_time"] = current_time
        logger.info(
            f"تم إرسال رد التأكيد مسبقاً للمستخدم {chat_id}، تم التخطي."
        )
        return

    # 3. شرط المستخدم الجديد (يرد لمرة واحدة حتى وإن كنت نشطاً):
    if is_new_user:
      KNOWN_USERS.add(chat_id)
      USER_CONVERSATIONS[chat_id] = {
          "count": 1,
          "last_msg_time": current_time,
          "ack_sent": False,
      }
      reply_text = "انتضر ردي انا الان غير متواجد حاليا🥰"
      await message.reply(reply_text)
      logger.info(f"مستخدم جديد {chat_id} - تم إرسال الرد الترحيبي الأول.")
      return

    # 4. للمستخدمين الحاليين: التحقق من خمولك لمدة 30 دقيقة
    time_since_owner_active = current_time - LAST_OWNER_ACTIVITY
    if time_since_owner_active < OWNER_INACTIVITY_THRESHOLD:
      mins_left = int(
          (OWNER_INACTIVITY_THRESHOLD - time_since_owner_active) / 60
      )
      logger.info(
          f"أنت نشط حالياً (متبقي {mins_left} دقيقة لتفعيل الردود التلقائية)."
      )
      return

    # 5. منطق الردود المتدرجة عند غيابك لأكثر من 30 دقيقة:
    conv = USER_CONVERSATIONS.get(chat_id)

    # أ) الرسالة الأولى (أو بعد صمت لأكثر من 30 دقيقة):
    if not conv or (current_time - conv["last_msg_time"]) > 30 * 60:
      USER_CONVERSATIONS[chat_id] = {
          "count": 1,
          "last_msg_time": current_time,
          "ack_sent": False,
      }
      reply_text = "انتضر ردي انا الان غير متواجد حاليا🥰"
      await message.reply(reply_text)
      logger.info(f"تم إرسال الرد 1 للمستخدم: {chat_id}")
      return

    diff = current_time - conv["last_msg_time"]
    count = conv["count"]

    # ب) الرسالة الثانية (في أقل من دقيقتين = 120 ثانية):
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

    # ج) الرسالة الثالثة (في أقل من 3 دقائق = 180 ثانية):
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
      logger.info(
          f"المستخدم {chat_id} تجاوز 3 رسائل متتالية، تم تخطي الرد."
      )
      return

  except Exception as e:
    logger.error(f"خطأ أثناء معالجة الرسالة: {e}")


# أمر /start
@dp.message(CommandStart())
async def handle_start(message: types.Message):
  await message.answer("أهلاً بك! البوت مبرمج بالقواعد الذكية للردود التلقائية.")


# خادم ويب لإبقاء Render نشطاً
async def health_check(request):
  return web.Response(
      text="Telegram Business Bot is running with all custom rules!", status=200
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
  logger.info("بدء الاستماع للرسائل بالقواعد الجديدة الكاملة...")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
