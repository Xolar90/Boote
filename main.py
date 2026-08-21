import asyncio
import logging
import os
import random
import time
from typing import Dict, Any, List

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, BusinessConnection
from aiohttp import web
import aiohttp

# ==================== إعداد التسجيل ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("BusinessBot")

# ==================== المتغيرات البيئية ====================
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
OPENROUTER_API_KEY = (
    os.getenv("OPENROUTER_API_KEY") or os.getenv("AI_API_KEY") or ""
).strip()
GROQ_API_KEY = (os.getenv("GROQ_API_KEY") or "").strip()

# ==================== إعدادات السلوك ====================
OWNER_INACTIVITY_THRESHOLD = 60
MAX_REPLIES_PER_USER = 12
HISTORY_LIMIT = 12
CONVERSATION_RESET_AFTER = 7200

# ==================== الذاكرة ====================
USER_CONVERSATIONS: Dict[int, Dict[str, Any]] = {}
LAST_OWNER_ACTIVITY: float = 0.0
OWNER_ID: int | None = None

# ==================== شخصية البوت ====================
SYSTEM_PROMPT = (
    "أنت شخص عراقي واقعي ولطيف جداً تجاوب في محادثة تليجرام خاصة نيابة عن صاحب "
    "الحساب (صاحب الحساب مو يمه التلفون هسه طالع أو مشغول).\n"
    "قواعد الحديث:\n"
    "1. تحدث مثل إنسان عراقي حقيقي وبشري 100% بلهجة عراقية/بغدادية عفوية وطبيعية "
    "ومحترمة (استخدم: هلا عيوني، حبيبي، شخبارك، شكو ماكو، دومك يارب، تدلل، "
    "ههههه، فدوه لعينك، لا تاكل هم، هسه هو مو يمه التلفون بس يرجع يحاجيك).\n"
    "2. افهم سياق الكلام السابق وجاوب بدقة على كل سؤال "
    "(إذا سأل شوكت يرجع قله عنده شغلة طالع ساعة زمان ويرجع، "
    "إذا سلم رد السلام، إذا شكرك رد بتدلل وتكرم).\n"
    "3. ممنوع التحدث كبوت أو نظام آلي أو تكرار نفس الجملة! "
    "كل رسالة لها رد فريد وذكي ومختصر ومناسب لسياقها.\n"
    "4. لا تكرر نفس الرد أبداً. نوّع دائماً."
)

# ردود احتياطية ذكية حسب نوع السؤال (تُستخدم فقط إذا فشل كل الـ AI)
SMART_FALLBACKS = {
    "greeting": [
        "هلا بيك عيوني ❤️ شخبارك؟",
        "هلا والله حبيبي، شلونك؟",
        "أهلاً وسهلاً تدلل، شكو ماكو؟",
        "هلا عيوني، دومك يارب 🌹",
    ],
    "when": [
        "هسه هو طالع شغلة، تقريباً ساعة زمان ويرجع إن شاء الله ⏳",
        "ما يمه الفون هسه، بس يفرغ يرجعلك خبر خلال ساعة أو أقل ❤️",
        "عنده شغل برا، يرجع قريب إن شاء الله، لا تاكل هم",
        "شوي مشغول، بس يرجع يحاجيك بأقرب وقت تدلل",
    ],
    "what": [
        "ههه شنو بالضبط؟ وضحلي أكثر عيوني",
        "ما فهمت زين، عيد السؤال لو سمحت حبيبي",
        "قصدك شنو بالضبط؟ قلي أكثر تفاصيل",
    ],
    "why_same": [
        "هههه آسف، صاحب الحساب مشغول واحنا نحاول نرد عنّه أحسن ما نقدر 😅",
        "لأن هو مو يمه الفون هسه، بس يرجع يحاجيك بنفسه قريب إن شاء الله",
        "هسه الوضع شغلة، بس لا تاكل هم يرجعك خبر",
    ],
    "thanks": [
        "تدلل عيوني ❤️",
        "تكرم حبيبي، أي وقت",
        "العفو والله، دومك يارب",
    ],
    "default": [
        "هسه هو مو يمه التلفون، بس يرجع يحاجيك إن شاء الله ❤️",
        "صاحب الحساب طالع شغلة، يرجع قريب تدلل",
        "ما يمه الفون هسه، بس يفرغ يرجعلك خبر ⏳",
        "عيوني هو مشغول شوي، بس يرجعك إن شاء الله لا تاكل هم",
    ],
}


