from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth import get_user_model

from datetime import date, timedelta

from .models import (
    Book,
    BookItem,
    Loan,
    LoanStatus,
    Reservation,
    ReservationStatus,
)

MAX_RESERVATION_COUNT_PER_USER = 3
LOAN_PERIOD_DAYS = 30
MAX_LOAN_COUNT_PER_USER = 5


def borrow_book_item(
    *,
    user,
    book_item_id: int,
    start_date: date,
) -> Loan:
    """蔵書(BookItem)の貸出手続き処理"""
    if start_date < timezone.localdate():
        raise ValidationError("過去の日付は貸出開始日に指定できません。")

    User = get_user_model()

    with transaction.atomic():
        # 同一ユーザーの同時貸出を防ぐためユーザーをロック
        User.objects.select_for_update().get(pk=user.pk)

        current_loan_count = Loan.objects.filter(
            user=user,
            status=LoanStatus.BORROWED,
        ).count()

        if current_loan_count >= MAX_LOAN_COUNT_PER_USER:
            raise ValidationError(
                f"貸出上限数({MAX_LOAN_COUNT_PER_USER}冊)を超えています。"
            )

        # 対象の蔵書に排他ロックをかけて取得
        locked_item = (
            BookItem.objects.select_for_update()
            .select_related("book")
            .get(pk=book_item_id)
        )

        reservation_to_complete = None

        if locked_item.status == BookItem.Status.LOANED:
            raise ValidationError("この蔵書は現在貸出中です。")

        elif locked_item.status == BookItem.Status.RESERVED:
            reservation_to_complete = (
                Reservation.objects.select_for_update()
                .filter(
                    user=user,
                    book=locked_item.book,
                    book_item=locked_item,
                    status=ReservationStatus.READY,
                )
                .first()
            )

            if not reservation_to_complete:
                raise ValidationError(
                    "この蔵書は他の利用者の取り置き中のため貸出できません。"
                )

        elif locked_item.status != BookItem.Status.AVAILABLE:
            raise ValidationError("この蔵書は現在貸出できる状態ではありません。")

        due_date = start_date + timedelta(days=LOAN_PERIOD_DAYS)

        loan = Loan.objects.create(
            user=user,
            book_item=locked_item,
            loaned_at=start_date,
            due_date=due_date,
            status=LoanStatus.BORROWED,
        )

        locked_item.status = BookItem.Status.LOANED
        locked_item.save(update_fields=["status"])

        if reservation_to_complete:
            reservation_to_complete.status = ReservationStatus.COMPLETED
            reservation_to_complete.save(update_fields=["status"])

        return loan


def return_book_item(*, user, loan_id: int) -> Loan:
    """蔵書(BookItem)の返却処理"""
    with transaction.atomic():
        # 貸出レコードをロックし、現在のユーザーの貸出であることを確認
        locked_loan = (
            Loan.objects.select_for_update()
            .select_related("book_item")
            .get(
                pk=loan_id,
                user=user,
            )
        )

        # 既に返却済みなら早期リターン
        if locked_loan.status == LoanStatus.RETURNED:
            raise ValidationError("この返却手続きは既に完了しています。")

        # 蔵書レコードをロック
        locked_item = BookItem.objects.select_for_update().get(
            pk=locked_loan.book_item_id
        )

        # 貸出ステータスを返却済みに更新
        locked_loan.status = LoanStatus.RETURNED
        locked_loan.returned_at = timezone.now()
        locked_loan.save(update_fields=["status", "returned_at"])

        # (WAITING)の最優先予約者を取得（_id参照）
        next_reservation = (
            Reservation.objects.select_for_update()
            .filter(
                book_id=locked_item.book_id,
                status=ReservationStatus.WAITING,
            )
            .order_by("reserved_at")
            .first()
        )

        if next_reservation:
            next_reservation.status = ReservationStatus.READY
            next_reservation.book_item = locked_item
            next_reservation.save(update_fields=["status", "book_item"])

            locked_item.status = BookItem.Status.RESERVED
            locked_item.save(update_fields=["status"])
        else:
            # 次の予約者がいない場合は利用可能に変更
            locked_item.status = BookItem.Status.AVAILABLE
            locked_item.save(update_fields=["status"])

        return locked_loan


