from app.events import OrderStatusChanged
from app.projector import OrderProjector


def test_stale_event_does_not_regress_newer_state():
    projector = OrderProjector()
    projector.apply(OrderStatusChanged("o-1", 2, "SHIPPED"))
    projector.apply(OrderStatusChanged("o-1", 1, "PAID"))
    assert projector.state.status == "SHIPPED"
    assert projector.state.version == 2
