from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
import datetime
import logging
import sqlite3
from contextlib import closing
from telegram import Bot
from typing import Dict, Any
from pprint import pprint
app = FastAPI()
logger = logging.getLogger(__name__)
TELEGRAM_BOT_TOKEN = "7567195140:AAHAFnyTM9V5s7A5sQYiOcv5B_GLl1CF-HQ"

# Database setup
DATABASE_NAME = "payments.db"


class WebhookData(BaseModel):
    type: str
    event: str
    object: Dict[str, Any]

def save_payment_data(payment_data: Dict[str, Any]):
    try:
        with closing(sqlite3.connect(DATABASE_NAME)) as conn:
            cursor = conn.cursor()
            payment_method = payment_data.get('payment_method', {})
            num = cursor.execute('select count(*) from payments')
            print('payments num: ', num.fetchone())

            num = cursor.execute('select * from payments')
            print('all payments: ')
            pprint(num.fetchall())

            if not (chat_id := payment_data.get('merchant_customer_id')):
                chat_id = payment_data.get('metadata', {}).get('chat_id')
            cursor.execute('''
                INSERT OR REPLACE INTO payments
                (id, chat_id, amount, currency, status, description,
                 payment_method_id, is_recurrent, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                payment_data.get('id'),
                chat_id,
                payment_data.get('amount', {}).get('value'),
                payment_data.get('amount', {}).get('currency'),
                payment_data.get('status'),
                payment_data.get('description'),
                payment_method.get('id'),
                payment_method.get('saved', False),
                datetime.datetime.now().isoformat()
            ))

            if payment_method.get('saved'):
                locate = cursor.execute(
                    f'select * from subscriptions where payment_method_id = "{payment_method.get('id')}"')
                if not locate.fetchone():
                    cursor.execute('''
                        INSERT OR REPLACE INTO subscriptions
                        (payment_method_id, chat_id, saved, last_payment,
                        last_error_message, started, interval, amount,
                        currency, description)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        payment_method.get('id'),
                        chat_id,
                        True,
                        datetime.datetime.now().isoformat(),
                        None,
                        datetime.datetime.now().isoformat(),
                        payment_data.get('metadata', {}).get('payment_interval', 60),
                        payment_data.get('amount', {}).get('value'),
                        payment_data.get('amount', {}).get('currency'),
                        payment_data.get('description'),
                    ))
                    print('saved recurrent added to database')
                else:
                    print('saved recurrent already in database')
            conn.commit()
    except Exception as e:
        logger.error(f"Database error: {str(e)}")

def update_refund_status(payment_id: str):
    try:
        with closing(sqlite3.connect(DATABASE_NAME)) as conn:
            conn.execute('''
                UPDATE payments
                SET status = 'refunded'
                WHERE id = ?
            ''', (payment_id,))
            conn.commit()
    except Exception as e:
        logger.error(f"Refund update error: {str(e)}")

def handle_payment_status(event_type: str, payment_data: Dict[str, Any]) -> str:
    chat_id = payment_data.get('merchant_customer_id')
    amount = payment_data.get('amount', {})
    payment_id = payment_data.get('id')
    description = payment_data.get('description', '')
    payment_method = payment_data.get('payment_method', {})

    status_messages = {
        "payment.succeeded": "✅ Платеж успешно завершен",
        "payment.waiting_for_capture": "🕒 Ожидает подтверждения",
        "payment.canceled": "❌ Платеж отменен",
        "refund.succeeded": "🔄 Возврат выполнен"
    }

    base_msg = status_messages.get(event_type, f"⚠️ Неизвестный статус: {event_type}")
    amount_str = f"{amount.get('value', 'N/A')} {amount.get('currency', '')}"

    message = (
        f"{base_msg}\nID: {payment_id}\n"
        f"Сумма: {amount_str}\nОписание: {description}\n"
        f"Время: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    if payment_method.get('saved'):
        message += "\n\n💳 Способ оплаты сохранен для рекуррентных платежей"

    return message, chat_id


@app.post("/webhook")
async def process_webhook(request: Request):
    try:
        webhook_data = await request.json()
        logger.info(f"Received webhook: {webhook_data}")

        # Immediate response to prevent retries
        response = {"status": "received"}

        event_type = webhook_data.get('event')
        payment_data = webhook_data.get('object', {})

        # Save/update payment data
        try:
            if event_type == "refund.succeeded":
                update_refund_status(payment_data.get('payment_id'))
            elif event_type == "payment.succeeded":
                save_payment_data(payment_data)
        except Exception as e:
            logger.error(f"Data processing error: {str(e)}")

        # Generate and send notification
        message, chat_id = handle_payment_status(event_type, payment_data)
        if chat_id is None:
            chat_id = payment_data.get('metadata', {}).get('chat_id')
        if chat_id is None:
            logger.error(f"chat id is missing: {chat_id} {webhook_data}")
            with closing(sqlite3.connect(DATABASE_NAME)) as conn:
                cursor = conn.cursor()
                payment_id = payment_data.get('payment_id')
                # payment_id = payment_data.get('id')
                cursor.execute(f"select chat_id from payments where id = \"{payment_id}\"")
                chat_id = cursor.fetchone()[0]
        else:
            logger.error(f"chat id was received: {chat_id} {webhook_data}")

        try:
            async with Bot(TELEGRAM_BOT_TOKEN) as bot:
                await bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Telegram send error: {str(e)}")
        return response

    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")
        return {"status": "error", "details": str(e)}






class NotificationRequest(BaseModel):
    chat_id: int  # Telegram chat_id
    message_type: str  # success/failure/retry
    details: dict = None  # Optional additional data


def construct_message(message_type: str, details: dict) -> str:
    now = datetime.datetime.now()
    if message_type == "success":
        return f"✅ {now} Payment succeeded! Amount: {details.get("amount")}"
    elif message_type == "failure":
        return f"❌ {now} Payment failed! Reason: {details.get("error", "Unknown error")}"
    elif message_type == "retry":
        return f"🔄 {now} Retrying payment."
    return "⚠️ Unknown payment status"

@app.post("/send-notification")
async def send_notification(request: NotificationRequest):
    try:
        message = construct_message(request.message_type, request.details or {})
        async with Bot(TELEGRAM_BOT_TOKEN) as bot:
            await bot.send_message(chat_id=request.chat_id, text=message)
        return {"status": "Message sent"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
