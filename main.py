import asyncio
import logging
import os
import time
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiohttp import web

# إعداد التسجيل لمتابعة العمليات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# قراءة التوكن من المتغيرات البيئية
BOT_TOKEN = os.getenv("BOT_TOKEN")

# مدة الانتظار بين الردود لنفس الشخص (بالثواني) - 1800 ثانية = 30 دقيقة
COOLDOWN_SECONDS = 1800
# لتسجيل وقت آخر رد لكل محادثة
LAST_REPLIED = {}

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher()


# معالجة رسائل Telegram Business
@dp.business_message()
async def handle_business_message(message: types.Message):
  try:
    # 1. منع البوت من الرد على رسائلك أنت (الرسائل الصادرة من حسابك)
    if message.chat.type == "private" and message.from_user.id != message.chat.id:
      logger.info("تجاهل رسالة صادرة من صاحب الحساب.")
      return

    chat_id = message.chat.id
    current_time = time.time()

    # 2. منع تكرار الرد (الرد مرة واحدة كل 30 دقيقة للشخص الواحد)
    if chat_id in LAST_REPLIED:
      time_passed = current_time - LAST_REPLIED[chat_id]
      if time_passed < COOLDOWN_SECONDS:
        logger.info(
            f"تم تخطي الرد للمستخدم {chat_id} لوجود رد حديث قبل"
            f" {int(time_passed)} ثانية."
        )
        return

    # تسجيل وقت الرد الجديد
    LAST_REPLIED[chat_id] = current_time

    # 3. إرسال الرد التلقائي
    reply_text = "أهلاً بك! أنا غير متواجد حالياً، هذه رسالة رد تلقائي."
    await message.reply(reply_text)
    logger.info(f"تم إرسال رد تلقائي بنجاح إلى: {chat_id}")

  except Exception as e:
    logger.error(f"خطأ أثناء معالجة الرسالة: {e}")


# أمر /start
@dp.message(CommandStart())
async def handle_start(message: types.Message):
  await message.answer(
      "أهلاً بك! هذا البوت مخصص للردود التلقائية الذكية عبر Telegram Business."
  )


# خادم ويب لإبقاء Render نشطاً
async def health_check(request):
  return web.Response(
      text="Telegram Business Bot is running smoothly!", status=200
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
  # حذف أي Webhook قديم لتفادي التعارض
  await bot.delete_webhook(drop_pending_updates=True)
  logger.info("بدء الاستماع للرسائل...")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
