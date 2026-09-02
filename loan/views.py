from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.http import HttpResponse

from .forms import BorrowForm, ReturnForm, ReserveForm

from .models import Book, BookItem, Loan, LoanStatus, ReservationStatus

from .services import (
    borrow_book_item,
    return_book_item,
    reserve_book,
    cancel_reservation,
)

# Create your views here.


@login_required
def my_loans_view(request):
    loans = request.user.loans.filter(status=LoanStatus.BORROWED).select_related(
        "book_item__book"
    )
    reservations = (
        request.user.reservations.filter(
            status__in=[
                ReservationStatus.WAITING,
                ReservationStatus.READY,
            ]
        )
        .select_related("book")
        .order_by("reserved_at")
    )

    return render(
        request,
        "loan/my_loans.html",
        {
            "loans": loans,
            "reservations": reservations,
        },
    )


@login_required
def borrow_view(request):
    if request.method == "POST":
        form = BorrowForm(request.POST)

        if form.is_valid():
            book_item_id = form.cleaned_data["book_item_id"]
            start_date = form.cleaned_data["start_date"]
            book_item = get_object_or_404(BookItem, pk=book_item_id)

            try:
                loan = borrow_book_item(
                    user=request.user,
                    book_item_id=book_item.pk,
                    start_date=start_date,
                )

                messages.success(
                    request,
                    f"『{book_item.book.title}』の貸し出し手続きが完了しました。",
                )
                return redirect("loan:borrow_success", pk=loan.pk)

            except ValidationError as e:
                for message in e.messages:
                    messages.error(request, message)
                return redirect("books:book_detail", pk=book_item.book.pk)
        else:
            messages.error(
                request,
                "不正なリクエストです。もう一度お試しください。",
            )

            book_item_id = request.POST.get("book_item_id")

            if book_item_id and BookItem.objects.filter(pk=book_item_id).exists():
                item = BookItem.objects.get(pk=book_item_id)
                return redirect("books:book_detail", pk=item.book.pk)

    return redirect("books:book_list")


@login_required
def borrow_success_view(request, pk):
    """貸出完了画面"""
    loan = get_object_or_404(Loan, pk=pk, user=request.user)
    return render(request, "loan/borrow_success.html", {"loan": loan})


@login_required
@require_POST
def return_view(request):

    is_htmx = request.headers.get("HX-Request") == "true"
    form = ReturnForm(request.POST)

    if not form.is_valid():
        error_msg = "送信されたデータが正しくありません"
        if is_htmx:
            response = render(
                request,
                "loan/partials/message_alert.html",
                {"message": error_msg, "tags": "danger"},
            )
            response["HX-Retarget"] = "#message-container"
            response["HX-Reswap"] = "innerHTML"
            return response

        messages.error(request, error_msg)
        return redirect("loan:my_loans")

    loan_id = form.cleaned_data["loan_id"]

    try:
        loan = return_book_item(user=request.user, loan_id=loan_id)
        success_msg = f"『{loan.book_item.book.title}』の返却手続きが完了しました。"

        if is_htmx:
            return render(
                request,
                "loan/partials/return_success.html",
                {"message": success_msg},
            )
        messages.success(request, success_msg)

    except ValidationError as e:
        error_msg = e.messages[0] if hasattr(e, "messages") else str(e)

        if is_htmx:
            response = render(
                request,
                "loan/partials/message_alert.html",
                {"message": error_msg, "tags": "danger"},
            )
            response["HX-Retarget"] = "#message-container"
            response["HX-Reswap"] = "innerHTML"
            return response

        messages.error(request, error_msg)

    return redirect("loan:my_loans")


@login_required
@require_POST
def reserve_view(request):
    form = ReserveForm(request.POST)

    if form.is_valid():
        book_id = form.cleaned_data["book_id"]
        book = get_object_or_404(Book, pk=book_id)

        try:
            reserve_book(user=request.user, book=book)
            messages.success(request, f"『{book.title}』の予約が完了しました。")
            return redirect("books:book_detail", pk=book.pk)

        except ValidationError as e:
            for message in e.messages:
                messages.error(request, message)
            return redirect("books:book_detail", pk=book.pk)

    else:
        messages.error(request, "入力内容に誤りがあるか、不正なリクエストです。")
        book_id = request.POST.get("book_id")
        if book_id and Book.objects.filter(pk=book_id).exists():
            return redirect("books:book_detail", pk=book_id)

    return redirect("books:book_list")


@login_required
@require_POST
def reserve_cancel_view(request):
    """予約キャンセル処理"""
    reservation_id_raw = request.POST.get("reservation_id")

    if not reservation_id_raw:
        messages.error(request, "キャンセル対象の予約が指定されていません。")
        return redirect("loan:my_loans")

    try:
        reservation_id = int(reservation_id_raw)
        cancel_reservation(
            reservation_id=reservation_id,
            user=request.user,
        )
    except ValueError:
        # 数値変換エラー時のユーザー向けメッセージ
        messages.error(request, "不正な予約IDが指定されました。")
    except ValidationError as e:
        # ValidationErrorのメッセージリストを個別に展開
        for message in e.messages:
            messages.error(request, message)
    else:
        messages.success(request, "予約をキャンセルしました。")
        if request.headers.get("HX-Request") == "true":
            return HttpResponse("")

    return redirect("loan:my_loans")
