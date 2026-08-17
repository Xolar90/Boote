import os
import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart

# إعداد التسجيل (Logging) لمتابعة حالة البوت في سجلات Render
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# قراءة توكن البوت من المتغيرات البيئية (Environment Variables)
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    logger.warning("تحذير: لم يتم تعيين BOT_TOKEN في المتغيرات البيئية!")

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher()

# 1. الرد على رسائل تيليجرام للأعمال (المحادثة الآلية نيابة عنك في الخاص)
@dp.business_message()
async def handle_business_message(message: types.Message):
    try:
        # نص الرسالة التلقائية - يمكنك تعديلها حسب رغبتك
        reply_text = "أهلاً بك! أنا غير متواجد حالياً، هذه رسالة رد تلقائي."
        await message.reply(reply_text)
        logger.info(f"تم إرسال رد تلقائي إلى المحادثة: {message.chat.id}")
    except Exception as e:
        logger.error(f"خطأ أثناء إرسال الرد التلقائي: {e}")

# 2. الرد على أمر /start عند فتح البوت مباشرة
@dp.message(CommandStart())
async def handle_start(message: types.Message):
    await message.answer("أهلاً بك! هذا البوت مخصص للردود التلقائية عبر ميزة Telegram Business.")

# 3. سيرفر ويب مصغر لإبقاء الخدمة متوافقة مع استضافة Render المجانية
async def health_check(request):
    return web.Response(text="Telegram Business Bot is running perfectly!", status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"تم تشغيل خادم الويب على المنفذ: {port}")

async def main():
    if not bot:
        logger.error("لا يمكن بدء البوت بدون BOT_TOKEN. يرجى ضبط المتغير في إعدادات Render.")
        # تشغيل سيرفر الويب فقط حتى لا يفشل Render في الـ Deploy
        await start_web_server()
        while True:
            await asyncio.sleep(3600)
        return

    # تشغيل سيرفر الويب والبوت معاً
    await start_web_server()
    logger.info("بدء تشغيل الاستماع للرسائل (Polling)...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
