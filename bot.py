import json
import os
import sys
import threading
import time
import telebot
from telebot import types

TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
if not TOKEN or ":" not in TOKEN:
    print("❌ خطأ: متغير البيئة BOT_TOKEN غير مضبوط! أضفه في Railway Variables ثم أعد التشغيل.")
    sys.exit(1)

bot = telebot.TeleBot(TOKEN)

DB_FILE = "movies_db.json"

DEFAULT_CATALOG = [
    {
        "title": "Inception",
        "category": "فيلم",
        "genre": "خيال علمي / إثارة",
        "duration": "2h 28m",
        "desc": "لص محترف يسرق الأسرار من داخل الأحلام وتُعرض عليه مهمة زرع فكرة في عقل هدفه.",
        "url": "https://www.imdb.com/title/tt1375666/",
        "media_type": "none",
        "media_id": None,
    },
    {
        "title": "Interstellar",
        "category": "فيلم",
        "genre": "مغامرة / خيال علمي",
        "duration": "2h 49m",
        "desc": "رحلة فضائية عبر ثقب دودي للبحث عن كوكب جديد صالح لحياة البشرية.",
        "url": "https://www.imdb.com/title/tt0816692/",
        "media_type": "none",
        "media_id": None,
    },
    {
        "title": "The Dark Knight",
        "category": "فيلم",
        "genre": "أكشن / جريمة",
        "duration": "2h 32m",
        "desc": "مواجهة شرسة في جوثام بين باتمان والجوكر الذي يختبر حدود المدينة وأخلاقها.",
        "url": "https://www.imdb.com/title/tt0468569/",
        "media_type": "none",
        "media_id": None,
    },
    {
        "title": "John Wick",
        "category": "فيلم",
        "genre": "أكشن / تشويق",
        "duration": "1h 41m",
        "desc": "قاتل محترف متقاعد يعود لعالم الجريمة بدافع الانتقام بعد سرقة سيارته وقتل كلبه.",
        "url": "https://www.imdb.com/title/tt2911666/",
        "media_type": "none",
        "media_id": None,
    },
    {
        "title": "Toy Story",
        "category": "كرتون",
        "genre": "كرتون / مغامرة / كوميديا",
        "duration": "1h 21m",
        "desc": "ألعاب تنبض بالحياة عندما لا يراها البشر وتبدأ مغامرة مشوقة بين وودي وباز لايتيير.",
        "url": "https://www.imdb.com/title/tt0114709/",
        "media_type": "none",
        "media_id": None,
    },
    {
        "title": "Tom and Jerry",
        "category": "كرتون",
        "genre": "كرتون كلاسيكي / كوميديا",
        "duration": "سلسلة حلقات",
        "desc": "مطارادات ومواقف كوميدية سريعة بين القط توم والفأر جيري لا تنتهي.",
        "url": "https://www.imdb.com/title/tt0032138/",
        "media_type": "none",
        "media_id": None,
    },
    {
        "title": "Spirited Away",
        "category": "كرتون",
        "genre": "أنيميشن / فانتازيا",
        "duration": "2h 05m",
        "desc": "فتاة تدخل عالماً سحرياً غامضاً وتبحث عن طريقة لإنقاذ والديها والعودة للمنزل.",
        "url": "https://www.imdb.com/title/tt0245429/",
        "media_type": "none",
        "media_id": None,
    },
    {
        "title": "Coco",
        "category": "كرتون",
        "genre": "كرتون / عائلي / موسيقى",
        "duration": "1h 45m",
        "desc": "طفل عاشق للموسيقى ينتقل إلى عالم الموتى ليكشف سر عائلته ويحقق حلمه.",
        "url": "https://www.imdb.com/title/tt2380307/",
        "media_type": "none",
        "media_id": None,
    },
]


def load_catalog():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and data:
                    return data
        except Exception as e:
            print(f"[DB_LOAD_ERR] {e}")
    save_catalog(DEFAULT_CATALOG)
    return list(DEFAULT_CATALOG)


def save_catalog(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[DB_SAVE_ERR] {e}")


catalog = load_catalog()
db_lock = threading.Lock()
search_waiting = {}      # user_id -> {"chat_id": int, "created_at": float}
adding_state = {}        # user_id -> dict
deleting_waiting = set() # user_id set


def escape_html(text):
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def normalize_ar(text):
    t = (text or "").strip().lower()
    t = (
        t.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ى", "ي")
        .replace("ة", "ه")
    )
    return " ".join(t.split())


def is_admin_in_chat(chat_id, user_id):
    if chat_id > 0:
        # في الخاص نسمح لو المستخدم كتب أمر الإدارة أو نتحقق من متغير ADMIN_IDS لو حابب تقيده
        admin_ids_env = (os.getenv("ADMIN_IDS") or "").strip()
        if not admin_ids_env:
            return True
        allowed = {int(x.strip()) for x in admin_ids_env.split(",") if x.strip().isdigit()}
        return user_id in allowed
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ["administrator", "creator"]
    except Exception:
        return False


def build_main_menu_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎬 أفلام", callback_data="cat:فيلم"),
        types.InlineKeyboardButton("🧸 كرتون", callback_data="cat:كرتون"),
    )
    markup.add(
        types.InlineKeyboardButton("🔍 اكتب اسم الفيلم أو الكرتون", callback_data="prompt_search")
    )
    return markup


