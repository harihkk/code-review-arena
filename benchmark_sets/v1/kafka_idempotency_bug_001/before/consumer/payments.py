class PaymentConsumer:
    def __init__(self, ledger):
        self.ledger = ledger
        self.processed_event_ids = set()

    def handle(self, event):
        if event["event_id"] in self.processed_event_ids:
            return
        self.ledger.credit(event["account_id"], event["amount"])
        self.processed_event_ids.add(event["event_id"])

