from django.contrib.auth.decorators import permission_required, login_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib import messages
from django.db.models import Count, Q
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.generic import ListView
from django.views.decorators.http import require_POST
from django.urls import reverse
from .openbd import get_book_by_isbn, OpenBDError
from .forms import BookRegisterForm

from books.models import Book, BookItem, Category, Location
from loan.models import (
    Loan,
    Reservation,
    LoanStatus,
    ReservationStatus,
)

from .openbd import get_book_by_isbn, OpenBDError
from .forms import BookRegisterForm, BookItemAddForm
from .service import increase_stock


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
                "value": BookItem.objects.filter(
                    status__in=[
                        BookItem.Status.AVAILABLE,
                        BookItem.Status.LOANED,
                        BookItem.Status.RESERVED,
                    ]
                ).count(),
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


def _build_stock_summary(book: Book):
    """指定したBookの、保管場所ごとの蔵書数一覧を [(location名, 冊数), ...] で返す。"""
    summary = (
        book.items.exclude(status=BookItem.Status.DISPOSED)
        .values("location__name")
        .annotate(count=Count("id"))
        .order_by("location__name")
    )
    return [(row["location__name"], row["count"]) for row in summary]


def _get_existing_location(book: Book) -> Location | None:
    """bookの蔵書が現在ある保管場所を返す(在庫がなければNone)。

    廃棄済み(DISPOSED)状態は除外する。同一本は単一locationにのみ存在する前提。
    """
    item = (
        BookItem.objects.filter(book=book)
        .exclude(status=BookItem.Status.DISPOSED)
        .select_related("location")
        .first()
    )
    return item.location if item else None


@login_required
@permission_required("books.add_book", raise_exception=True)
def book_register_view(request):
    """ISBN入力画面(初期表示)"""
    form = BookRegisterForm()
    return render(request, "management/books/register.html", {"form": form})


@login_required
@permission_required("books.add_book", raise_exception=True)
@require_POST
def book_isbn_search_view(request):
    """HTMXから呼ばれる、ISBN検索の部分レスポンス"""
    is_htmx = request.headers.get("HX-Request") == "true"
    isbn = request.POST.get("isbn", "").strip().replace("-", "")

    if not isbn:
        return render(
            request,
            "management/books/partials/search_not_found.html",
            {"message": "ISBNを入力してください。"},
        )

    # 既に登録済みのISBNであれば openBD には問い合わせず、
    # 既存Bookへの蔵書追加フローへ振り分ける
    existing_book = Book.objects.filter(isbn=isbn).first()
    if existing_book:
        return render(
            request,
            "management/books/partials/search_result_existing.html",
            {
                "book": existing_book,
                "stock_summary": _build_stock_summary(existing_book),
                "form": BookItemAddForm(),
            },
        )

    try:
        book_data = get_book_by_isbn(isbn)
    except OpenBDError:
        error_msg = "openBDへの接続に失敗しました。時間をおいて再度お試しください。"
        if is_htmx:
            response = render(
                request,
                "partials/message_alert.html",
                {"message": error_msg, "tags": "danger"},
            )
            response["HX-Retarget"] = "#message-container"
            response["HX-Reswap"] = "innerHTML"
            return response
        messages.error(request, error_msg)
        return redirect("management:book_register")

    if book_data is None:
        return render(
            request,
            "management/books/partials/search_not_found.html",
            {"message": "該当する書籍情報が見つかりませんでした。"},
        )

    form = BookRegisterForm(initial=book_data)
    return render(
        request,
        "management/books/partials/search_result.html",
        {"form": form},
    )


@login_required
@permission_required("books.add_book", raise_exception=True)
@require_POST
def book_create_view(request):
    """登録ボタン押下時(新規Book + 蔵書の登録)"""
    is_htmx = request.headers.get("HX-Request") == "true"
    form = BookRegisterForm(request.POST)

    if not form.is_valid():
        if is_htmx:
            return render(
                request,
                "management/books/partials/search_result.html",
                {"form": form},
            )
        messages.error(request, "入力内容に誤りがあります。")
        return redirect("management:book_register")

    location = form.cleaned_data["location"]
    quantity = form.cleaned_data["quantity"]

    with transaction.atomic():
        book = form.save()
        increase_stock(book, location, quantity)

    success_msg = f"『{book.title}』を{quantity}冊登録しました。"

    if is_htmx:
        return render(
            request,
            "management/books/partials/register_success.html",
            {"message": success_msg},
        )

    messages.success(request, success_msg)
    return redirect("management:book_list")


@login_required
@permission_required("books.add_book", raise_exception=True)
@require_POST
def book_item_create_view(request, book_id):
    """既存Bookに対する蔵書追加登録"""
    is_htmx = request.headers.get("HX-Request") == "true"
    book = get_object_or_404(Book, pk=book_id)
    form = BookItemAddForm(request.POST)

    if not form.is_valid():
        if is_htmx:
            return render(
                request,
                "management/books/partials/search_result_existing.html",
                {
                    "book": book,
                    "stock_summary": _build_stock_summary(book),
                    "form": form,
                },
            )
        messages.error(request, "入力内容に誤りがあります。")
        return redirect("management:book_register")

    location = form.cleaned_data["location"]
    quantity = form.cleaned_data["quantity"]

    with transaction.atomic():
        increase_stock(book, location, quantity)

    success_msg = f"『{book.title}』を{quantity}冊追加登録しました。"

    if is_htmx:
        return render(
            request,
            "management/books/partials/register_success.html",
            {"message": success_msg},
        )

    messages.success(request, success_msg)
    return redirect("management:book_list")
