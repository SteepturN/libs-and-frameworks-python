#!/usr/bin/env python3
import traceback
import logging
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CopyTextButton
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
    CallbackQueryHandler,
)
import requests
import json

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

API_URL = "http://127.0.0.1:5001/api"

# Состояния диалога
STATE_MAIN = "main"
STATE_PRODUCTS = "products"
STATE_REFUND = "refund"
STATE_RECURRENT_PAYMENTS = "recurrent-payments"
def get_products():
    return ["Product 1", "Product 2", "Product 3"]
def get_recurrent_payments():
    return ["P1", "P2", "P3"]

# Обработка команды отмены
cancel_keyboard = [[KeyboardButton("Главное меню")]]

async def start(update: Update, context: CallbackContext) -> None:
    keyboard = [
        [KeyboardButton("Выбрать продукт")],
        [KeyboardButton("Мои заказы")],
        [KeyboardButton("Вернуть заказ")],
        [KeyboardButton("Начать рекуррентные платежи")]
    ]
    await update.effective_user.send_message(
        "Выберите действие:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard, resize_keyboard=False, one_time_keyboard=True),
    )
    context.user_data['state'] = STATE_MAIN

async def main_state_handler(update: Update, context: CallbackContext) -> None:
    text = update.message.text
    chat_id = update.effective_chat.id
    user_data = context.user_data
    if text == "Выбрать продукт":
        user_data['state'] = STATE_PRODUCTS
        res = await show_products(update, chat_id)
    elif text == "Мои заказы":
        res = await show_orders(update, chat_id)
    elif text == "Вернуть заказ":
        user_data['state'] = STATE_REFUND
        res = await start_refund(update, chat_id)
    elif text == "Начать рекуррентные платежи":
        user_data['state'] = STATE_RECURRENT_PAYMENTS
        res = await show_recurrent_products(update, chat_id)
    else:
        await update.message.reply_text(
            "Неизвестная команда",
            reply_markup=ReplyKeyboardMarkup(
                cancel_keyboard, resize_keyboard=False, one_time_keyboard=True))
        res = False
    if not res:
        return await start(update, context)


async def handle_message(update: Update, context: CallbackContext) -> None:
    text = update.message.text
    user_data = context.user_data
    chat_id = update.effective_chat.id
    try:
        # Инициализация состояния
        if 'state' not in user_data:
            user_data['state'] = STATE_MAIN

        if text == "Главное меню":
            user_data['state'] = STATE_MAIN
            return await start(update, context)

        # Обработка по текущему состоянию
        if user_data['state'] == STATE_MAIN:
            return await main_state_handler(update, context)
        elif user_data['state'] == STATE_PRODUCTS:
            if text not in get_products():
                await update.message.reply_text(
                    "Некорректный выбор продукта",
                    reply_markup=ReplyKeyboardMarkup(
                        cancel_keyboard, resize_keyboard=True))
                return await start(update, context)
            user_data['product'] = text
            user_data['confirmation-type'] = 'product'
            return await get_confirmation(update, f"приобрести продукт {text}")


        elif user_data['state'] == STATE_REFUND:
            if await process_refund(update, chat_id, text):
                return await start(update, context)

        elif user_data['state'] == STATE_RECURRENT_PAYMENTS:
            if text not in get_recurrent_payments():
                await update.message.reply_text(
                    "Некорректный выбор платежа",
                    reply_markup=ReplyKeyboardMarkup(
                        cancel_keyboard, resize_keyboard=True))
                return await start(update, context)
            user_data['recurrent-payment'] = text
            user_data['confirmation-type'] = 'recurrent-payments'
            return await get_confirmation(update, f"подписаться на платежи для {text}")

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        await update.message.reply_text(
            f"Произошла ошибка {e}. Возврат в главное меню",
            reply_markup=ReplyKeyboardMarkup(
                cancel_keyboard, resize_keyboard=False, one_time_keyboard=True))
        return await start(update, context)


async def get_confirmation(update: Update, text) -> bool:
    keyboard = [[InlineKeyboardButton("Yes", callback_data='yes'),
                 InlineKeyboardButton("No", callback_data='no')]]
    await update.message.reply_text(
        f"Вы хотите {text}?",
        reply_markup=InlineKeyboardMarkup(
            keyboard),
    )
    return True


async def show_products(update: Update, chat_id: int) -> bool:
    keyboard = [[KeyboardButton(p)] for p in get_products()]
    await update.message.reply_text(
        "Выберите продукт:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True,
                                         one_time_keyboard=True),
    )
    return True


