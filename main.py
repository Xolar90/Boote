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

# قراءة المفاتيح من المتغيرات البيئية في Render
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
OPENROUTER_API_KEY = (
    os.getenv("OPENROUTER_API_KEY") or os.getenv("AI_API_KEY") or ""
).strip()
GROQ_API_KEY = (os.getenv("GROQ_API_KEY") or "").strip()

# مدة الخمول لتفعيل الردود الذكية (1 دقيقة = 60 ثانية)
OWNER_INACTIVITY_THRESHOLD = 60
LAST_OWNER_ACTIVITY = 0

# الحد الأقصى للردود لكل مستخدم (10 رسائل)
MAX_REPLIES_PER_USER = 10

# ذاكرة المحادثات للاحتفاظ بالسياق: {chat_id: {"count": int, "last_msg_time": float, "history": list}}
USER_CONVERSATIONS = {}

# شخصية الذكاء الاصطناعي الواقعية العفوية
SYSTEM_PROMPT = (
    "أنت شخص عراقي واقعي ولطيف جداً تجاوب في محادثة تليجرام خاصة نيابة عن صاحب"
    " الحساب (صاحب الحساب مو يمه التلفون هسه طالع أو مشغول).\n"
    "قواعد الحديث:\n"
    "1. تحدث مثل إنسان عراقي حقيقي وبشري 100% بلهجة عراقية/بغدادية عفوية وطبيعية"
    " ومحترمة (استخدم: هلا عيوني، حبيبي، شخبارك، شكو ماكو، دومك يارب، تدلل،"
    " ههههه، فدوه لعينك، لا تاكل هم، هسه هو مو يمه التلفون بس يرجع يحاجيك).\n"
    "2. افهم سياق الكلام السابق وجاوب بدقة على كل سؤال (إذا سأل شوكت يرجع قله"
    " عنده شغلة طالع ساعة زمان ويرجع، إذا سلم رد السلام، إذا شكرك رد بتدلل"
    " وتكرم).\n"
    "3. ممنوع التحدث كبوت أو نظام آلي أو تكرار نفس الجملة! كل رسالة لها رد"
    " فريد وذكي ومختصر ومناسب لسياقها."
)


async def query_gemini(messages_history: list) -> str:
  """الاتصال المباشر بمحرك Google Gemini REST API مع تمرير سياق المحادثة"""
  if not GEMINI_API_KEY:
    return ""

  gemini_contents = []
  for msg in messages_history:
    role = "user" if msg["role"] == "user" else "model"
    gemini_contents.append({"role": role, "parts": [{"text": msg["content"]}]})

  models = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-flash-latest"]
  for m in models:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": gemini_contents,
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "generationConfig": {"temperature": 0.85, "maxOutputTokens": 180},
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
              logger.info(f"تم توليد الرد بنجاح عبر Gemini: {m}")
              return text
    except Exception as e:
      logger.error(f"استثناء Gemini: {e}")
  return ""


async def query_openrouter(messages_history: list) -> str:
  """الاتصال الاحتياطي بمحرك OpenRouter مع سياق المحادثة"""
  if not OPENROUTER_API_KEY:
    return ""

  url = "https://openrouter.ai/api/v1/chat/completions"
  headers = {
      "Authorization": f"Bearer {OPENROUTER_API_KEY}",
      "HTTP-Referer": "https://render.com",
      "X-Title": "Telegram Iraqi AI Bot",
      "Content-Type": "application/json",
  }
  msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + messages_history
  models = [
      "meta-llama/llama-3.3-70b-instruct:free",
      "google/gemini-2.0-flash-exp:free",
  ]
  for m in models:
    payload = {
        "model": m,
        "messages": msgs,
        "max_tokens": 180,
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
              logger.info(f"تم توليد الرد عبر OpenRouter: {m}")
              return text
    except Exception as e:
      logger.error(f"استثناء OpenRouter: {e}")
  return ""


async def query_pollinations_direct(messages_history: list) -> str:
  """محرك ذكاء اصطناعي فوري مباشر مجاني لضمان عدم توقف الذكاء أبداً"""
  url = "https://text.pollinations.ai/openai"
  msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + messages_history
  payload = {"messages": msgs, "model": "openai", "temperature": 0.8}
  try:
    async with aiohttp.ClientSession() as session:
      async with session.post(url, json=payload, timeout=8) as resp:
        if resp.status == 200:
          data = await resp.json()
          text = (
              data.get("choices", [{}])[0]
              .get("message", {})
              .get("content", "")
              .strip()
          )
          if text:
            logger.info("تم توليد الرد عبر المحرك السحابي الفوري.")
            return text
  except Exception as e:
    logger.error(f"استثناء المحرك الفوري: {e}")
  return ""


async def generate_smart_ai_reply(history: list) -> str:
  """توليد الرد الذكي المعتمد على الذكاء الاصطناعي وسياق المحادثة بالكامل"""
  # 1. التجربة عبر Google Gemini
  ans = await query_gemini(history)
  if ans:
    return ans

  # 2. التجربة عبر OpenRouter
  ans = await query_openrouter(history)
  if ans:
    return ans

  # 3. التجربة عبر المحرك السحابي الفوري المباشر
  ans = await query_pollinations_direct(history)
  if ans:
    return ans

  return (
      "هلا بيك عيوني، صاحب الحساب شوي طالع وما يمه الفون، بس يفرغ يرجعلك خبر إن"
      " شاء الله ❤️"
  )


bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher()


# معالجة رسائل Telegram Business
@dp.business_message()
async def handle_business_message(message: types.Message):
  global LAST_OWNER_ACTIVITY
  current_time = time.time()
  chat_id = message.chat.id
  text = message.text or message.caption or ""

  if not text:
    return

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

    # 3. إدارة ذاكرة وسياق المحادثة:
    conv = USER_CONVERSATIONS.setdefault(
        chat_id,
        {"count": 0, "last_msg_time": current_time, "history": []},
    )

    # تصفير المحادثة إذا مرت أكثر من ساعتين على آخر رسالة
    if (current_time - conv["last_msg_time"]) > 7200:
      conv["count"] = 0
      conv["history"] = []

    # التحقق من حد الـ 10 رسائل
    if conv["count"] >= MAX_REPLIES_PER_USER:
      logger.info(
          f"المستخدم {chat_id} وصل للحد الأقصى (10 رسائل). تم التخطي."
      )
      return

    # إضافة رسالة المستخدم الجديدة إلى سجل المحادثة
    conv["history"].append({"role": "user", "content": text})
    # الاحتفاظ بآخر 10 رسائل فقط في الذاكرة لتوفير السرعة
    if len(conv["history"]) > 10:
      conv["history"] = conv["history"][-10:]

    conv["count"] += 1
    conv["last_msg_time"] = current_time

    # 4. توليد الرد الذكي المعتمد على كامل سياق الحوار بالذكاء الاصطناعي:
    reply_text = await generate_smart_ai_reply(conv["history"])

    # حفظ رد البوت في الذاكرة للمتابعة في الرسائل القادمة
    conv["history"].append({"role": "assistant", "content": reply_text})

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
      "أهلاً بك! البوت مبرمج بالذكاء الاصطناعي للردود التلقائية باللهجة"
      " العراقية."
  )


# خادم ويب لإبقاء Render نشطاً
async def health_check(request):
  return web.Response(text="Telegram Business AI Bot is running!", status=200)


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
