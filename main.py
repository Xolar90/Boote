import asyncio
import logging
import os
import random
import time
import json
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
OWNER_INACTIVITY_THRESHOLD = 90          # 90 ثانية خمول قبل الرد
MAX_REPLIES_PER_USER = 15
HISTORY_LIMIT = 14
CONVERSATION_RESET_AFTER = 7200

# ==================== الذاكرة ====================
USER_CONVERSATIONS: Dict[int, Dict[str, Any]] = {}
LAST_OWNER_ACTIVITY: float = 0.0
OWNER_ID: int | None = None
# مجموعة إضافية من المعرفات التي نعتبرها "صاحب الحساب" (يمكن توسيعها يدوياً)
OWNER_IDS: set[int] = set()

# ==================== شخصية البوت ====================
SYSTEM_PROMPT = (
    "أنت شخص عراقي واقعي ولطيف جداً تجاوب في محادثة تليجرام خاصة نيابة عن صاحب "
    "الحساب (صاحب الحساب مو يمه التلفون هسه طالع أو مشغول).\n\n"
    "قواعد الحديث الإلزامية:\n"
    "1. تحدث مثل إنسان عراقي حقيقي 100% بلهجة عراقية/بغدادية عفوية وطبيعية ومحترمة.\n"
    "   كلمات مفيدة: هلا عيوني، حبيبي، شخبارك، شكو ماكو، دومك يارب، تدلل، ههههه، "
    "فدوه لعينك، لا تاكل هم، هسه هو مو يمه التلفون بس يرجع يحاجيك.\n"
    "2. افهم سياق الكلام السابق جيداً وجاوب بدقة:\n"
    "   - إذا سأل «شوكت يرجع» أو «متى يرجع» → قل عنده شغلة طالع تقريباً ساعة ويرجع.\n"
    "   - إذا سلم → رد السلام بلطف.\n"
    "   - إذا شكرك → رد بتدلل وتكرم.\n"
    "   - إذا سأل «شنو» أو «شبيك» أو «وزي» → جاوب بطريقة طبيعية حسب السياق.\n"
    "3. ممنوع تماماً:\n"
    "   - التحدث كبوت أو نظام آلي.\n"
    "   - تكرار نفس الجملة أو نفس الرد.\n"
    "   - الردود الطويلة (خليها قصيرة وطبيعية).\n"
    "4. كل رسالة لازم يكون لها رد فريد وذكي ومناسب للسياق."
)