def get_smart_fallback(user_text: str) -> str:
    """رد ذكي محلي حسب محتوى الرسالة حتى لو فشل الـ AI"""
    text = user_text.strip().lower()

    # تحيات
    if any(w in text for w in ["هلا", "هلو", "مرحبا", "السلام", "سلام", "ها", "هاي", "أهلا"]):
        return random.choice(SMART_FALLBACKS["greeting"])

    # متى يرجع
    if any(w in text for w in ["شوكت", "متى", "يمتى", "وقت", "يرجع", "يرجعك", "متى يرجع"]):
        return random.choice(SMART_FALLBACKS["when"])

    # شنو / ماذا
    if any(w in text for w in ["شنو", "ماذا", "ما هو", "ايش", "وشو"]):
        return random.choice(SMART_FALLBACKS["what"])

    # لماذا نفس الرد
    if any(w in text for w in ["لماذا", "ليش", "نفس الرد", "تكرر", "نفس الشي", "نفس"]):
        return random.choice(SMART_FALLBACKS["why_same"])

    # شكر
    if any(w in text for w in ["شكرا", "شكراً", "مشكور", "تسلم", "يعطيك"]):
        return random.choice(SMART_FALLBACKS["thanks"])

    return random.choice(SMART_FALLBACKS["default"])


# ==================== محركات الذكاء الاصطناعي ====================
async def query_gemini(messages_history: List[dict]) -> str:
    """Google Gemini - الأولوية الأولى"""
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY غير موجود")
        return ""

    # تحويل التاريخ لصيغة Gemini
    contents = []
    for msg in messages_history:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    # نماذج محدثة (الأحدث أولاً)
    models = [
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-flash-latest",
        "gemini-1.5-pro",
    ]

    for model in models:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={GEMINI_API_KEY}"
        )
        payload = {
            "contents": contents,
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "generationConfig": {
                "temperature": 0.9,
                "maxOutputTokens": 200,
                "topP": 0.95,
            },
        }
        try:
            timeout = aiohttp.ClientTimeout(total=12)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    body = await resp.text()
                    if resp.status == 200:
                        import json
                        data = json.loads(body)
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts and "text" in parts[0]:
                                text = parts[0]["text"].strip()
                                if text:
                                    logger.info(f"✅ Gemini نجح ({model})")
                                    return text
                        logger.warning(f"Gemini {model}: لا يوجد نص في الرد")
                    else:
                        logger.error(f"Gemini {model} status={resp.status} | {body[:300]}")
        except Exception as e:
            logger.error(f"استثناء Gemini ({model}): {e}")
    return ""


async def query_groq(messages_history: List[dict]) -> str:
    """Groq - سريع ومجاني"""
    if not GROQ_API_KEY:
        return ""

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + messages_history
    models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"]

    for model in models:
        payload = {
            "model": model,
            "messages": msgs,
            "max_tokens": 180,
            "temperature": 0.85,
        }
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        text = (
                            data.get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                            .strip()
                        )
                        if text:
                            logger.info(f"✅ Groq نجح ({model})")
                            return text
                    else:
                        body = await resp.text()
                        logger.warning(f"Groq {model} status={resp.status} | {body[:200]}")
        except Exception as e:
            logger.error(f"استثناء Groq ({model}): {e}")
    return ""


async def query_openrouter(messages_history: List[dict]) -> str:
    """OpenRouter - نماذج مجانية"""
    if not OPENROUTER_API_KEY:
        return ""

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://render.com",
        "X-Title": "Iraqi Business Bot",
        "Content-Type": "application/json",
    }
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + messages_history
    models = [
        "meta-llama/llama-3.3-70b-instruct:free",
        "google/gemini-2.0-flash-exp:free",
        "microsoft/phi-3-mini-128k-instruct:free",
    ]

    for model in models:
        payload = {
            "model": model,
            "messages": msgs,
            "max_tokens": 180,
            "temperature": 0.85,
        }
        try:
            timeout = aiohttp.ClientTimeout(total=12)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        text = (
                            data.get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                            .strip()
                        )
                        if text:
                            logger.info(f"✅ OpenRouter نجح ({model})")
                            return text
        except Exception as e:
            logger.error(f"استثناء OpenRouter ({model}): {e}")
    return ""


async def generate_smart_ai_reply(history: List[dict], last_user_text: str) -> str:
    """توليد الرد: Gemini → Groq → OpenRouter → رد ذكي محلي"""
    for name, func in [
        ("Gemini", query_gemini),
        ("Groq", query_groq),
        ("OpenRouter", query_openrouter),
    ]:
        try:
            ans = await func(history)
            if ans and len(ans) > 3:
                return ans
        except Exception as e:
            logger.error(f"فشل {name}: {e}")

    # إذا فشل كل شيء → رد ذكي محلي متنوع
    logger.warning("كل محركات الـ AI فشلت → استخدام الرد الذكي المحلي")
    return get_smart_fallback(last_user_text)


# ==================== تهيئة البوت ====================
if not BOT_TOKEN:
    logger.critical("❌ BOT_TOKEN غير موجود!")
    bot = None
else:
    bot = Bot(token=BOT_TOKEN)

dp = Dispatcher()


# ==================== المعالجات ====================
@dp.business_connection()
async def on_business_connection(event: BusinessConnection):
    global OWNER_ID
    OWNER_ID = event.user.id
    status = "مفعّل" if event.is_enabled else "معطّل"
    logger.info(f"Business Connection | owner={OWNER_ID} | {status}")


