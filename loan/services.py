from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date, datetime, timedelta

from .models import (
    BookItem,
    Loan,
    LoanStatus,
    Reservation,
    ReservationStatus,
)

LOAN_PERIOD_DAYS = 30
MAX_LOAN_COUNT_PER_USER = 5


def borrow_book_item(*, user, book_item: BookItem, start_date: date = None) -> Loan:
    """
    蔵書(BookItem) をユーザーに貸し出す処理
    """
    if start_date is None:
        start_date = timezone.localdate()

    # 　過去日チェック
    if start_date < timezone.localdate():
        raise ValidationError("過去の日付は利用できません")

    with transaction.atomic():
        # BookItemを行ロックで再取得（競合防止）
        locked_book_item = BookItem.objects.select_for_update().get(pk=book_item.pk)

        if locked_book_item.status != BookItem.Status.AVAILABLE:
            raise ValidationError("その蔵書は現在貸出できません")

        ready_reservation = (
            Reservation.objects.select_for_update()
            .filter(book=locked_book_item.book, status=ReservationStatus.READY)
            .order_by("reserved_at")
            .first()
        )

        if ready_reservation:
            if ready_reservation.user != user:
                raise ValidationError("この書籍は他利用者が予約済みです。")

            ready_reservation.status = ReservationStatus.COMPLETED
            ready_reservation.save(update_fields=["status"])

        # ユーザーの現在の貸し出し数チェック
        current_loans_count = Loan.objects.filter(
            user=user, status=LoanStatus.BORROWED
        ).count()

        if current_loans_count >= MAX_LOAN_COUNT_PER_USER:
            raise ValidationError(
                f"貸出上限数({MAX_LOAN_COUNT_PER_USER}冊)に達しています"
            )

        # 　返却期限日の計算
        due_date = start_date + timedelta(days=LOAN_PERIOD_DAYS)
        loan_datetime = timezone.make_aware(
            datetime.combine(start_date, datetime.min.time())
        )

        #  Loan レコードの作成
        loan = Loan.objects.create(
            user=user,
            book_item=locked_book_item,
            loaned_at=loan_datetime,
            due_date=due_date,
            status=LoanStatus.BORROWED,
        )

        #  book_item_statusの更新
        locked_book_item.status = BookItem.Status.LOANED
        locked_book_item.save(update_fields=["status"])

        return loan


def return_book_item(*, user, loan_id: int) -> Loan:
    """
    貸出中の本を返却処理する
    """
    with transaction.atomic():
        # 行ロック(select_for_update)を取得して同時更新（競合）を防止
        try:
            loan = (
                Loan.objects.select_related("book_item")
                .select_for_update()
                .get(id=loan_id, user=user, status=LoanStatus.BORROWED)
            )
        except Loan.DoesNotExist:
            raise ValidationError(
                "該当するアクティブな貸出データが見つかりません（すでに返却済みの可能性があります）。"
            )

        # 返却ステータスと返却日時を更新
        now = timezone.now()
        loan.status = LoanStatus.RETURNED
        loan.returned_at = now
        loan.save(update_fields=["status", "returned_at"])

        book_item = loan.book_item

        next_reservation = (
            Reservation.objects.select_for_update()
            .filter(book=book_item.book, status=ReservationStatus.WAITING)
            .order_by("reserved_at")
            .first()
        )

        if next_reservation:
            next_reservation.status = ReservationStatus.READY
            next_reservation.save(update_fields=["status"])

        book_item.status = BookItem.Status.AVAILABLE
        book_item.save(update_fields=["status"])

        return loan
