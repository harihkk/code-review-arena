from app.paging import page_count


def test_partial_final_page_is_counted():
    assert page_count(10, 3) == 4


def test_exact_multiple_has_no_extra_page():
    assert page_count(9, 3) == 3


def test_single_partial_page():
    assert page_count(1, 20) == 1


def test_no_items_means_no_pages():
    assert page_count(0, 20) == 0
