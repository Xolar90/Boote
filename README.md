# Telegram Business Auto-Reply Bot (Iraqi Dialect)

بوت تيليجرام ذكي للرد التلقائي على الرسائل الخاصة نيابة عنك باستخدام **Telegram Business**.  
يرد باللهجة العراقية العفوية عندما تكون مشغولاً.

## المميزات
- رد ذكي مع فهم سياق المحادثة
- لهجة عراقية/بغدادية طبيعية
- سلسلة محركات: **Gemini → Groq → OpenRouter → ردود ذكية محلية**
- لا يكرر نفس الرد أبداً (حتى لو فشل الـ AI)
- يتوقف تلقائياً عندما تكون نشطاً
- يعمل مجاناً على Render.com

## إعداد المفاتيح (مهم جداً)

في Render → Environment Variables أضف:

| المفتاح | مطلوب؟ | من أين تحصل عليه |
|---------|--------|------------------|
| `BOT_TOKEN` | إجباري | @BotFather |
| `GEMINI_API_KEY` | موصى به بقوة | [Google AI Studio](https://aistudio.google.com/apikey) |
| `GROQ_API_KEY` | اختياري (سريع) | [console.groq.com](https://console.groq.com) |
| `OPENROUTER_API_KEY` | اختياري | [openrouter.ai](https://openrouter.ai) |

> **لا تضع المفتاح داخل الكود أبداً.** ضعه فقط في Environment Variables.

## خطوات التشغيل على Render

1. ارفع الملفات إلى GitHub
2. New Web Service على Render
3. Build: `pip install -r requirements.txt`
4. Start: `python main.py`
5. أضف المتغيرات أعلاه
6. Deploy
7. ضع رابط الخدمة في UptimeRobot (كل 5 دقائق)

## تفعيل Business Mode

1. اذهب لـ @BotFather → /mybots → اختر البوت → Bot Settings → Business Mode → فعّله
2. من تطبيق تيليجرام: الإعدادات → Telegram Business → Chatbots → أضف البوت

## أوامر البوت
- `/start` – ترحيب
- `/status` – حالة المفاتيح والمحادثات
- `/clear` – تصفير الذاكرة

## ملاحظات
- بعد إضافة `GEMINI_API_KEY` أعد تشغيل الخدمة (Manual Deploy).
- إذا رأيت في اللوج `✅ Gemini نجح` فكل شيء يعمل.
- الردود المحلية الذكية تعمل حتى بدون أي مفتاح AI.
