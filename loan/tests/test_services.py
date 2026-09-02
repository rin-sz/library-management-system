from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, tag
from django.utils import timezone

from books.models import Book, BookItem, Location
from loan.models import Loan, LoanStatus, Reservation, ReservationStatus
from loan.services import (
    MAX_LOAN_COUNT_PER_USER,
    MAX_RESERVATION_COUNT_PER_USER,
    borrow_book_item,
    reserve_book,
    return_book_item,
    cancel_reservation,
)

from datetime import timedelta

User = get_user_model()


class BorrowBookItemServiceTestCase(TestCase):
    def setUp(self):
        """各テストメソッド実行前の共通セットアップ"""
        self.user = User.objects.create_user(
            username="testuser", password="password123"
        )
        self.location = Location.objects.create(name="中央図書館 1F")
        self.book = Book.objects.create(title="テスト用書籍")
        self.book_item = BookItem.objects.create(
            book=self.book,
            status=BookItem.Status.AVAILABLE,
            location=self.location,
        )

    @tag("UT-LOAN-SVC-001")
    def test_borrow_book_item_when_not_available_raises_error(self):
        """[UT-LOAN-SVC-001] 貸出不能な蔵書の貸出拒否"""
        # 事前条件: ステータスを LOANED に変更
        self.book_item.status = BookItem.Status.LOANED
        self.book_item.save()

        # 検証: ValidationError が送出されること
        with self.assertRaises(ValidationError) as cm:
            borrow_book_item(
                user=self.user,
                book_item_id=self.book_item.pk,
                start_date=timezone.localdate(),
            )

        self.assertIn("この蔵書は現在貸出中です。", str(cm.exception))

    @tag("UT-LOAN-SVC-002")
    def test_borrow_book_item_when_max_loans_reached_raises_error(self):
        """[UT-LOAN-SVC-002] 貸出上限数到達時の貸出拒否"""
        # 事前条件: ユーザーの現在貸出中件数を5件にする
        # 現在の日時をもとにダミーの返却予定日を作成
        dummy_due_date = timezone.localdate() + timedelta(days=30)

        for _ in range(MAX_LOAN_COUNT_PER_USER):
            item = BookItem.objects.create(
                book=self.book,
                status=BookItem.Status.LOANED,
                location=self.location,
            )
            Loan.objects.create(
                user=self.user,
                book_item=item,
                loaned_at=timezone.localdate(),
                status=LoanStatus.BORROWED,
                due_date=dummy_due_date,
            )

        # 検証: ValidationError が送出されること
        with self.assertRaises(ValidationError) as cm:
            borrow_book_item(
                user=self.user,
                book_item_id=self.book_item.pk,
                start_date=timezone.localdate(),
            )

        self.assertIn(
            f"貸出上限数({MAX_LOAN_COUNT_PER_USER}冊)を超えています。",
            str(cm.exception),
        )

    @tag("UT-LOAN-SVC-003")
    def test_borrow_book_item_when_under_max_loans_succeeds(self):
        """[UT-LOAN-SVC-003] 貸出上限直下での貸出許可"""
        # 事前条件: ユーザーの現在貸出中件数を4件にする
        dummy_due_date = timezone.localdate() + timedelta(days=30)

        for _ in range(MAX_LOAN_COUNT_PER_USER - 1):
            item = BookItem.objects.create(
                book=self.book,
                status=BookItem.Status.LOANED,
                location=self.location,
            )
            Loan.objects.create(
                user=self.user,
                book_item=item,
                loaned_at=timezone.localdate(),
                status=LoanStatus.BORROWED,
                due_date=dummy_due_date,
            )

        # 検証: 例外が発生せず貸出データが作成されること
        loan = borrow_book_item(
            user=self.user,
            book_item_id=self.book_item.pk,
            start_date=timezone.localdate(),
        )
        self.assertIsNotNone(loan)
        self.assertEqual(
            Loan.objects.filter(user=self.user, status=LoanStatus.BORROWED).count(),
            5,
        )

    @tag("UT-LOAN-SVC-004")
    def test_borrow_book_item_success(self):
        """[UT-LOAN-SVC-004] 貸出可能な蔵書を借りる（正常系）"""
        # 検証: 正常に Loan オブジェクトが返却されDBに保存されること
        loan = borrow_book_item(
            user=self.user,
            book_item_id=self.book_item.pk,
            start_date=timezone.localdate(),
        )

        self.assertIsNotNone(loan.pk)
        self.assertEqual(loan.user, self.user)
        self.assertEqual(loan.book_item, self.book_item)

    @tag("UT-LOAN-SVC-005")
    def test_borrow_with_past_date_raises_validation_error(self):
        """[UT-LOAN-SVC-005] 過去の日付を指定して貸出を行うと ValidationError が発生することを確認"""
        past_date = timezone.localdate() - timedelta(days=1)  # 昨日

        with self.assertRaises(ValidationError) as cm:
            borrow_book_item(
                user=self.user, book_item_id=self.book_item.pk, start_date=past_date
            )

        self.assertIn(
            "過去の日付は貸出開始日に指定できません。",
            str(cm.exception),
        )


