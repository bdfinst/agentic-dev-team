from datetime import date

import pytest
from billing.history import list_invoices
from tests.fakes import FakeInvoiceRepo, invoice


@pytest.fixture
def repo():
    return FakeInvoiceRepo(
        [invoice("c-1", date(2026, 11, d)) for d in (1, 2, 3)]
    )


def test_first_page_is_newest_first(repo):
    page = list_invoices(repo, "c-1", page=1, page_size=2)
    assert [i.created_at.day for i in page.items] == [3, 2]
    assert page.has_more is True


def test_last_partial_page_has_no_more(repo):
    page = list_invoices(repo, "c-1", page=2, page_size=2)
    assert [i.created_at.day for i in page.items] == [1]
    assert page.has_more is False


def test_page_past_end_is_empty(repo):
    page = list_invoices(repo, "c-1", page=3, page_size=2)
    assert page.items == []
    assert page.has_more is False


@pytest.mark.parametrize("page,size", [(1, 101), (1, 0), (0, 10)])
def test_out_of_range_arguments_raise(repo, page, size):
    with pytest.raises(ValueError):
        list_invoices(repo, "c-1", page=page, page_size=size)
