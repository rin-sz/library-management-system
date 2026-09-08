from django.contrib.auth.decorators import permission_required, login_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db.models import Count, Q
from django.shortcuts import render
from django.utils import timezone
from django.views.generic import ListView
from django.urls import reverse

from books.models import Book, BookItem, Category, Location
from loan.models import (
    Loan,
    Reservation,
    LoanStatus,
    ReservationStatus,
)


# Create your views here.
def _get_loan_stats(today):
    return Loan.objects.aggregate(
        borrowed_count=Count(
            "id",
            filter=Q(status=LoanStatus.BORROWED),
        ),
        overdue_count=Count(
            "id",
            filter=Q(
                status=LoanStatus.BORROWED,
                due_date__lt=today,
            ),
        ),
    )


def _get_reservation_stats():
    return Reservation.objects.aggregate(
        waiting_reservation_count=Count(
            "id",
            filter=Q(status=ReservationStatus.WAITING),
        ),
        ready_reservation_count=Count(
            "id",
            filter=Q(status=ReservationStatus.READY),
        ),
    )


@login_required
@permission_required("books.view_book", raise_exception=True)
def dashboard_view(request):
    today = timezone.localdate()
    loan_stats = _get_loan_stats(today)
    reservation_stats = _get_reservation_stats()

    context = {
        "library_stats": [
            {
                "label": "書誌情報",
                "value": Book.objects.count(),
                "unit": "件",
                "description": "登録されている書誌情報",
                "url": reverse("management:book_list"),
            },
            {
                "label": "蔵書",
                "value": BookItem.objects.count(),
                "unit": "冊",
                "description": "登録されている蔵書",
            },
            {
                "label": "保管場所",
                "value": Location.objects.count(),
                "unit": "件",
                "description": "登録されている保管場所",
            },
            {
                "label": "カテゴリ",
                "value": Category.objects.count(),
                "unit": "件",
                "description": "登録されているカテゴリ",
            },
        ],
        "usage_stats": [
            {
                "label": "現在貸出中",
                "value": loan_stats["borrowed_count"],
                "unit": "件",
                "description": "現在貸し出されている蔵書",
                "is_alert": False,
            },
            {
                "label": "返却期限超過",
                "value": loan_stats["overdue_count"],
                "unit": "件",
                "description": "返却期限を過ぎている貸出",
                "is_alert": loan_stats["overdue_count"] > 0,
            },
            {
                "label": "予約待ち",
                "value": reservation_stats["waiting_reservation_count"],
                "unit": "件",
                "description": "順番待ちの予約",
                "is_alert": False,
            },
            {
                "label": "取り置き中",
                "value": reservation_stats["ready_reservation_count"],
                "unit": "件",
                "description": "受取準備が完了している予約",
                "is_alert": False,
            },
        ],
    }
    return render(
        request,
        "management/dashboard.html",
        context,
    )


class BookListView(PermissionRequiredMixin, ListView):
    model = Book
    template_name = "management/books/list.html"
    paginate_by = 20
    permission_required = "books.view_book"
    raise_exception = True
    ordering = ["title"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_range"] = context["page_obj"].paginator.get_elided_page_range(
            number=context["page_obj"].number,
            on_each_side=2,
            on_ends=1,
        )
        return context
