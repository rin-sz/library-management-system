from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, tag
from django.utils import timezone

from books.models import Book, BookItem, Location
from loan.models import Loan, LoanStatus
from loan.services import MAX_LOAN_COUNT_PER_USER, borrow_book_item

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
            borrow_book_item(user=self.user, book_item=self.book_item)

        self.assertIn("その蔵書は現在貸出できません", str(cm.exception))

    @tag("UT-LOAN-SVC-002")
    def test_borrow_book_item_when_max_loans_reached_raises_error(self):
        """[UT-LOAN-SVC-002] 貸出上限数到達時の貸出拒否"""
        # 事前条件: ユーザーの現在貸出中件数を5件にする
        # 現在の日時をもとにダミーの返却予定日を作成
        dummy_due_date = timezone.now() + timedelta(days=30)
        for _ in range(MAX_LOAN_COUNT_PER_USER):
            item = BookItem.objects.create(
                book=self.book,
                status=BookItem.Status.LOANED,
                location=self.location,
            )
            Loan.objects.create(
                user=self.user,
                book_item=item,
                status=LoanStatus.BORROWED,
                due_date=dummy_due_date,
            )

        # 検証: ValidationError が送出されること
        with self.assertRaises(ValidationError) as cm:
            borrow_book_item(user=self.user, book_item=self.book_item)

        self.assertIn(
            f"貸出上限数({MAX_LOAN_COUNT_PER_USER}冊)に達しています",
            str(cm.exception),
        )

    @tag("UT-LOAN-SVC-003")
    def test_borrow_book_item_when_under_max_loans_succeeds(self):
        """[UT-LOAN-SVC-003] 貸出上限直下での貸出許可"""
        # 事前条件: ユーザーの現在貸出中件数を4件にする
        dummy_due_date = timezone.now() + timedelta(days=30)
        for _ in range(MAX_LOAN_COUNT_PER_USER - 1):
            item = BookItem.objects.create(
                book=self.book,
                status=BookItem.Status.LOANED,
                location=self.location,
            )
            Loan.objects.create(
                user=self.user,
                book_item=item,
                status=LoanStatus.BORROWED,
                due_date=dummy_due_date,
            )

        # 検証: 例外が発生せず貸出データが作成されること
        loan = borrow_book_item(user=self.user, book_item=self.book_item)
        self.assertIsNotNone(loan)
        self.assertEqual(
            Loan.objects.filter(user=self.user, status=LoanStatus.BORROWED).count(),
            5,
        )

    @tag("UT-LOAN-SVC-004")
    def test_borrow_book_item_success(self):
        """[UT-LOAN-SVC-004] 貸出可能な蔵書を借りる（正常系）"""
        # 検証: 正常に Loan オブジェクトが返却されDBに保存されること
        loan = borrow_book_item(user=self.user, book_item=self.book_item)

        self.assertIsNotNone(loan.pk)
        self.assertEqual(loan.user, self.user)
        self.assertEqual(loan.book_item, self.book_item)

    @tag("UT-LOAN-SVC-005")
    def test_borrow_with_past_date_raises_validation_error(self):
        """[UT-LOAN-SVC-005] 過去の日付を指定して貸出を行うと ValidationError が発生することを確認"""
        past_date = timezone.localdate() - timedelta(days=1)  # 昨日

        with self.assertRaises(ValidationError) as cm:
            borrow_book_item(
                user=self.user, book_item=self.book_item, start_date=past_date
            )
