# 🧠 Main Brain — Habit Tracker Telegram bot

Bot har bir foydalanuvchi uchun shaxsiy odat (habit) jadvali tuzadi, kerakli vaqtda eslatadi, kun oxirida natijani **Gemini** yordamida 10 ballik tizimda baholaydi va maqsad kuni kelganda butun yo'lni jadval + rasmlar bilan yuboradi.

## Bot qanday ishlaydi

1. **Anketa** (`/start`): maqsad → qolgan kunlar → kunlik vaqt → mashqlar (yoki «Brain tanlasin») → boshlash soati → haftasiga 1 / 3 / 7 kun.
2. **Eslatma:** belgilangan soatda «Hurmatli ... foydalanuvchi, siz soat ...da «...» maqsadingiz tomon harakat qilishingizni aytgansiz va maqsad kuniga ... kun qoldi. Iltimos, harakatni boshlang!» xabari keladi. Boshlamasangiz har 30 daqiqada yana eslatadi (ko'pi bilan 4 marta).
3. **«Boshladim»** bosilgach bot ajratilgan vaqtni sanaydi. Vaqt tugagach: *«Bajardingizmi?»*. Erta tugatsangiz «Erta tugatdim» tugmasi bor.
4. **Hisobot:** nimalarni bajargan, nimalarni bajarmagan va sabablarini yozasiz, so'ng natija rasmlarini (1–10 ta) yuborasiz.
5. **Baho:** Main Brain hisobot va rasmlarga qarab 10 ball beradi.
   - **8, 9, 10** → ertaga reja o'zgarishsiz.
   - **8 dan past** → bajarilmagan vazifalar keyingi ish kuniga qo'shimcha bo'lib qo'shiladi.
   - Hisobot kelmasa → kun 0 ball bilan o'tkazib yuboriladi, vazifalar keyingi kunga o'tadi.
6. **Maqsad kuni** kelganda bot jadval (rasm), Main Brain xulosasi va kunma-kun rasmlarni yuboradi.

## Gemini vaqtincha ishlamasa nima bo'ladi

Google serveri ba'zan (kamdan-kam) vaqtincha band bo'lib qoladi (`503 UNAVAILABLE`). Bot buni ikki xil bosqichda hal qiladi:

- **Mashqlar tuzishda** (anketa, 4-qadam): agar Gemini butunlay javob bermasa, bot foydalanuvchi yozgan matndan (masalan `Reading - 1 soat`) o'zi mahalliy reja tuzadi, hech qachon to'xtab qolmaydi.
- **Kunlik hisobotni baholashda**: darhol muvaffaqiyatsiz bo'lsa, bot rasm va hisobotni yo'qotmasdan 3, 6, so'ng 12 daqiqadan keyin **o'zi avtomatik qayta uradi** — foydalanuvchi hech narsa qilishi shart emas. 4 marta ham ishlamasa, «Tayyor» tugmasi orqali istalgan payt qo'lda qayta urinish mumkin.

## Vazifa fayllarini oldindan yuklab qo'yish

Istalgan vaqtda botga fayl yuborsangiz (rasm, Word, Excel, PDF, video, ovozli xabar — xohlagan format), agar hozir hech qanday hisobot yoki rasm kutilmayotgan bo'lsa, bot uni **navbatga** qo'yadi. Har bir ish kuni «Boshladim» tugmasi bosilganda, navbatdagi birinchi fayl avtomatik yuboriladi. Kun o'tkazib yuborilsa, fayl navbatda qoladi va keyingi faol kunda chiqadi — hech narsa yo'qolmaydi. Maqsad kuni kelganda, ishlatilmagan qolgan fayllar ham yakuniy hisobot bilan birga yuboriladi.

## Ma'lumotlar qayerda saqlanadi

- **Baza: PostgreSQL** (alohida serverda). Foydalanuvchilar, jadval, ballar, anketa holati shu yerda.
- **Rasmlar:** botga yuborilgan rasmlarning Telegram `file_id` si bazada saqlanadi (har bir foydalanuvchi va kun bo'yicha alohida). Rasmning o'zi Telegram serverlarida turadi, shuning uchun botning serverida disk kerak emas. Baholash vaqtida rasmlar vaqtincha yuklab olinib, Gemini'ga beriladi.

## Buyruqlar

| Buyruq | Vazifasi |
|---|---|
| `/start` | Yangi maqsad qo'yish |
| `/holat` | Bugungi holat va umumiy natija |
| `/jadval` | Habit tracker jadvalini ko'rish |
| `/reset` | Ma'lumotlarni o'chirib, qaytadan boshlash |
| `/yordam` | Buyruqlar ro'yxati |

## 1-qadam. PostgreSQL bazasini tayyorlang

Istalgan PostgreSQL server ishlaydi: o'zingizning VPS, yoki bepul bulutli baza (masalan Neon, Supabase). Kerak bo'lgan narsa yagona manzil (connection string):

```
postgresql://USER:PAROL@HOST:5432/BAZA
```

Eslatmalar:
- Bulutli bazada manzil oxirida `?sslmode=require` bo'lishi mumkin, shunday qoldiring.
- Neon manzilida `channel_binding=require` bo'lsa, uni **o'chirib tashlang**.
- Jadvallarni qo'lda yaratish shart emas, bot birinchi ishga tushganda o'zi yaratadi.

## 2-qadam. Tokenlarni oling

- **Telegram bot tokeni:** [@BotFather](https://t.me/BotFather) → `/newbot`.
- **Gemini API kaliti:** [aistudio.google.com/apikey](https://aistudio.google.com/apikey).

## Lokal ishga tushirish (sinash uchun)

Kerak: Python 3.10+.

```bash
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Linux / macOS
pip install -r requirements.txt
```

`.env.example` dan `.env` yarating va to'ldiring:

```
BOT_TOKEN=123456:ABC...
GEMINI_API_KEY=AIza...
GEMINI_MODEL=gemini-3.5-flash
TIMEZONE=Asia/Tashkent
DATABASE_URL=postgresql://USER:PAROL@HOST:5432/BAZA
```

```bash
python main.py
```

Lokal rejimda bot **polling** bilan ishlaydi. Tez sinash uchun lokal baza (Docker):

```bash
docker run -d --name habitdb -e POSTGRES_PASSWORD=pass -p 5432:5432 postgres:16
```

`DATABASE_URL=postgresql://postgres:pass@localhost:5432/postgres`

## Render'ga deploy qilish (bepul Web Service)

Render'da bot **webhook** rejimida ishlaydi: Telegram xabarni to'g'ridan-to'g'ri servisga yuboradi. Render bergan `RENDER_EXTERNAL_URL` avtomatik ishlatiladi.

### 1. Kodni GitHub'ga yuklang

`render.yaml` repozitoriyning **ildizida** bo'lsin.

```bash
git init
git add .
git commit -m "habit bot"
git branch -M main
git remote add origin https://github.com/USERNAME/habit-bot.git
git push -u origin main
```

`.env` yuklanmaydi (`.gitignore` da yozilgan).

### 2. Render'da Blueprint yarating

1. [dashboard.render.com](https://dashboard.render.com) → **New +** → **Blueprint** → repozitoriyni tanlang.
2. So'ralganda `BOT_TOKEN`, `GEMINI_API_KEY`, `DATABASE_URL` ni kiriting.
3. **Apply** bosing.
4. Logs'da `Webhook rejimi: https://...onrender.com` yozuvi chiqsa, tayyor.

### 3. Servisni uxlatmaslik (MUHIM)

Bepul tarifda Render servisi taxminan 15 daqiqa tashqi so'rov bo'lmasa **uxlaydi**. Uxlagan servisda eslatmalar ishlamaydi, chunki eslatma bot ichidagi taymerga tayanadi. Buni tashqi «ping» xizmati hal qiladi:

1. [UptimeRobot](https://uptimerobot.com) yoki [cron-job.org](https://cron-job.org) da bepul hisob oching.
2. Yangi monitor: `https://<servis-nomi>.onrender.com/health`, oraliq **5 daqiqa**.

Ping o'tkazib yuborilsa ham ma'lumot yo'qolmaydi: servis uyg'onganda bot vaqtni o'zi solishtiradi va kechikkan eslatma/hisobotni yuboradi. Faqat xabar kechroq keladi.

Bepul tarifning oylik soat limiti va shartlari o'zgarishi mumkin, render.com/pricing da tekshirib turing.

### Muhim qoidalar

- Faqat **1 ta instance** ishlasin.
- Kodni yangilash: `git push` qilsangiz Render o'zi qayta deploy qiladi.
- Sozlamani o'zgartirish: Dashboard → servis → **Environment**.

## Sozlamalar (`config.py`)

| Nom | Qiymat | Ma'nosi |
|---|---|---|
| `PASS_SCORE` | 8 | Shu balldan yuqori bo'lsa reja o'zgarmaydi |
| `MAX_PHOTOS_PER_DAY` | 10 | Kuniga eng ko'p rasm |
| `FINAL_PHOTOS_PER_DAY` | 3 | Yakuniy hisobotda har kundan nechta rasm |
| `REMINDER_INTERVAL_MIN` | 30 | Eslatmalar oralig'i (daqiqa) |
| `MAX_REMINDERS` | 4 | Kuniga eng ko'p eslatma |
| `REPORT_GRACE_HOURS` | 12 | Hisobot uchun qo'shimcha kutish vaqti |

## Fayllar tuzilmasi

```
habit_bot/
├── main.py          # ishga tushirish (webhook yoki polling)
├── config.py        # sozlamalar
├── render.yaml      # Render deploy sozlamalari
├── handlers.py      # anketa, tugmalar, hisobot qabul qilish
├── scheduler.py     # eslatmalar va vaqt nazorati
├── service.py       # kunni yopish, qoldiqni ko'chirish, yakunlash
├── brain.py         # Gemini bilan aloqa (Main Brain)
├── report.py        # jadval rasmi va yakuniy hisobot
├── plan.py          # vaqt/sana hisob-kitoblari
├── db.py            # PostgreSQL
└── storage.py       # anketa holatini bazada saqlash
```

## Ko'p uchraydigan muammolar

- **Bot javob bermayapti** → Logs'ni oching; `BOT_TOKEN` va `DATABASE_URL` to'g'riligini tekshiring.
- **Baza bilan ulanish xatosi** → manzilni, parolni va bazaning tashqi ulanishga ruxsat berganini tekshiring (Neon'da `channel_binding` ni olib tashlang).
- **«Main Brain javob bera olmadi»** → `GEMINI_API_KEY` va `GEMINI_MODEL` nomini tekshiring.
- **Eslatma kech keladi** → ping xizmati ishlayotganini tekshiring (3-qadam).
- **Eslatma noto'g'ri vaqtda keladi** → `TIMEZONE` ni to'g'rilang.
- **Telegram `Conflict` xatosi** → bir vaqtda ikki joyda (masalan lokal va Render) polling ishlayapti. Lokal botni o'chiring.
