# Telegram Business Auto-Reply Bot

بوت تيليجرام مخصص للرد التلقائي على الرسائل الخاصة نيابة عنك باستخدام ميزة **Telegram Business**، مهيأ للتشغيل المجاني على استضافة **Render.com**.

## خطوات التشغيل:
1. ارفع هذه الملفات إلى مستودع جديد على **GitHub**.
2. انتقل إلى [Render Dashboard](https://dashboard.render.com).
3. اختر **New +** ثم **Web Service** واربط مستودع GitHub.
4. الإعدادات:
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python main.py`
   - **Plan:** `Free`
5. في قسم **Environment Variables**، أضف المتغير التالي:
   - `BOT_TOKEN`: التوكن الخاص ببوتك من @BotFather
6. اضغط **Deploy Web Service**.
7. بعد اكتمال النشر، انسخ رابط الخدمة وقم بإضافته إلى [UptimeRobot](https://uptimerobot.com) لفحص الرابط كل 10 دقائق حتى لا يتوقف السيرفر.