def build_results_markup(items):
    markup = types.InlineKeyboardMarkup(row_width=1)
    with db_lock:
        for item in items:
            try:
                idx = catalog.index(item)
            except ValueError:
                continue
            icon = "🎬" if item.get("category") == "فيلم" else "🧸"
            title_short = (item.get("title") or "تشغيل")[:28]
            markup.add(
                types.InlineKeyboardButton(
                    f"▶️ تشغيل: {icon} {title_short}",
                    callback_data=f"play:{idx}"
                )
            )
    markup.add(types.InlineKeyboardButton("🔍 بحث جديد", callback_data="prompt_search"))
    return markup


def send_catalog_list(chat_id, category=None, query=None):
    with db_lock:
        if query:
            nq = normalize_ar(query)
            matches = [
                x for x in catalog
                if nq in normalize_ar(x.get("title", ""))
                or nq in normalize_ar(x.get("genre", ""))
                or nq in normalize_ar(x.get("category", ""))
            ]
            header = f"🔍 <b>نتائج البحث عن:</b> <code>{escape_html(query)}</code>"
        else:
            matches = [x for x in catalog if x.get("category") == category]
            header = "🎬 <b>قائمة الأفلام المتاحة:</b>" if category == "فيلم" else "🧸 <b>قائمة الكرتون المتاحة:</b>"

        snapshot = list(matches)

    if not snapshot:
        bot.send_message(
            chat_id,
            "😕 ملقتش أعمال مطابقة دلوقتي، جرب اسم تاني أو تصفح الأقسام 👇",
            reply_markup=build_main_menu_markup()
        )
        return

    lines = [header, "━━━━━━━━━━━━━━━━━━━━"]
    for i, item in enumerate(snapshot, start=1):
        lines.append(
            f"{i}. <b>{escape_html(item.get('title', 'بدون عنوان'))}</b>\n"
            f"   └ 🎭 {escape_html(item.get('genre', 'متنوع'))} • ⏱ <code>{escape_html(item.get('duration', 'غير محدد'))}</code>"
        )
    lines.append("\nاختار زرار <b>تشغيل</b> تحت العمل اللي عايز تشوفه 👇")

    bot.send_message(
        chat_id,
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=build_results_markup(snapshot)
    )


def send_item_player_card(chat_id, idx):
    with db_lock:
        if idx < 0 or idx >= len(catalog):
            return None
        item = dict(catalog[idx])

    title = escape_html(item.get("title", "بدون عنوان"))
    category = escape_html(item.get("category", "عمل"))
    genre = escape_html(item.get("genre", "متنوع"))
    duration = escape_html(item.get("duration", "غير محدد"))
    desc = escape_html(item.get("desc", "لا يوجد وصف."))
    url = (item.get("url") or "").strip()

    caption = (
        f"{'🎬' if category == 'فيلم' else '🧸'} <b>{title}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>النوع:</b> {category}\n"
        f"• <b>التصنيف:</b> {genre}\n"
        f"• <b>المدة:</b> <code>{duration}</code>\n"
        f"• <b>القصة:</b> {desc}"
    )

    markup = types.InlineKeyboardMarkup()
    if url.startswith("http://") or url.startswith("https://"):
        markup.add(types.InlineKeyboardButton("▶️ مشاهدة / تشغيل الآن", url=url))
    markup.add(types.InlineKeyboardButton("🔍 بحث عن عمل آخر", callback_data="prompt_search"))

    m_type = item.get("media_type", "none")
    m_id = item.get("media_id")

    if m_type == "video" and m_id:
        bot.send_video(chat_id, m_id, caption=caption, parse_mode="HTML", reply_markup=markup)
    elif m_type == "photo" and m_id:
        bot.send_photo(chat_id, m_id, caption=caption, parse_mode="HTML", reply_markup=markup)
    else:
        bot.send_message(chat_id, caption, parse_mode="HTML", reply_markup=markup)

    return item.get("title", "العمل")


