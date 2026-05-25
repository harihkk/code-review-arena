from consumer.payments import PaymentConsumer


class Ledger:
    def __init__(self):
        self.balance = 0

    def credit(self, _account_id, amount):
        self.balance += amount


def test_duplicate_kafka_delivery_is_idempotent():
    ledger = Ledger()
    consumer = PaymentConsumer(ledger)
    event = {"event_id": "evt-9", "account_id": "acct-1", "amount": 100}
    consumer.handle(event)
    consumer.handle(event)
    assert ledger.balance == 100

