#!/usr/bin/env python3

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List
import uuid
import uvicorn

app = FastAPI()

# Mock database
orders_db: Dict[str, dict] = {}


class OrderCreate(BaseModel):
    user_id: int
    product: str


class OrderRefund(BaseModel):
    user_id: int
    order_id: str


# Payment service mock
def process_payment(user_id: int, amount: float) -> bool:
    """Replace this with real payment processing"""
    return True


def get_order_price(product: str) -> float:
    """Replace with real pricing logic"""
    prices = {"Product 1": 100.0, "Product 2": 200.0, "Product 3": 300.0}
    return prices.get(product, 0.0)


# API endpoints
@app.post("/api/create_order")
async def create_order(order_data: OrderCreate):
    order_id = str(uuid.uuid4())
    price = get_order_price(order_data.product)

    if not process_payment(order_data.user_id, price):
        raise HTTPException(status_code=400, detail="Payment failed")

    orders_db[order_id] = {
        "id": order_id,
        "user_id": order_data.user_id,
        "product": order_data.product,
        "status": "paid",
        "price": price,
    }
    return {"order_id": order_id}


@app.get("/api/orders")
async def get_orders(user_id: int):
    return [order for order in orders_db.values() if order["user_id"] == user_id]


@app.post("/api/refund")
async def refund_order(refund_data: OrderRefund):
    order = orders_db.get(refund_data.order_id)

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["user_id"] != refund_data.user_id:
        raise HTTPException(status_code=403, detail="Not your order")
    if order["status"] != "paid":
        raise HTTPException(status_code=400, detail="Order not eligible for refund")

    orders_db[refund_data.order_id]["status"] = "refunded"
    return {"status": "refund_processed"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5001)
