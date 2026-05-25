from app.models import Record


def fetch_page(
    records: list[Record], *, cursor: int | None, limit: int
) -> tuple[list[Record], int | None]:
    ordered = sorted(records, key=lambda item: item.created_at)
    start = 0
    if cursor is not None:
        for index, item in enumerate(ordered):
            if item.created_at > cursor:
                start = index
                break
        else:
            return [], None
    page = ordered[start : start + limit]
    if not page:
        return [], None
    last = page[-1]
    next_cursor = None if len(page) < limit else last.created_at
    return page, next_cursor