async def handle_callback(update: Update, context: CallbackContext) -> None:
    option = update.callback_query.data
    chat_id = update.effective_chat.id
    product = context.user_data.get('product', None)
    recurrent_payment = context.user_data.get('recurrent-payment', None)
    order_id = context.user_data.get('order_id', None)
    confirmation_type = context.user_data.get('confirmation-type', None)
    query = update.callback_query
    await query.answer()
    if confirmation_type is not None:
        if confirmation_type == 'product' and option == "yes" and product is not None:
            await query.answer("creating order...")
            if order := await create_order(update, chat_id, product):
                await update.effective_user.send_message(
                    f"Заказ {order['id']} создан!\nВы можете оплатить его по ссылке: {order['link']}",
                )
            else:
                await update.effective_user.send_message(
                    f"Заказ не создан",
                )
            context.user_data['product'] = None

        elif (confirmation_type == 'recurrent-payments' and option == "yes"
              and recurrent_payment is not None):
            await query.answer("creating recurrent payment...")
            if order := await create_recurrent_payment(update, context, recurrent_payment):
                await update.effective_user.send_message(
                    f"Повторяющиеся платежи будут созданы после оплаты заказа" +
                    f" {order['id']}. Ссылка: {order['link']}"
                    # f"✅ Подписка оформлена!\n" +
                    # f"ID: {data['payment_id']}\n" +
                    # f"Следующий платеж: {data['next_payment']}"
                )
            else:
                await update.effective_user.send_message(
                    f"Заказ не создан",
                )
            context.user_data['product'] = None
        context.user_data['confirmation-type'] = None
    elif 'get' in option.__dir__() and option.get('type', None) == "refund":
        await process_refund(update, chat_id, option['order_id'])
    elif option == "start":
        await query.answer("to the start it is")

    await start(update, context)


async def create_recurrent_payment(update: Update, context: CallbackContext, product: str) -> bool:
    try:
        chat_id = update.effective_chat.id
        # Формирование запроса к API
        payload = {
            "chat_id": chat_id,
            "amount": 200,
            "interval": 100,  # Фиксированный интервал для примера
            "product": product,
        }

        # Вызов API для создания рекуррентного платежа
        response = requests.post(
            f"{API_URL}/recurrent-payments",
            json=payload
        )
        if response.status_code == 200:
            order = response.json()
            return order

        error = response.text
        await update.effective_user.send_message(f"Ошибка создания подписки: {error}")

    except Exception as e:
        await update.effective_user.send_message(f"Ошибка обработки запроса: {e}")
        logger.error(f"Unexpected error: {traceback.format_exception(e)}")
    return False


async def create_order(update: Update, chat_id: int, product: str) -> bool:
    try:
        response = requests.post(
            f"{API_URL}/create_order", json={"chat_id": chat_id, "product": product}
        )
        
        if response.status_code == 200:
            return response.json()

    except requests.exceptions.RequestException as e:
        await update.effective_user.send_message(f"Ошибка соединения с сервером {e}")
    return False

async def show_recurrent_products(update: Update, chat_id: int) -> bool:
    keyboard = [[KeyboardButton(p)] for p in get_recurrent_payments()]
    await update.effective_user.send_message(
        "Выберите рекуррентный платёж:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True,
                                         one_time_keyboard=True),
    )
    return True




async def show_orders(update: Update, chat_id: int) -> bool:
    try:
        response = requests.get(f"{API_URL}/orders?chat_id={chat_id}")
        if response.status_code != 200:
            await update.effective_user.send_message(
                "Заказов нет")
            return False

        orders = response.json()
        if not orders:
            await update.message.reply_text(
                "Заказов нет")
            return False

        await update.message.reply_text("Ваши заказы:")
        for order in orders:
            msg = (
                f"time: {order['time']}\nid: {order['id']}:\nproduct: " +
                f"{order['product']}\nstatus: {order['status']}"
            )
            button = [
                [InlineKeyboardButton(
                    text=f"copy id",
                    copy_text=CopyTextButton(order['id']))],
                [InlineKeyboardButton(
                    text=f"REFUND",
                    callback_data={'type': "refund", 'order_id': order['id']})]
            ]
            if order['status'] != "succeeded":
                button.pop()
            await update.message.reply_text(
                msg, reply_markup=InlineKeyboardMarkup(button))
    except requests.exceptions.RequestException as e:
        await update.message.reply_text(f"Ошибка получения заказов {e}")
    return False


async def start_refund(update: Update, chat_id: int) -> bool:
    try:
        response = requests.get(f"{API_URL}/orders?chat_id={chat_id}")
        if response.status_code == 200:
            refundable = [o for o in response.json() if o["status"] == "succeeded"]
            if refundable:
                keyboard = [[KeyboardButton(f"{o['id']}")] for o in refundable]
                await update.message.reply_text(
                    "Выберите заказ для возврата:",
                    reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
                )
                return True
            else:
                await update.message.reply_text("Нет доступных заказов для возврата")
    except requests.exceptions.RequestException as e:
        await update.message.reply_text(f"Ошибка получения заказов {e}")
    return False

async def process_refund(update: Update, chat_id: int, order_id: str) -> bool:
    try:
        response = requests.post(
            f"{API_URL}/refund", json={"chat_id": chat_id, "order_id": order_id}
        )
        if response.status_code == 200:
            await update.effective_user.send_message(f"Возврат для заказа {order_id} запущен")
            return True
        else:
            await update.effective_user.send_message(f"Ошибка возврата {response.json()['detail']}")
    except requests.exceptions.RequestException as e:
        await update.effective_user.send_message(f"Ошибка соединения с сервером {e}")
    return False


def main() -> None:
    application = (
        Application.builder()
        .token("7567195140:AAHAFnyTM9V5s7A5sQYiOcv5B_GLl1CF-HQ")
        .arbitrary_callback_data(True)
        .build()
    )
    application.add_handler(
        CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND,
                       handle_message)
    )
    application.add_handler(
        CallbackQueryHandler(handle_callback)
    )
    application.run_polling()


if __name__ == "__main__":
    main()