@bot.message_handler(commands=["start", "help"])
@bot.message_handler(func=lambda m: bool(m.text and m.text.strip() in ["القائمة", "الاوامر", "الأوامر"]))
def welcome_handler(message):
    text = (
        "🎬 <b>أهلاً بك في بوت الأفلام والكرتون</b> 🧸\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "• اكتب <code>افلام</code> أو <code>كرتون</code> للتصفح\n"
        "• اكتب <code>بحث اسم العمل</code> أو اضغط زر البحث واكتب الاسم\n"
        "• للأدمنز: اكتب <code>اضافة عمل</code> أو <code>حذف عمل</code>"
    )
    bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=build_main_menu_markup())


@bot.message_handler(func=lambda m: bool(m.text and m.text.strip().lower() in ["افلام", "أفلام", "فيلم"]))
def movies_cmd(message):
    send_catalog_list(message.chat.id, category="فيلم")


@bot.message_handler(func=lambda m: bool(m.text and m.text.strip().lower() in ["كرتون", "الكرتون", "انمي", "أنمي"]))
def cartoons_cmd(message):
    send_catalog_list(message.chat.id, category="كرتون")


@bot.message_handler(func=lambda m: bool(m.text and m.text.strip().lower().startswith("بحث ")))
def search_cmd(message):
    query = message.text.strip()[4:].strip()
    if not query:
        bot.send_message(message.chat.id, "اكتب اسم الفيلم أو الكرتون بعد كلمة <code>بحث</code>.", parse_mode="HTML")
        return
    send_catalog_list(message.chat.id, query=query)


@bot.message_handler(func=lambda m: bool(m.text and m.text.strip() == "اضافة عمل"))
def add_item_start(message):
    uid = message.from_user.id if message.from_user else 0
    if not is_admin_in_chat(message.chat.id, uid):
        bot.send_message(message.chat.id, "🚫 إضافة الأعمال متاحة للأدمنز فقط.")
        return

    search_waiting.pop(uid, None)
    deleting_waiting.discard(uid)
    adding_state[uid] = {"step": "category", "chat_id": message.chat.id}
    bot.send_message(
        message.chat.id,
        "➕ <b>إضافة عمل جديد:</b>\nاكتب <code>فيلم</code> أو <code>كرتون</code> (أو <code>/الغاء</code>):",
        parse_mode="HTML"
    )


@bot.message_handler(
    func=lambda m: bool(m.from_user and m.from_user.id in adding_state),
    content_types=["text", "photo", "video"]
)
def add_item_steps(message):
    uid = message.from_user.id
    st = adding_state.get(uid)
    if not st or st["chat_id"] != message.chat.id:
        return

    if message.text and message.text.strip() == "/الغاء":
        del adding_state[uid]
        bot.send_message(message.chat.id, "❎ تم إلغاء الإضافة.")
        return

    step = st["step"]
    if step == "category":
        val = (message.text or "").strip()
        if val not in ["فيلم", "كرتون"]:
            bot.send_message(message.chat.id, "اكتب <code>فيلم</code> أو <code>كرتون</code>.", parse_mode="HTML")
            return
        st["category"] = val
        st["step"] = "title"
        bot.send_message(message.chat.id, "ابعت <b>اسم الفيلم أو الكرتون</b>:", parse_mode="HTML")

    elif step == "title":
        if not message.text or not message.text.strip():
            bot.send_message(message.chat.id, "ابعت اسم واضح.")
            return
        st["title"] = message.text.strip()
        st["step"] = "genre"
        bot.send_message(message.chat.id, "ابعت <b>التصنيف</b> (مثلاً: أكشن / كوميدي):", parse_mode="HTML")

    elif step == "genre":
        st["genre"] = (message.text or "متنوع").strip()
        st["step"] = "duration"
        bot.send_message(message.chat.id, "ابعت <b>المدة</b> (مثلاً: 1h 50m أو <code>غير محدد</code>):", parse_mode="HTML")

    elif step == "duration":
        st["duration"] = (message.text or "غير محدد").strip()
        st["step"] = "desc"
        bot.send_message(message.chat.id, "ابعت <b>ملخص قصير للقصة</b>:", parse_mode="HTML")

    elif step == "desc":
        st["desc"] = (message.text or "لا يوجد وصف.").strip()
        st["step"] = "url"
        bot.send_message(message.chat.id, "ابعت <b>رابط المشاهدة</b> (https://...) أو اكتب <code>بدون</code>:", parse_mode="HTML")

    elif step == "url":
        u = (message.text or "").strip()
        st["url"] = "" if u == "بدون" else u
        st["step"] = "media"
        bot.send_message(message.chat.id, "ابعت <b>فيديو أو صورة بوستر</b>، أو اكتب <code>تخطي</code>:", parse_mode="HTML")

    elif step == "media":
        media_type = "none"
        media_id = None
        if message.content_type == "photo":
            media_type = "photo"
            media_id = message.photo[-1].file_id
        elif message.content_type == "video":
            media_type = "video"
            media_id = message.video.file_id
        elif message.text and message.text.strip() == "تخطي":
            media_type = "none"
            media_id = None
        else:
            bot.send_message(message.chat.id, "ابعت صورة أو فيديو أو اكتب <code>تخطي</code>.", parse_mode="HTML")
            return

        new_item = {
            "title": st["title"],
            "category": st["category"],
            "genre": st["genre"],
            "duration": st["duration"],
            "desc": st["desc"],
            "url": st["url"],
            "media_type": media_type,
            "media_id": media_id,
        }
        with db_lock:
            catalog.append(new_item)
            save_catalog(catalog)

        del adding_state[uid]
        bot.send_message(
            message.chat.id,
            f"✅ تم حفظ ({new_item['category']}): <b>{escape_html(new_item['title'])}</b>!",
            parse_mode="HTML"
        )