class ReturnBookItemServiceTestCase(TestCase):
    def setUp(self):
        """各テストメソッド実行前の共通セットアップ"""
        self.user = User.objects.create_user(
            username="testuser", password="password123"
        )
        self.other_user = User.objects.create_user(
            username="otheruser", password="password123"
        )
        self.location = Location.objects.create(name="中央図書館 1F")
        self.book = Book.objects.create(title="テスト用書籍")
        self.book_item = BookItem.objects.create(
            book=self.book,
            status=BookItem.Status.LOANED,
            location=self.location,
        )
        self.loan = Loan.objects.create(
            user=self.user,
            book_item=self.book_item,
            loaned_at=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=30),
            status=LoanStatus.BORROWED,
        )

    @tag("UT-LOAN-SVC-006")
    def test_return_book_item_success_without_reservations(self):
        """[UT-LOAN-SVC-006] 予約がない蔵書の返却処理（正常系）"""
        returned_loan = return_book_item(user=self.user, loan_id=self.loan.pk)

        self.loan.refresh_from_db()
        self.book_item.refresh_from_db()

        self.assertEqual(returned_loan.status, LoanStatus.RETURNED)
        self.assertIsNotNone(returned_loan.returned_at)
        self.assertEqual(self.book_item.status, BookItem.Status.AVAILABLE)

    @tag("UT-LOAN-SVC-007")
    def test_return_book_item_success_with_waiting_reservation(self):
        """[UT-LOAN-SVC-007] 待機中の予約がある蔵書の返却処理（最優先予約者の繰り上げ）"""
        reservation = Reservation.objects.create(
            user=self.other_user,
            book=self.book,
            status=ReservationStatus.WAITING,
        )

        return_book_item(user=self.user, loan_id=self.loan.pk)

        self.book_item.refresh_from_db()
        reservation.refresh_from_db()

        self.assertEqual(self.book_item.status, BookItem.Status.RESERVED)
        self.assertEqual(reservation.status, ReservationStatus.READY)
        self.assertEqual(reservation.book_item, self.book_item)

    @tag("UT-LOAN-SVC-008")
    def test_return_book_item_already_returned_raises_error(self):
        """[UT-LOAN-SVC-008] 既に返却済みの貸出に対する返却拒否"""
        self.loan.status = LoanStatus.RETURNED
        self.loan.save()

        with self.assertRaises(ValidationError) as cm:
            return_book_item(user=self.user, loan_id=self.loan.pk)

        self.assertIn("この返却手続きは既に完了しています。", str(cm.exception))