# ==================== ردود احتياطية ذكية ومتنوعة ====================
def get_smart_fallback(user_text: str, history: List[dict] | None = None) -> str:
    """رد ذكي محلي يفهم نوع السؤال ويتجنب التكرار"""
    text = (user_text or "").strip().lower()

    # جمع الردود السابقة لتجنب التكرار
    previous_replies = set()
    if history:
        for h in history:
            if h.get("role") == "assistant":
                previous_replies.add(h.get("content", "").strip())

    def pick(options: list[str]) -> str:
        available = [o for o in options if o not in previous_replies]
        if not available:
            available = options
        return random.choice(available)

    # تحيات
    if any(w in text for w in ["هلا", "هلو", "مرحبا", "السلام", "سلام عليكم", "هاي", "أهلا", "اهلا"]):
        return pick([
            "هلا بيك عيوني ❤️ شخبارك؟",
            "هلا والله حبيبي، شلونك؟",
            "أهلاً وسهلاً تدلل، شكو ماكو؟",
            "هلا عيوني، دومك يارب 🌹",
            "وعليكم السلام حبيبي، شلونك؟",
        ])

    # متى يرجع / شوكت
    if any(w in text for w in ["شوكت", "متى", "يمتى", "وقت يرجع", "يرجع", "متى يرجع", "شوكت يرجع"]):
        return pick([
            "هسه هو طالع شغلة، تقريباً ساعة زمان ويرجع إن شاء الله ⏳",
            "ما يمه الفون هسه، بس يفرغ يرجعلك خبر خلال ساعة أو أقل ❤️",
            "عنده شغل برا، يرجع قريب إن شاء الله، لا تاكل هم",
            "شوي مشغول، بس يرجع يحاجيك بأقرب وقت تدلل",
            "يرجع قريب إن شاء الله، خلينا ننتظره شوية",
        ])

    # شنو / ماذا / وضح
    if any(w in text for w in ["شنو", "ماذا", "ما هو", "ايش", "وشو", "قصدك"]):
        return pick([
            "ههه شنو بالضبط؟ وضحلي أكثر عيوني",
            "ما فهمت زين، عيد السؤال لو سمحت حبيبي",
            "قصدك شنو بالضبط؟ قلي أكثر تفاصيل",
            "مو واضح عندي، اشرح أكثر تدلل",
        ])

    # شبيك / شلك / وينك
    if any(w in text for w in ["شبيك", "شلك", "وينك", "وين صرت", "شلونك", "شخبارك"]):
        return pick([
            "والله تمام الحمد لله، بس صاحب الحساب مو يمه الفون هسه ❤️",
            "زين الحمد لله، هو طالع شغلة ويرجع قريب",
            "بخير تدلل، بس هو مشغول شوي حالياً",
            "الحمد لله تمام، يرجعك خبر قريب إن شاء الله",
        ])

    # وزي / تمام / اوك
    if any(w in text for w in ["وزي", "وزين", "تمام", "اوك", "اوكي", "طيب", "حاضر"]):
        return pick([
            "تمام عيوني ❤️",
            "تدلل حبيبي",
            "إن شاء الله يرجع قريب ويحاجيك",
            "زين، لا تاكل هم",
        ])

    # لماذا نفس الرد / تكرر
    if any(w in text for w in ["لماذا", "ليش", "نفس الرد", "تكرر", "نفس الشي", "نفس", "ليش ترد"]):
        return pick([
            "هههه آسف، صاحب الحساب مشغول واحنا نحاول نرد عنّه أحسن ما نقدر 😅",
            "لأن هو مو يمه الفون هسه، بس يرجع يحاجيك بنفسه قريب إن شاء الله",
            "هسه الوضع شغلة، بس لا تاكل هم يرجعك خبر",
            "المعذرة، نحاول نوصل الرسالة بأفضل شكل لين يرجع هو",
        ])

    # شكر
    if any(w in text for w in ["شكرا", "شكراً", "مشكور", "تسلم", "يعطيك", "يسلمو"]):
        return pick([
            "تدلل عيوني ❤️",
            "تكرم حبيبي، أي وقت",
            "العفو والله، دومك يارب",
            "ما يسوى حبيبي",
        ])

    # ضحك
    if any(w in text for w in ["ههه", "هههه", "lol", "😂", "🤣", "هع"]):
        return pick([
            "ههههه والله 😂",
            "هههه تدلل",
            "ههههه عيوني",
            "😂😂 دومك يارب",
        ])

    # افتراضي متنوع
    return pick([
        "هسه هو مو يمه التلفون، بس يرجع يحاجيك إن شاء الله ❤️",
        "صاحب الحساب طالع شغلة، يرجع قريب تدلل",
        "ما يمه الفون هسه، بس يفرغ يرجعلك خبر ⏳",
        "عيوني هو مشغول شوي، بس يرجعك إن شاء الله لا تاكل هم",
        "شوي صبر، يرجع قريب ويحاجيك بنفسه",
        "هو برا شغلة، إن شاء الله يرجع بأقرب وقت",
    ])


# ==================== محركات الذكاء الاصطناعي ====================
async def query_gemini(messages_history: List[dict]) -> str:
    if not GEMINI_API_KEY:
        logger.warning("⚠️ GEMINI_API_KEY غير موجود في Environment Variables")
        return ""

    contents = []
    for msg in messages_history:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    models = [
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
        "gemini-1.5-pro",
        "gemini-1.5-flash-latest",
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
                "temperature": 0.95,
                "maxOutputTokens": 220,
                "topP": 0.95,
                "topK": 40,
            },
        }
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    body = await resp.text()
                    if resp.status == 200:
                        data = json.loads(body)
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts and "text" in parts[0]:
                                text = parts[0]["text"].strip()
                                # تنظيف بسيط
                                if text.startswith('"') and text.endswith('"'):
                                    text = text[1:-1]
                                if text:
                                    logger.info(f"✅ Gemini نجح ← {model}")
                                    return text
                        logger.warning(f"Gemini {model}: لا يوجد نص | {body[:200]}")
                    else:
                        logger.error(f"❌ Gemini {model} status={resp.status} | {body[:350]}")
                        # إذا كان الخطأ 400 أو 403 بسبب المفتاح، لا تجرب باقي النماذج
                        if resp.status in (400, 403):
                            logger.error("مشكلة في المفتاح أو الصلاحيات — توقف عن تجربة نماذج أخرى")
                            break
        except Exception as e:
            logger.error(f"استثناء Gemini ({model}): {type(e).__name__}: {e}")
    return ""