@bot.message_handler(func=lambda m: bool(m.text and m.text.strip() == "حذف عمل"))
def delete_item_start(message):
    uid = message.from_user.id if message.from_user else 0
    if not is_admin_in_chat(message.chat.id, uid):
        bot.send_message(message.chat.id, "🚫 حذف الأعمال متاح للأدمنز فقط.")
        return

    deleting_waiting.add(uid)
    bot.send_message(message.chat.id, "🗑 ابعت <b>اسم الفيلم أو الكرتون</b> اللي عايز تحذفه (أو <code>/الغاء</code>):", parse_mode="HTML")


@bot.message_handler(
    func=lambda m: bool(m.from_user and m.from_user.id in deleting_waiting),
    content_types=["text"]
)
def delete_item_process(message):
    uid = message.from_user.id
    deleting_waiting.discard(uid)

    if message.text.strip() == "/الغاء":
        bot.send_message(message.chat.id, "❎ تم إلغاء الحذف.")
        return

    target = normalize_ar(message.text)
    removed_title = None
    with db_lock:
        for i, item in enumerate(catalog):
            if target == normalize_ar(item.get("title", "")) or target in normalize_ar(item.get("title", "")):
                removed_title = catalog.pop(i).get("title")
                save_catalog(catalog)
                break

    if removed_title:
        bot.send_message(message.chat.id, f"🗑 تم حذف: <b>{escape_html(removed_title)}</b>", parse_mode="HTML")
    else:
        bot.send_message(message.chat.id, "⚠️ ملقتش عمل بالاسم ده.")


@bot.message_handler(
    func=lambda m: bool(m.from_user and m.from_user.id in search_waiting),
    content_types=["text"]
)
def waiting_search_handler(message):
    uid = message.from_user.id
    st = search_waiting.get(uid)
    if not st or st["chat_id"] != message.chat.id:
        return
    if time.time() - st["created_at"] > 120:
        search_waiting.pop(uid, None)
        return

    search_waiting.pop(uid, None)
    query = (message.text or "").strip()
    if query:
        send_catalog_list(message.chat.id, query=query)


@bot.callback_query_handler(func=lambda call: bool(call.data and call.data.startswith("cat:")))
def callback_category(call):
    cat = call.data.split(":", 1)[1]
    bot.answer_callback_query(call.id, f"عرض {cat}")
    send_catalog_list(call.message.chat.id, category=cat)


@bot.callback_query_handler(func=lambda call: bool(call.data == "prompt_search"))
def callback_prompt_search(call):
    uid = call.from_user.id if call.from_user else 0
    search_waiting[uid] = {"chat_id": call.message.chat.id, "created_at": time.time()}
    bot.answer_callback_query(call.id, "اكتب اسم الفيلم أو الكرتون ✍️")
    bot.send_message(
        call.message.chat.id,
        "🔍 <b>اكتب دلوقتي اسم الفيلم أو الكرتون اللي بتدور عليه:</b>",
        parse_mode="HTML"
    )


@bot.callback_query_handler(func=lambda call: bool(call.data and call.data.startswith("play:")))
def callback_play(call):
    try:
        idx = int(call.data.split(":", 1)[1])
    except Exception:
        return

    title = send_item_player_card(call.message.chat.id, idx)
    if title is None:
        bot.answer_callback_query(call.id, "العمل ده مش متاح حالياً.", show_alert=True)
        return
    bot.answer_callback_query(call.id, f"▶️ تشغيل: {title[:25]}")


if __name__ == "__main__":
    print("Movies & Cartoons Bot is running...")
    try:
        bot.remove_webhook()
    except Exception:
        pass
    bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=20)
