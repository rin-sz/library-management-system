from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
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


def borrow_book_item(*, user, book_item: BookItem, start_date: date) -> Loan:
    """蔵書(BookItem)の貸出手続き処理"""

    # 日付バリデーション
    if start_date < timezone.localdate():
        raise ValidationError("過去の日付は貸出開始日に指定できません。")

    with transaction.atomic():
        # 対象の蔵書に排他ロックをかけて取得
        locked_item = BookItem.objects.select_for_update().get(pk=book_item.pk)

        current_loan_count = Loan.objects.filter(
            user=user,
            status=LoanStatus.BORROWED,
        ).count()

        if current_loan_count >= MAX_LOAN_COUNT_PER_USER:
            raise ValidationError(
                f"貸出上限数({MAX_LOAN_COUNT_PER_USER}冊)を超えています。"
            )

        # 蔵書のステータスに応じた制御
        reservation_to_complete = None

        if locked_item.status == BookItem.Status.LOANED:
            raise ValidationError("この蔵書は現在貸出中です。")

        elif locked_item.status == BookItem.Status.RESERVED:
            # 取り置き中の場合：本人がREADY状態の予約を持っているか確認
            reservation_to_complete = (
                Reservation.objects.select_for_update()
                .filter(
                    user=user,
                    book=locked_item.book,
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

        # 貸出開始日から返却期限日を計算
        due_date = start_date + timedelta(days=LOAN_PERIOD_DAYS)

        # 貸出レコードを作成
        loan = Loan.objects.create(
            user=user,
            book_item=locked_item,
            loaned_at=start_date,
            due_date=due_date,
            status=LoanStatus.BORROWED,
        )

        # 蔵書を貸出中に変更
        locked_item.status = BookItem.Status.LOANED
        locked_item.save(update_fields=["status"])

        # 予約者本人が受け取った場合、予約を完了に変更
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

        # 蔵書をロック
        locked_item = BookItem.objects.select_for_update().get(
            pk=locked_loan.book_item.pk
        )

        if locked_loan.status == LoanStatus.RETURNED:
            raise ValidationError("この返却手続きは既に完了しています。")

        # 貸出ステータスを返却済みに更新
        locked_loan.status = LoanStatus.RETURNED
        locked_loan.returned_at = timezone.now()
        locked_loan.save(update_fields=["status", "returned_at"])

        # 待ち状態(WAITING)の最優先予約者を取得
        next_reservation = (
            Reservation.objects.select_for_update()
            .filter(
                book=locked_item.book,
                status=ReservationStatus.WAITING,
            )
            .order_by("reserved_at")
            .first()
        )

        # 次の予約者の有無に応じたステータス変更
        if next_reservation:
            next_reservation.status = ReservationStatus.READY
            next_reservation.save(update_fields=["status"])

            locked_item.status = BookItem.Status.RESERVED
            locked_item.save(update_fields=["status"])
        else:
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


def cancel_reservation(*, reservation_id: int, user) -> Reservation:
    """予約のキャンセル処理"""
    with transaction.atomic():
        # 対象の予約をロックして取得
        try:
            reservation = Reservation.objects.select_for_update().get(
                pk=reservation_id,
                user=user,
            )
        except Reservation.DoesNotExist:
            raise ValidationError("指定された予約が見つかりません。")

        # キャンセル可能な状態か確認
        if reservation.status not in [
            ReservationStatus.WAITING,
            ReservationStatus.READY,
        ]:
            raise ValidationError("この予約はキャンセルできません。")

        # キャンセル前の状態を保持
        was_ready = reservation.status == ReservationStatus.READY

        # READYの場合に使用するBookItemを取得
        reserved_item = None

        if was_ready:
            reserved_item = (
                BookItem.objects.select_for_update()
                .filter(
                    book=reservation.book,
                    status=BookItem.Status.RESERVED,
                )
                .first()
            )

            if reserved_item is None:
                raise ValidationError(
                    "取り置き中の蔵書が見つからないため、予約をキャンセルできません。"
                )

        # 予約をキャンセル状態に変更
        reservation.status = ReservationStatus.CANCELED
        reservation.save(update_fields=["status"])

        if not was_ready:
            return reservation

        # READY予約だった場合、
        # 次のWAITING予約を取得
        next_reservation = (
            Reservation.objects.select_for_update()
            .filter(
                book=reservation.book,
                status=ReservationStatus.WAITING,
            )
            .order_by("reserved_at")
            .first()
        )

        if next_reservation:
            # 次の予約者へREADYを引き継ぐ
            next_reservation.status = ReservationStatus.READY
            next_reservation.save(update_fields=["status"])

        else:
            reserved_item.status = BookItem.Status.AVAILABLE
            reserved_item.save(update_fields=["status"])

        return reservation