async def query_groq(messages_history: List[dict]) -> str:
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
            "max_tokens": 200,
            "temperature": 0.9,
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
                            logger.info(f"✅ Groq نجح ← {model}")
                            return text
                    else:
                        body = await resp.text()
                        logger.warning(f"Groq {model} status={resp.status} | {body[:200]}")
        except Exception as e:
            logger.error(f"استثناء Groq ({model}): {e}")
    return ""


async def query_openrouter(messages_history: List[dict]) -> str:
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
            "max_tokens": 200,
            "temperature": 0.9,
        }
        try:
            timeout = aiohttp.ClientTimeout(total=14)
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
                            logger.info(f"✅ OpenRouter نجح ← {model}")
                            return text
        except Exception as e:
            logger.error(f"استثناء OpenRouter ({model}): {e}")
    return ""


async def generate_smart_ai_reply(history: List[dict], last_user_text: str) -> str:
    """Gemini → Groq → OpenRouter → رد ذكي محلي"""
    for name, func in [
        ("Gemini", query_gemini),
        ("Groq", query_groq),
        ("OpenRouter", query_openrouter),
    ]:
        try:
            ans = await func(history)
            if ans and len(ans.strip()) > 2:
                return ans.strip()
        except Exception as e:
            logger.error(f"فشل {name}: {e}")

    logger.warning("⚠️ كل محركات الـ AI فشلت → استخدام الرد الذكي المحلي")
    return get_smart_fallback(last_user_text, history)


# ==================== تهيئة البوت ====================
if not BOT_TOKEN:
    logger.critical("❌ BOT_TOKEN غير موجود!")
    bot = None
else:
    bot = Bot(token=BOT_TOKEN)

dp = Dispatcher()


def is_owner(user_id: int | None) -> bool:
    """التحقق هل هذا المستخدم هو صاحب الحساب"""
    if user_id is None:
        return False
    if OWNER_ID and user_id == OWNER_ID:
        return True
    if user_id in OWNER_IDS:
        return True
    return False


# ==================== المعالجات ====================
@dp.business_connection()
async def on_business_connection(event: BusinessConnection):
    global OWNER_ID
    OWNER_ID = event.user.id
    OWNER_IDS.add(event.user.id)
    status = "مفعّل" if event.is_enabled else "معطّل"
    logger.info(f"🔗 Business Connection | owner_id={OWNER_ID} | {status}")


@dp.business_message(F.text)
async def handle_business_message(message: Message):
    global LAST_OWNER_ACTIVITY

    if not bot:
        return

    current_time = time.time()
    chat_id = message.chat.id
    text = (message.text or "").strip()
    from_user_id = message.from_user.id if message.from_user else None

    if not text:
        return

    try:
        # ========== 1. إذا الرسالة من صاحب الحساب → لا ترد أبداً ==========
        if is_owner(from_user_id):
            LAST_OWNER_ACTIVITY = current_time
            USER_CONVERSATIONS.pop(chat_id, None)
            logger.info(f"👤 صاحب الحساب كتب (id={from_user_id}) → تم التجاهل وتصفير المحادثة")
            return

        # ========== 2. فترة الخمول ==========
        time_since = current_time - LAST_OWNER_ACTIVITY
        if time_since < OWNER_INACTIVITY_THRESHOLD:
            remaining = int(OWNER_INACTIVITY_THRESHOLD - time_since)
            logger.info(f"⏳ صاحب الحساب لا يزال ضمن فترة النشاط (متبقي {remaining} ث) → لا رد")
            return

        # ========== 3. إدارة السياق ==========
        conv = USER_CONVERSATIONS.setdefault(
            chat_id, {"count": 0, "last_msg_time": current_time, "history": []}
        )

        if (current_time - conv["last_msg_time"]) > CONVERSATION_RESET_AFTER:
            conv["count"] = 0
            conv["history"] = []
            logger.info(f"🔄 تصفير سياق قديم لـ {chat_id}")

        if conv["count"] >= MAX_REPLIES_PER_USER:
            logger.info(f"🛑 وصل للحد الأقصى ({MAX_REPLIES_PER_USER}): {chat_id}")
            return

        # إضافة رسالة المستخدم
        conv["history"].append({"role": "user", "content": text})
        if len(conv["history"]) > HISTORY_LIMIT:
            conv["history"] = conv["history"][-HISTORY_LIMIT:]

        conv["count"] += 1
        conv["last_msg_time"] = current_time

        # ========== 4. توليد الرد ==========
        reply_text = await generate_smart_ai_reply(conv["history"], text)

        # منع التكرار المباشر لنفس الرد السابق
        if conv["history"] and conv["history"][-1].get("role") == "assistant":
            if conv["history"][-1].get("content", "").strip() == reply_text.strip():
                reply_text = get_smart_fallback(text, conv["history"])

        conv["history"].append({"role": "assistant", "content": reply_text})

        # ========== 5. إرسال الرد ==========
        await bot.send_message(
            chat_id=chat_id,
            text=reply_text,
            business_connection_id=message.business_connection_id,
            reply_to_message_id=message.message_id,
        )
        logger.info(f"💬 رد ({conv['count']}/{MAX_REPLIES_PER_USER}) → {chat_id}: {reply_text[:50]}...")

    except Exception as e:
        logger.exception(f"❌ خطأ معالجة رسالة من {chat_id}: {e}")


