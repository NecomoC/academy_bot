import logging
import html
import re
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler, CallbackQueryHandler
)
import os
# ========== НАСТРОЙКИ ==========

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID"))

if not BOT_TOKEN or not ADMIN_CHAT_ID:
    raise ValueError("Не заданы переменные окружения BOT_TOKEN или ADMIN_CHAT_ID")
# Список направлений теперь вынесен в конфигурацию (легко расширять)
DIRECTIONS = [
    ("🎓 ВУЗ", "ВУЗ"),
    ("📚 Колледж", "Колледж"),
    ("🏛 Академия", "Академия")
]

# Этапы диалога
DIRECTION, PHONE = range(2)

# Настройка логирования: вывод в консоль и в файл
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ========== СТАРТ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # Очищаем данные прошлого диалога
    context.user_data.clear()
    # Сохраняем имя (если пустое, используем username или "Пользователь")
    name = user.full_name or (user.username or "Пользователь")
    context.user_data["name"] = name

    # Формируем inline-клавиатуру из списка DIRECTIONS
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(text, callback_data=data)] for text, data in DIRECTIONS
    ])

    await update.message.reply_text(
        f"👋 Привет, *{html.escape(user.first_name)}*!\n\n"
        f"Добро пожаловать в *Компьютерную Академию TOP* 🎓\n\n"
        f"Мы готовим востребованных IT-специалистов по современным программам.\n\n"
        f"Пожалуйста, выберите направление, которое вас интересует:",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    return DIRECTION


# ========== ВЫБОР НАПРАВЛЕНИЯ ==========
async def direction_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    direction = query.data
    context.user_data["direction"] = direction

    # Убираем inline-кнопки и подтверждаем выбор
    await query.edit_message_text(
        f"✅ Вы выбрали: *{html.escape(direction)}*\n\n"
        f"Отлично! Теперь, пожалуйста, поделитесь своим номером телефона, "
        f"чтобы наш менеджер мог связаться с вами 📞",
        parse_mode="HTML"
    )

    # Создаём клавиатуру с кнопкой "Отправить номер" и кнопкой "Назад"
    phone_keyboard = ReplyKeyboardMarkup(
        [
            [KeyboardButton("📱 Отправить мой номер", request_contact=True)],
            [KeyboardButton("🔙 Назад к выбору направления")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False  # Не убираем автоматически, чтобы можно было вернуться
    )

    await query.message.reply_text(
        "Нажмите кнопку ниже или введите номер вручную в формате *+7XXXXXXXXXX*:",
        parse_mode="HTML",
        reply_markup=phone_keyboard
    )
    return PHONE


# ========== ОБРАБОТКА КНОПКИ "НАЗАД" ==========
async def back_to_directions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возвращает пользователя к выбору направления."""
    # Показываем снова inline-клавиатуру с направлениями
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(text, callback_data=data)] for text, data in DIRECTIONS
    ])
    await update.message.reply_text(
        "Пожалуйста, выберите направление:",
        reply_markup=keyboard
    )
    # Удаляем старую reply-клавиатуру, чтобы не мешала
    await update.message.reply_text(
        "⬆️ Выберите направление выше.",
        reply_markup=ReplyKeyboardRemove()
    )
    return DIRECTION


# ========== ПОЛУЧЕНИЕ ТЕЛЕФОНА ==========
async def phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text

    # Если нажата кнопка "Назад"
    if text and text == "🔙 Назад к выбору направления":
        return await back_to_directions(update, context)

    # Получаем номер — через контакт или текст
    if update.message.contact:
        phone = update.message.contact.phone_number
        if not phone.startswith("+"):
            phone = "+" + phone
        # Валидируем и контактный номер (на всякий случай)
        if not validate_phone(phone):
            await update.message.reply_text(
                "⚠️ Полученный номер имеет неверный формат. Пожалуйста, введите номер вручную.",
                parse_mode="HTML"
            )
            return PHONE
    else:
        phone = text.strip()
        if not validate_phone(phone):
            await update.message.reply_text(
                "⚠️ Пожалуйста, введите корректный номер телефона в формате *+7XXXXXXXXXX*\n"
                "Или воспользуйтесь кнопкой «Отправить мой номер».",
                parse_mode="HTML"
            )
            # Оставляем клавиатуру, чтобы пользователь мог попробовать снова
            return PHONE

    context.user_data["phone"] = phone

    # Убираем reply-клавиатуру
    await update.message.reply_text(
        "✅ *Спасибо! Ваша заявка принята.*\n\n"
        "Наш менеджер свяжется с вами в ближайшее время 🚀\n\n"
        "Если у вас есть вопросы — напишите нам:\n"
        "📌 <a href='https://volgograd.top-academy.ru/'>Сайт Академии TOP</a>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )

    # Отправляем данные в чат администраторов (и дублируем в лог-файл)
    await send_to_admin(context, user, context.user_data)
    logger.info(f"Заявка от {user.id} сохранена: {context.user_data}")

    return ConversationHandler.END


# ========== ВАЛИДАЦИЯ ТЕЛЕФОНА (улучшенная) ==========
def validate_phone(phone: str) -> bool:
    # Удаляем все пробелы, дефисы, скобки
    cleaned = re.sub(r"[\s\-\(\)]", "", phone)
    # Допустимые форматы: +7xxxxxxxxxx, 8xxxxxxxxxx, 7xxxxxxxxxx (ровно 11 цифр после + или без)
    # Также может быть 10 цифр (без кода) — тогда считаем российским и добавляем +7? Но лучше требовать полный.
    # Для простоты разрешим: начинается с +7 или 8 или 7 и содержит ровно 11 цифр (включая код)
    pattern = r"^(\+7|8|7)?\d{10}$"
    # Если номер начинается с 7 или 8, то после него должно быть 10 цифр = всего 11
    # Но если уже есть +7, то после него 10 цифр = 12 символов с +.
    # Упростим: проверяем, что после удаления мусора остались только цифры и возможно один +
    digits = re.sub(r"[^\d]", "", cleaned)  # оставляем только цифры
    if cleaned.startswith("+"):
        # если есть +, то должно быть ровно 12 символов: + и 11 цифр
        if len(cleaned) == 12 and digits == cleaned[1:] and len(digits) == 11:
            return True
    else:
        # без + должно быть ровно 11 цифр
        if len(digits) == 11:
            return True
    return False


# ========== ОТПРАВКА В ЧАТ АДМИНИСТРАТОРОВ ==========
async def send_to_admin(context: ContextTypes.DEFAULT_TYPE, user, data: dict):
    username = f"@{user.username}" if user.username else "нет username"
    # Экранируем все пользовательские данные для HTML
    name = html.escape(data.get('name', '—'))
    direction = html.escape(data.get('direction', '—'))
    phone = html.escape(data.get('phone', '—'))
    user_id = user.id
    username_escaped = html.escape(username)

    message = (
        "🔔 <b>Новая заявка из Telegram-бота!</b>\n"
        "─────────────────────\n"
        f"👤 <b>Имя:</b> {name}\n"
        f"🆔 <b>Telegram ID:</b> <code>{user_id}</code>\n"
        f"🔗 <b>Username:</b> {username_escaped}\n"
        f"📚 <b>Направление:</b> {direction}\n"
        f"📞 <b>Телефон:</b> <code>{phone}</code>\n"
        "─────────────────────"
    )
    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=message,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке в чат администраторов: {e}")


# ========== ОТМЕНА ==========
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Диалог отменён. Напишите /start чтобы начать заново.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


# ========== НЕИЗВЕСТНЫЕ СООБЩЕНИЯ ==========
async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Пожалуйста, используйте /start для начала работы с ботом 🙂"
    )


# ========== ЗАПУСК БОТА ==========
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            DIRECTION: [CallbackQueryHandler(direction_handler)],
            PHONE: [
                MessageHandler(filters.CONTACT, phone_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, phone_handler),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start)  # /start теперь работает и внутри диалога
        ],
        allow_reentry=True  # Разрешаем перезапуск диалога через /start
    )

    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.ALL, unknown))

    # При старте проверим доступность админ-чата (отправим уведомление о запуске)
    async def send_startup_notification(app: Application):
        try:
            await app.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text="<b>🤖 Бот запущен и готов к работе!</b>",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить сообщение в админ-чат при запуске: {e}")

    application.post_init = send_startup_notification

    logger.info("Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":

    main()