@dp.business_message(F.text)
async def handle_business_message(message: Message):
    global LAST_OWNER_ACTIVITY

    if not bot:
        return

    current_time = time.time()
    chat_id = message.chat.id
    text = (message.text or "").strip()
    if not text:
        return

    try:
        # صاحب الحساب يكتب → توقف
        if OWNER_ID and message.from_user and message.from_user.id == OWNER_ID:
            LAST_OWNER_ACTIVITY = current_time
            USER_CONVERSATIONS.pop(chat_id, None)
            logger.info(f"صاحب الحساب نشط → تصفير {chat_id}")
            return

        # فترة الخمول
        if (current_time - LAST_OWNER_ACTIVITY) < OWNER_INACTIVITY_THRESHOLD:
            remaining = int(OWNER_INACTIVITY_THRESHOLD - (current_time - LAST_OWNER_ACTIVITY))
            logger.info(f"لا يزال نشطاً (متبقي {remaining} ث)")
            return

        # إدارة السياق
        conv = USER_CONVERSATIONS.setdefault(
            chat_id, {"count": 0, "last_msg_time": current_time, "history": []}
        )

        if (current_time - conv["last_msg_time"]) > CONVERSATION_RESET_AFTER:
            conv["count"] = 0
            conv["history"] = []

        if conv["count"] >= MAX_REPLIES_PER_USER:
            logger.info(f"وصل للحد الأقصى: {chat_id}")
            return

        conv["history"].append({"role": "user", "content": text})
        if len(conv["history"]) > HISTORY_LIMIT:
            conv["history"] = conv["history"][-HISTORY_LIMIT:]

        conv["count"] += 1
        conv["last_msg_time"] = current_time

        # توليد الرد
        reply_text = await generate_smart_ai_reply(conv["history"], text)

        # منع التكرار المباشر
        if len(conv["history"]) >= 2 and conv["history"][-1].get("content") == reply_text:
            reply_text = get_smart_fallback(text)

        conv["history"].append({"role": "assistant", "content": reply_text})

        await bot.send_message(
            chat_id=chat_id,
            text=reply_text,
            business_connection_id=message.business_connection_id,
            reply_to_message_id=message.message_id,
        )
        logger.info(f"رد ({conv['count']}/{MAX_REPLIES_PER_USER}) → {chat_id}: {reply_text[:40]}...")

    except Exception as e:
        logger.exception(f"خطأ معالجة {chat_id}: {e}")


@dp.message(CommandStart())
async def handle_start(message: Message):
    await message.answer(
        "أهلاً بك! 👋\n"
        "بوت الرد التلقائي الذكي لحسابات Telegram Business.\n"
        "يرد باللهجة العراقية عندما تكون مشغولاً.\n\n"
        "الأوامر:\n"
        "/status - حالة البوت\n"
        "/clear - تصفير الذاكرة"
    )


@dp.message(Command("status"))
async def handle_status(message: Message):
    active = len(USER_CONVERSATIONS)
    inactive = int(time.time() - LAST_OWNER_ACTIVITY) if LAST_OWNER_ACTIVITY else "—"
    gemini = "✅" if GEMINI_API_KEY else "❌"
    groq = "✅" if GROQ_API_KEY else "❌"
    openrouter = "✅" if OPENROUTER_API_KEY else "❌"
    await message.answer(
        f"📊 حالة البوت:\n"
        f"• المحادثات النشطة: {active}\n"
        f"• آخر نشاط: قبل {inactive} ثانية\n"
        f"• Gemini: {gemini}\n"
        f"• Groq: {groq}\n"
        f"• OpenRouter: {openrouter}\n"
        f"• حد الردود: {MAX_REPLIES_PER_USER}"
    )


@dp.message(Command("clear"))
async def handle_clear(message: Message):
    count = len(USER_CONVERSATIONS)
    USER_CONVERSATIONS.clear()
    await message.answer(f"✅ تم تصفير {count} محادثة.")


# ==================== خادم الويب ====================
async def health_check(request: web.Request) -> web.Response:
    return web.Response(text="Telegram Business AI Bot is running ✅", status=200)


async def start_web_server() -> None:
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🌐 خادم الويب على المنفذ {port}")


# ==================== التشغيل ====================
async def main() -> None:
    if not bot:
        logger.critical("BOT_TOKEN مفقود")
        return

    await start_web_server()

    logger.info("🚀 بدء البوت...")
    logger.info(f"Gemini: {'مفعّل' if GEMINI_API_KEY else 'غير مفعّل'}")
    logger.info(f"Groq: {'مفعّل' if GROQ_API_KEY else 'غير مفعّل'}")
    logger.info(f"OpenRouter: {'مفعّل' if OPENROUTER_API_KEY else 'غير مفعّل'}")

    await dp.start_polling(
        bot,
        allowed_updates=[
            "message",
            "business_message",
            "business_connection",
            "edited_business_message",
        ],
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("تم إيقاف البوت.")