@dp.message(CommandStart())
async def handle_start(message: Message):
    await message.answer(
        "أهلاً بك! 👋\n"
        "بوت الرد التلقائي الذكي لحسابات Telegram Business.\n"
        "يرد باللهجة العراقية عندما تكون مشغولاً.\n\n"
        "الأوامر:\n"
        "/status — حالة البوت والمفاتيح\n"
        "/clear — تصفير ذاكرة المحادثات\n"
        "/setowner — تسجيل نفسك كصاحب الحساب (مهم)"
    )


@dp.message(Command("status"))
async def handle_status(message: Message):
    active = len(USER_CONVERSATIONS)
    inactive = int(time.time() - LAST_OWNER_ACTIVITY) if LAST_OWNER_ACTIVITY else "—"
    gemini = "✅ موجود" if GEMINI_API_KEY else "❌ غير موجود"
    groq = "✅ موجود" if GROQ_API_KEY else "❌ غير موجود"
    openrouter = "✅ موجود" if OPENROUTER_API_KEY else "❌ غير موجود"
    owner_info = f"{OWNER_ID}" if OWNER_ID else "لم يُسجَّل بعد"
    await message.answer(
        f"📊 حالة البوت:\n\n"
        f"• المحادثات النشطة: {active}\n"
        f"• آخر نشاط لصاحب الحساب: قبل {inactive} ثانية\n"
        f"• OWNER_ID المسجل: {owner_info}\n"
        f"• Gemini: {gemini}\n"
        f"• Groq: {groq}\n"
        f"• OpenRouter: {openrouter}\n"
        f"• حد الردود: {MAX_REPLIES_PER_USER}\n"
        f"• عتبة الخمول: {OWNER_INACTIVITY_THRESHOLD} ثانية"
    )


@dp.message(Command("clear"))
async def handle_clear(message: Message):
    count = len(USER_CONVERSATIONS)
    USER_CONVERSATIONS.clear()
    await message.answer(f"✅ تم تصفير {count} محادثة.")


@dp.message(Command("setowner"))
async def handle_setowner(message: Message):
    """يسجل من يرسل الأمر كصاحب الحساب (مهم إذا لم يصل business_connection)"""
    global OWNER_ID
    if not message.from_user:
        return
    OWNER_ID = message.from_user.id
    OWNER_IDS.add(OWNER_ID)
    await message.answer(
        f"✅ تم تسجيلك كصاحب الحساب\n"
        f"معرفك: `{OWNER_ID}`\n\n"
        f"الآن البوت لن يرد على رسائلك أنت."
    )
    logger.info(f"تم تسجيل OWNER_ID يدوياً = {OWNER_ID}")


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
    logger.info(f"🌐 خادم الويب يعمل على المنفذ {port}")


# ==================== التشغيل ====================
async def main() -> None:
    if not bot:
        logger.critical("BOT_TOKEN مفقود — توقف")
        return

    await start_web_server()

    logger.info("🚀 بدء تشغيل البوت...")
    logger.info(f"Gemini     : {'✅ مفعّل' if GEMINI_API_KEY else '❌ غير مفعّل'}")
    logger.info(f"Groq       : {'✅ مفعّل' if GROQ_API_KEY else '❌ غير مفعّل'}")
    logger.info(f"OpenRouter : {'✅ مفعّل' if OPENROUTER_API_KEY else '❌ غير مفعّل'}")

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
