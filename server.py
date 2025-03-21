#!/usr/bin/env python3
from pydantic import BaseModel
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from fastapi.responses import JSONResponse
import uuid
import datetime
import yookassa_api
import sqlite3
from contextlib import closing
from check_for_recurrent import start_recurrent_checker


API_KEY="test_MUPhjN2Ti23BskNgqzAltDiI-21G0KLMncGkrtaxn1I"
SHOP_ID="1055267"
URL="https://rnmgv-5-228-83-118.a.free.pinggy.link" + "/webhook"
payment_processor = yookassa_api.PaymentProcessor(SHOP_ID, API_KEY, URL)


DATABASE_NAME = "payments.db"



app = FastAPI()

# Mock database
with closing(sqlite3.connect(DATABASE_NAME)) as conn:
    conn.execute('''CREATE TABLE IF NOT EXISTS payments
                    (id TEXT PRIMARY KEY,
                    chat_id TEXT,
                    amount REAL,
                    currency TEXT,
                    status TEXT,
                    description TEXT,
                    payment_method_id TEXT,
                    is_recurrent BOOLEAN,
                    refunded BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP
                    );''')

    conn.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                    (payment_method_id TEXT PRIMARY KEY,
                    chat_id TEXT,
                    saved BOOLEAN,
                    last_payment TIMESTAMP,
                    last_error_message TIMESTAMP,
                    started TIMESTAMP,
                    interval INT,
                    amount REAL,
                    currency TEXT,
                    description TEXT
                    );''')
    # interval should be month maybe
    conn.commit()

start_recurrent_checker(payment_processor)

def payments_insert(id, chat_id, price, currency, status,
                    product, payment_method_id, is_recurrent, created_at):
    with closing(sqlite3.connect(DATABASE_NAME)) as conn:
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO payments
            (id, chat_id, amount, currency, status, description,
                payment_method_id, is_recurrent, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (id, chat_id, price, currency, status,
              product, payment_method_id, is_recurrent, created_at
        ))
        conn.commit()



class OrderCreate(BaseModel):
    chat_id: int
    product: str


class OrderRefund(BaseModel):
    chat_id: int
    order_id: str



def get_order_price(product: str) -> float:
    """Replace with real pricing logic"""
    prices = {"Product 1": 100.0, "Product 2": 200.0, "Product 3": 300.0}
    return prices.get(product, 0.0)


# API endpoints
@app.post("/api/create_order")
async def create_order(order_data: OrderCreate):
    price = get_order_price(order_data.product)

    if not (order :=
            payment_processor.create_payment(
                amount=price,
                currency='RUB',
                description=f'product:{order_data.product}',
                chat_id=order_data.chat_id)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Payment failed")

    payments_insert(
        order['id'],
        order_data.chat_id,
        price,
        "RUB",
        order['status'],
        f"product:{order_data.product}",
        None,
        False,
        datetime.datetime.now())
    return JSONResponse(content={"id": order['id'],
                                 "link": order['confirmation_url']},
                        status_code=status.HTTP_200_OK)

def dict_factory(cursor, row):
    fields = [column[0] for column in cursor.description]
    return {key: value for key, value in zip(fields, row)}

@app.get("/api/orders")
async def get_orders(chat_id: int):
    with closing(sqlite3.connect(DATABASE_NAME)) as conn:
        conn.row_factory = dict_factory

        cursor = conn.cursor()

        orders = cursor.execute(
            f"select * from payments where chat_id = {chat_id}")
        orders = orders.fetchall()
    res = []
    for order in orders:
        res.append({"time": order['created_at'], "id": order['id'],
                    "product": order['description'].split(':', 1)[1],
                    'status': order['status']})

    return JSONResponse(res)


@app.post("/api/refund")
async def refund_order(refund_data: OrderRefund):
    with closing(sqlite3.connect(DATABASE_NAME)) as conn:
        conn.row_factory = dict_factory
        cursor = conn.cursor()

        order = cursor.execute(f"select * from payments where id = \"{refund_data.order_id}\"")
        order = order.fetchall()
    order = order[0]
    if not order:
        print("Order not found")
        raise HTTPException(status_code=404, detail="Order not found")
    if str(order["chat_id"]) != str(refund_data.chat_id):
        print("Wrong chat_id???!!!")
        raise HTTPException(status_code=403, detail="Not your order")
    if order["status"] != "succeeded":
        print("status is smth but not succeeded")
        raise HTTPException(status_code=400, detail="Order not eligible for refund")

    result = payment_processor.refund_payment(refund_data.order_id, order['amount'])
    # orders_db[refund_data.order_id]["status"] = "refunded"
    return result

recurrent_payments_db: Dict[str, dict] = {}

class RecurrentPaymentRequest(BaseModel):
    chat_id: int  # ID чата для уведомлений
    amount: float
    interval: int
    product: Optional[str] = None


@app.post("/api/recurrent-payments")
async def create_recurrent_payment(request: RecurrentPaymentRequest):
    try:
        # Валидация данных
        if request.amount <= 0:
            raise ValueError("Сумма должна быть положительной")
        if request.interval < 1:
            raise ValueError("Интервал должен быть не менее 1")

        order = payment_processor.create_payment(
            request.amount,
            'RUB',
            f'product:{request.product}',
            request.chat_id,
            True,
            metadata={'payment_interval': request.interval, 'chat_id': request.chat_id})
        if not order:
            raise HTTPException(status_code=400, detail="Ошибка платежного шлюза")
        return JSONResponse(
            content={
                "id": order['id'],
                "link": order['confirmation_url'],
             # "chat_id": request.chat_id,
            # "next_payment": next_payment,
            # "status": "active"
            })

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=500,
            detail=f"Внутренняя ошибка сервера: {str(e)}"
        )

# if __name__ == "__main__":
#     uvicorn.run(app, host="127.0.0.1", port=5001)
