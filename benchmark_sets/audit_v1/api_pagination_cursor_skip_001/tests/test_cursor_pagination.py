from app.models import Record
from app.pagination import fetch_page


def test_all_records_returned_once_with_duplicate_timestamps():
    records = [
        Record("r1", 100, "a"),
        Record("r2", 100, "b"),
        Record("r3", 100, "c"),
        Record("r4", 200, "d"),
        Record("r5", 300, "e"),
    ]
    seen: list[str] = []
    cursor = None
    while True:
        page, cursor = fetch_page(records, cursor=cursor, limit=2)
        seen.extend(item.id for item in page)
        if cursor is None:
            break
    assert seen == ["r1", "r2", "r3", "r4", "r5"]
