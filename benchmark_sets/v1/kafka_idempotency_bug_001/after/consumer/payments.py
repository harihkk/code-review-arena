class PaymentConsumer:
    def __init__(self, ledger):
        self.ledger = ledger

    def handle(self, event):
        self.ledger.credit(event["account_id"], event["amount"])

