import yookassa
from yookassa import Configuration, Payment, Refund, Webhook
import uuid
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PaymentProcessor:
    def __init__(self, shop_id: str, api_key: str, base_url: str):
        Configuration.configure(shop_id, api_key)
        self.base_url = base_url
        # self.setup_webhooks()

    def setup_webhooks(self):
        """Configure required webhooks for payment notifications"""
        webhook_events = [
            ("payment.succeeded", f"{self.base_url}"),
            ("payment.canceled", f"{self.base_url}"),
            ("refund.succeeded", f"{self.base_url}"),
        ]

        for event, url in webhook_events:
            try:
                Webhook.add({"event": event, "url": url})
                logger.info(f"Webhook configured for {event} at {url}")
            except Exception as e:
                logger.error(f"Failed to configure webhook: {str(e)}")

    def create_payment(
            self,
            amount: float,
            currency: str,
            description: str,
            chat_id: str,
            start_recurrent: bool = False,
            payment_method_id: str = None, # after recurrent this is saved
            return_url: str = None,
            metadata=None,
    ):
        """Create payment with optional recurrent setup"""
        idempotence_key = str(uuid.uuid4())
        payload = {
            "amount": {
                "value": f"{amount:.2f}",
                "currency": currency
            },
            "description": description,
            "merchant_customer_id": chat_id,
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": return_url or self.base_url
            },
        }
        if metadata:
            payload["metadata"] = metadata

        if start_recurrent:
            payload["save_payment_method"] = True

        if payment_method_id:
            payload["payment_method_id"] = payment_method_id
            payload.pop("confirmation")

        try:
            payment = Payment.create(payload, idempotence_key)
            logger.info(f"Created payment {payment.json()}")
            return {
                "id": payment.id,
                "status": payment.status,
                "confirmation_url": payment.confirmation.confirmation_url if not payment_method_id else None,
                "payment_method_id": payment.payment_method.id if payment.payment_method else None
            }
        except Exception as e:
            logger.error(f"Payment creation failed: {str(e)}")
            return False

    def refund_payment(
        self,
        payment_id: str,
        amount: float,
        currency: str = "RUB"
    ):
        """Create refund for existing payment"""
        idempotence_key = str(uuid.uuid4())
        payload = {
            "payment_id": payment_id,
            "amount": {
                "value": f"{amount:.2f}",
                "currency": currency
            }
        }

        try:
            refund = Refund.create(payload, idempotence_key)
            logger.info(f"Created refund {refund.id}")
            return {
                "id": refund.id,
                "payment_id": refund.payment_id,
                "status": refund.status,
                "amount": refund.amount.value
            }
        except Exception as e:
            logger.error(f"Refund creation failed: {str(e)}")
            raise

# Example usage
if __name__ == '__main__':
    # Configuration
    SHOP_ID = "your_shop_id"
    API_KEY = "your_api_key"
    BASE_URL = "https://yourdomain.com"

    processor = PaymentProcessor(SHOP_ID, API_KEY, BASE_URL)

    # Create initial payment
    try:
        payment = processor.create_payment(
            amount=200.00,
            currency="RUB",
            description="Order No. 72",
            customer_id="user_12345",
            recurrent=True,
            return_url=f"{BASE_URL}/return"
        )
        print(f"Payment created: {payment}")
    except Exception as e:
        print(f"Payment failed: {str(e)}")

    # Create recurrent payment (example)
    try:
        recurrent_payment = processor.create_recurrent_payment(
            amount=200.00,
            currency="RUB",
            description="Recurrent payment for Order No. 72",
            customer_id="user_12345",
            payment_method_id="saved_payment_method_id"
        )
        print(f"Recurrent payment created: {recurrent_payment}")
    except Exception as e:
        print(f"Recurrent payment failed: {str(e)}")

    # Create refund (example)
    try:
        refund = processor.refund_payment(
            payment_id="payment_id_from_previous_transaction",
            amount=200.00
        )
        print(f"Refund created: {refund}")
    except Exception as e:
        print(f"Refund failed: {str(e)}")