class ReserveBookServiceTestCase(TestCase):
    def setUp(self):
        """各テストメソッド実行前の共通セットアップ"""
        self.user = User.objects.create_user(
            username="testuser", password="password123"
        )
        self.location = Location.objects.create(name="中央図書館 1F")
        self.book = Book.objects.create(
            title="テスト用書籍",
            isbn="9784000000001",
        )

    @tag("UT-LOAN-SVC-009")
    def test_reserve_book_success(self):
        """[UT-LOAN-SVC-009] 書籍の予約（正常系）"""
        BookItem.objects.create(
            book=self.book,
            status=BookItem.Status.LOANED,
            location=self.location,
        )

        reservation = reserve_book(user=self.user, book=self.book)

        self.assertIsNotNone(reservation.pk)
        self.assertEqual(reservation.user, self.user)
        self.assertEqual(reservation.book, self.book)
        self.assertEqual(reservation.status, ReservationStatus.WAITING)

    @tag("UT-LOAN-SVC-010")
    def test_reserve_book_when_no_items_raises_error(self):
        """[UT-LOAN-SVC-010] 所蔵がない書籍への予約拒否"""
        with self.assertRaises(ValidationError) as cm:
            reserve_book(user=self.user, book=self.book)

        self.assertIn("この書籍は現在所蔵されていません。", str(cm.exception))

    @tag("UT-LOAN-SVC-011")
    def test_reserve_book_when_max_reservations_reached_raises_error(self):
        """[UT-LOAN-SVC-011] 予約上限数到達時の予約拒否"""
        for i in range(MAX_RESERVATION_COUNT_PER_USER):
            other_book = Book.objects.create(
                title=f"別書籍_{i}",
                isbn=f"97840000000{i + 2}",
            )
            BookItem.objects.create(
                book=other_book,
                status=BookItem.Status.LOANED,
                location=self.location,
            )
            Reservation.objects.create(
                user=self.user,
                book=other_book,
                status=ReservationStatus.WAITING,
            )

        BookItem.objects.create(
            book=self.book,
            status=BookItem.Status.LOANED,
            location=self.location,
        )

        with self.assertRaises(ValidationError) as cm:
            reserve_book(user=self.user, book=self.book)

        self.assertIn(
            f"予約上限数({MAX_RESERVATION_COUNT_PER_USER}件)に達しています。",
            str(cm.exception),
        )

    @tag("UT-LOAN-SVC-012")
    def test_reserve_book_duplicate_reservation_raises_error(self):
        """[UT-LOAN-SVC-012] 同一書籍への重複予約拒否"""
        BookItem.objects.create(
            book=self.book,
            status=BookItem.Status.LOANED,
            location=self.location,
        )
        Reservation.objects.create(
            user=self.user,
            book=self.book,
            status=ReservationStatus.WAITING,
        )

        with self.assertRaises(ValidationError) as cm:
            reserve_book(user=self.user, book=self.book)

        self.assertIn("この書籍はすでに予約済みです。", str(cm.exception))

    @tag("UT-LOAN-SVC-013")
    def test_reserve_book_already_borrowed_raises_error(self):
        """[UT-LOAN-SVC-013] 自身が貸出中の書籍への予約拒否"""
        item = BookItem.objects.create(
            book=self.book,
            status=BookItem.Status.LOANED,
            location=self.location,
        )
        Loan.objects.create(
            user=self.user,
            book_item=item,
            loaned_at=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=30),
            status=LoanStatus.BORROWED,
        )

        with self.assertRaises(ValidationError) as cm:
            reserve_book(user=self.user, book=self.book)

        self.assertIn("現在貸出中の書籍は予約できません。", str(cm.exception))

    @tag("UT-LOAN-SVC-014")
    def test_reserve_book_available_item_exists_raises_error(self):
        """[UT-LOAN-SVC-014] 貸出可能な蔵書が存在する場合の予約拒否"""
        BookItem.objects.create(
            book=self.book,
            status=BookItem.Status.AVAILABLE,
            location=self.location,
        )

        with self.assertRaises(ValidationError) as cm:
            reserve_book(user=self.user, book=self.book)

        self.assertIn(
            "貸出可能な蔵書があります。予約ではなく直接貸出手続きを行ってください。",
            str(cm.exception),
        )


