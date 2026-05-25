from app.models import Record


def fetch_page(
    records: list[Record], *, cursor: tuple[int, str] | None, limit: int
) -> tuple[list[Record], tuple[int, str] | None]:
    ordered = sorted(records, key=lambda item: (item.created_at, item.id))
    start = 0
    if cursor is not None:
        created_at, record_id = cursor
        for index, item in enumerate(ordered):
            if (item.created_at, item.id) > (created_at, record_id):
                start = index
                break
        else:
            return [], None
    page = ordered[start : start + limit]
    if not page:
        return [], None
    last = page[-1]
    next_cursor = None if len(page) < limit else (last.created_at, last.id)
    return page, next_cursor
