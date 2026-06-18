from consumer.payments import PaymentConsumer


class Ledger:
    def __init__(self):
        self.balance = 0

    def credit(self, _account_id, amount):
        self.balance += amount


def test_repeated_delivery_credits_once():
    ledger = Ledger()
    consumer = PaymentConsumer(ledger)
    event = {"event_id": "evt-42", "account_id": "acct-1", "amount": 100}
    consumer.handle(event)
    consumer.handle(event)
    assert ledger.balance == 100
