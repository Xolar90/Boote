import asyncio
import logging
import os
import time
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiohttp import web

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# قراءة التوكن
BOT_TOKEN = os.getenv("BOT_TOKEN")

# مدة خمولك لتفعيل البوت (30 دقيقة = 1800 ثانية)
OWNER_INACTIVITY_THRESHOLD = 30 * 60

# وقت آخر رسالة أرسلتها أنت (يبدأ من 0 ليعمل مباشرة في حال عدم نشاطك)
LAST_OWNER_ACTIVITY = 0

# تتبع المحادثات: {chat_id: {"count": int, "last_msg_time": float}}
USER_CONVERSATIONS = {}

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher()


# معالجة رسائل Telegram Business
@dp.business_message()
async def handle_business_message(message: types.Message):
  global LAST_OWNER_ACTIVITY
  current_time = time.time()
  chat_id = message.chat.id

  try:
    # 1. إذا كانت الرسالة صادرة منك أنت (أنت من يكتب في المحادثة):
    if message.chat.type == "private" and message.from_user.id != message.chat.id:
      LAST_OWNER_ACTIVITY = current_time
      # تصفير المحادثة مع هذا الشخص لأنك قمت بالرد عليه بنفسك
      if chat_id in USER_CONVERSATIONS:
        del USER_CONVERSATIONS[chat_id]
      logger.info(
          f"أنت نشط الآن. تم تحديث وقت النشاط وتصفير المحادثة لـ: {chat_id}"
      )
      return

    # 2. التحقق من خمولك لمدة 30 دقيقة
    time_since_owner_active = current_time - LAST_OWNER_ACTIVITY
    if time_since_owner_active < OWNER_INACTIVITY_THRESHOLD:
      mins_left = int(
          (OWNER_INACTIVITY_THRESHOLD - time_since_owner_active) / 60
      )
      logger.info(
          f"صاحب الحساب نشط (قبل {int(time_since_owner_active)} ثانية). متبقي"
          f" {mins_left} دقيقة لتفعيل الردود."
      )
      return

    # 3. معالجة ردود المستخدم:
    conv = USER_CONVERSATIONS.get(chat_id)

    # أ) الرسالة الأولى (أو بعد غياب أكثر من 30 دقيقة):
    if not conv or (current_time - conv["last_msg_time"]) > 30 * 60:
      USER_CONVERSATIONS[chat_id] = {
          "count": 1,
          "last_msg_time": current_time,
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
        USER_CONVERSATIONS[chat_id] = {
            "count": 2,
            "last_msg_time": current_time,
        }
        reply_text = "انتضرني يا صديقي انا غير موجود 🙂🫶"
        await message.reply(reply_text)
        logger.info(f"تم إرسال الرد 2 للمستخدم: {chat_id}")
      else:
        conv["last_msg_time"] = current_time
      return

    # ج) الرسالة الثالثة (في أقل من 3 دقائق = 180 ثانية):
    elif count == 2:
      if diff <= 180:
        USER_CONVERSATIONS[chat_id] = {
            "count": 3,
            "last_msg_time": current_time,
        }
        reply_text = "يا اخي تحلى بل صبر ماذا دهاك😑"
        await message.reply(reply_text)
        logger.info(f"تم إرسال الرد 3 للمستخدم: {chat_id}")
      else:
        conv["last_msg_time"] = current_time
      return

    # د) أكثر من 3 رسائل:
    else:
      conv["last_msg_time"] = current_time
      logger.info(f"تم تخطي الرد للمستخدم {chat_id} لتجاوز 3 رسائل متتالية.")
      return

  except Exception as e:
    logger.error(f"خطأ أثناء معالجة الرسالة: {e}")


# أمر /start
@dp.message(CommandStart())
async def handle_start(message: types.Message):
  await message.answer("أهلاً بك! البوت مبرمج بالقواعد الذكية للردود التلقائية.")


# سيرفر ويب لـ Render
async def health_check(request):
  return web.Response(text="Bot is running with custom rules!", status=200)


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
    logger.error("يرجى ضبط BOT_TOKEN في Render.")
    await start_web_server()
    while True:
      await asyncio.sleep(3600)
    return

  await start_web_server()
  await bot.delete_webhook(drop_pending_updates=True)
  logger.info("بدء الاستماع للرسائل بالقواعد الجديدة...")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
