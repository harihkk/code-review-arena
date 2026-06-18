def page_count(item_total: int, per_page: int) -> int:
    """Number of pages needed to show ``item_total`` items at ``per_page`` each."""
    return (item_total + per_page - 1) // per_page
