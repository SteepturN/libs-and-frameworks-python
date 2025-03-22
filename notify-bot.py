from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
import traceback
import datetime
import logging
from telegram import Bot
from typing import Dict, Any
from pprint import pprint
import bd
import os
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

app = FastAPI()
logger = logging.getLogger(__name__)

# Database setup


class WebhookData(BaseModel):
    type: str
    event: str
    object: Dict[str, Any]

def save_payment_d(payment_data: Dict[str, Any]):
    try:
        payment_method = payment_data.get('payment_method', {})
        if not (chat_id := payment_data.get('merchant_customer_id')):
            chat_id = payment_data.get('metadata', {}).get('chat_id')
        bd.payments_insert(
            id=payment_data.get('id'),
            chat_id=chat_id,
            price=payment_data.get('amount', {}).get('value'),
            currency=payment_data.get('amount', {}).get('currency'),
            status=payment_data.get('status'),
            product=payment_data.get('description'),
            payment_method_id=payment_method.get('id'),
            is_recurrent=payment_method.get('saved', False),
            created_at=datetime.datetime.now().isoformat()
        )
        if payment_method.get('saved'):
            locate = bd.get_orders(
                search_name='payment_method_id',
                search_id=payment_method.get('id'),
                table='subscriptions')
            if not locate:
                bd.subscriptions_insert(
                    payment_method_id=payment_method.get('id'),
                    chat_id=chat_id,
                    saved=True,
                    last_payment=datetime.datetime.now().isoformat(),
                    last_error_message=None,
                    started=datetime.datetime.now().isoformat(),
                    interval=payment_data.get('metadata', {}).get('payment_interval', 60),
                    amount=payment_data.get('amount', {}).get('value'),
                    currency=payment_data.get('amount', {}).get('currency'),
                    description=payment_data.get('description'),
                )
                print('saved recurrent added to database')
            else:
                print('saved recurrent already in database')
    except Exception as e:
        logger.error(f"Database error: {traceback.format_exception(e)}")

def update_refund_status(payment_id: str):
    try:
        bd.update_set_refund_status(payment_id)
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
            payment_id = payment_data.get('payment_id')
            chat_id = bd.get_orders(search_name='id',
                                    search_id=payment_id,
                                    num='one')['chat_id']
        else:
            logger.error(f"chat id was received: {chat_id} {webhook_data}")
        print(f'chat id: {chat_id}')
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
        logger.error(f"Webhook processing error: {traceback.format_exception(e)}")
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