def reserve_book(*, user, book: Book) -> Reservation:
    """書籍(Book)をユーザーが予約する処理"""
    with transaction.atomic():
        # 対象の Book に行ロックをかけて同時実行による競合を防ぐ
        locked_book = Book.objects.select_for_update().get(pk=book.pk)

        # 蔵書(BookItem)が1冊も存在しない場合は予約不可
        total_items_count = BookItem.objects.filter(book=locked_book).count()
        if total_items_count == 0:
            raise ValidationError("この書籍は現在所蔵されていません。")

        # ユーザーの現在の有効な予約を取得
        user_reservations = Reservation.objects.filter(
            user=user,
            status__in=[ReservationStatus.WAITING, ReservationStatus.READY],
        )

        # 予約上限数チェック
        if user_reservations.count() >= MAX_RESERVATION_COUNT_PER_USER:
            raise ValidationError(
                f"予約上限数({MAX_RESERVATION_COUNT_PER_USER}件)に達しています。"
            )

        # 同一書籍への重複予約チェック
        if user_reservations.filter(book=locked_book).exists():
            raise ValidationError("この書籍はすでに予約済みです。")

        #  ユーザーが現在その書籍を借りていないかチェック
        is_already_borrowed = Loan.objects.filter(
            user=user,
            book_item__book=locked_book,
            status=LoanStatus.BORROWED,
        ).exists()

        if is_already_borrowed:
            raise ValidationError("現在貸出中の書籍は予約できません。")

        has_active_item = BookItem.objects.filter(
            book=locked_book,
            status__in=[
                BookItem.Status.AVAILABLE,
                BookItem.Status.LOANED,
                BookItem.Status.RESERVED,
            ],
        ).exists()

        if not has_active_item:
            raise ValidationError("現在蔵書がありません。")

        has_available_item = BookItem.objects.filter(
            book=locked_book, status=BookItem.Status.AVAILABLE
        ).exists()

        if has_available_item:
            raise ValidationError(
                "貸出可能な蔵書があります。予約ではなく直接貸出手続きを行ってください。"
            )

        reservation = Reservation.objects.create(
            user=user,
            book=locked_book,
            status=ReservationStatus.WAITING,
        )

        return reservation


def cancel_reservation(
    *,
    reservation_id: int,
    user,
) -> Reservation:
    """予約のキャンセル処理"""

    with transaction.atomic():
        # 対象の予約情報を確認
        try:
            target_reservation = Reservation.objects.get(
                pk=reservation_id,
                user=user,
            )
        except Reservation.DoesNotExist:
            raise ValidationError("指定された予約が見つかりません。")

        # WAITING・READY以外はキャンセル不可
        if target_reservation.status not in [
            ReservationStatus.WAITING,
            ReservationStatus.READY,
        ]:
            raise ValidationError("この予約はキャンセルできません。")

        # WAITINGの場合はBookItemのロック不要でキャンセル完了
        if target_reservation.status == ReservationStatus.WAITING:
            reservation = Reservation.objects.select_for_update().get(pk=reservation_id)
            reservation.status = ReservationStatus.CANCELED
            reservation.save(update_fields=["status"])
            return reservation

        # --- READYの場合の処理 ---
        if not target_reservation.book_item_id:
            raise ValidationError("この予約に取り置き蔵書が紐付いていません。")

        #  BookItem を先にロック
        reserved_item = BookItem.objects.select_for_update().get(
            pk=target_reservation.book_item_id
        )

        if reserved_item.status != BookItem.Status.RESERVED:
            raise ValidationError("取り置き中の蔵書の状態が正しくありません。")

        # 次に Reservation をロックしてキャンセル処理を行う
        reservation = Reservation.objects.select_for_update().get(pk=reservation_id)
        reservation.status = ReservationStatus.CANCELED
        reservation.save(update_fields=["status"])

        # 次のWAITING予約を取得してロック
        next_reservation = (
            Reservation.objects.select_for_update()
            .filter(
                book_id=reservation.book_id,
                status=ReservationStatus.WAITING,
            )
            .order_by("reserved_at")
            .first()
        )

        if next_reservation:
            # 次の予約者へ取り置きを引き継ぐ
            next_reservation.status = ReservationStatus.READY
            next_reservation.book_item = reserved_item
            next_reservation.save(update_fields=["status", "book_item"])
        else:
            # 次の予約者がいなければ貸出可能に戻す
            reserved_item.status = BookItem.Status.AVAILABLE
            reserved_item.save(update_fields=["status"])

        return reservation