class CancelReservationServiceTestCase(TestCase):
    def setUp(self):
        """各テストメソッド実行前の共通セットアップ"""
        self.user = User.objects.create_user(
            username="testuser", password="password123"
        )
        self.other_user = User.objects.create_user(
            username="otheruser", password="password123"
        )
        self.location = Location.objects.create(name="中央図書館 1F")
        self.book = Book.objects.create(title="テスト用書籍")

    @tag("UT-LOAN-SVC-015")
    def test_cancel_waiting_reservation_success(self):
        """[UT-LOAN-SVC-015] WAITING状態の予約キャンセル（正常系）"""
        reservation = Reservation.objects.create(
            user=self.user,
            book=self.book,
            status=ReservationStatus.WAITING,
        )

        canceled = cancel_reservation(reservation_id=reservation.pk, user=self.user)

        self.assertEqual(canceled.status, ReservationStatus.CANCELED)

    @tag("UT-LOAN-SVC-016")
    def test_cancel_ready_reservation_transfers_to_next_waiting_reservation(self):
        """[UT-LOAN-SVC-016] READY状態の予約キャンセル（後続予約者への自動引き継ぎ）"""
        book_item = BookItem.objects.create(
            book=self.book,
            status=BookItem.Status.RESERVED,
            location=self.location,
        )
        res_ready = Reservation.objects.create(
            user=self.user,
            book=self.book,
            book_item=book_item,
            status=ReservationStatus.READY,
        )
        res_waiting = Reservation.objects.create(
            user=self.other_user,
            book=self.book,
            status=ReservationStatus.WAITING,
        )

        cancel_reservation(reservation_id=res_ready.pk, user=self.user)

        res_ready.refresh_from_db()
        res_waiting.refresh_from_db()
        book_item.refresh_from_db()

        self.assertEqual(res_ready.status, ReservationStatus.CANCELED)
        self.assertEqual(res_waiting.status, ReservationStatus.READY)
        self.assertEqual(res_waiting.book_item, book_item)
        self.assertEqual(book_item.status, BookItem.Status.RESERVED)

    @tag("UT-LOAN-SVC-017")
    def test_cancel_ready_reservation_restores_item_to_available_when_no_waiting(self):
        """[UT-LOAN-SVC-017] READY状態の予約キャンセル（後続予約がない場合のAVAILABLE復帰）"""
        book_item = BookItem.objects.create(
            book=self.book,
            status=BookItem.Status.RESERVED,
            location=self.location,
        )
        res_ready = Reservation.objects.create(
            user=self.user,
            book=self.book,
            book_item=book_item,
            status=ReservationStatus.READY,
        )

        cancel_reservation(reservation_id=res_ready.pk, user=self.user)

        res_ready.refresh_from_db()
        book_item.refresh_from_db()

        self.assertEqual(res_ready.status, ReservationStatus.CANCELED)
        self.assertEqual(book_item.status, BookItem.Status.AVAILABLE)

    @tag("UT-LOAN-SVC-018")
    def test_cancel_reservation_not_found_or_other_user_raises_error(self):
        """[UT-LOAN-SVC-018] 存在しない・または他人の予約キャンセルに対する拒否"""
        reservation = Reservation.objects.create(
            user=self.user,
            book=self.book,
            status=ReservationStatus.WAITING,
        )

        with self.assertRaises(ValidationError) as cm:
            cancel_reservation(reservation_id=reservation.pk, user=self.other_user)

        self.assertIn("指定された予約が見つかりません。", str(cm.exception))

    @tag("UT-LOAN-SVC-019")
    def test_cancel_reservation_invalid_status_raises_error(self):
        """[UT-LOAN-SVC-019] キャンセル不可なステータス（CANCELEDなど）に対する拒否"""
        reservation = Reservation.objects.create(
            user=self.user,
            book=self.book,
            status=ReservationStatus.CANCELED,
        )

        with self.assertRaises(ValidationError) as cm:
            cancel_reservation(reservation_id=reservation.pk, user=self.user)

        self.assertIn("この予約はキャンセルできません。", str(cm.exception))
