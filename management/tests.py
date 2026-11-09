"""書籍情報編集機能のテスト。

対象:
- services.py: decrease_stock
- views.py: _build_stock_summary, _get_existing_location
- views.py: book_item_increase_view, book_item_decrease_view, book_update_view

前提:
- Book, BookItem, Location, Category は books/models.py の定義に準拠
- Loan は loan/models.py に存在し、book_item への FK を持つ
"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from books.models import Book, BookItem, Category, Location
from loan.models import Loan, LoanStatus
from management.service import decrease_stock
from management.views import _build_stock_summary, _get_existing_location

User = get_user_model()


class BookEditTestCaseBase(TestCase):
    """共通のセットアップをまとめた基底クラス。"""

    def setUp(self):
        self.book = Book.objects.create(
            isbn="9784000000000",
            title="テスト書籍",
            author="テスト著者",
            publisher="テスト出版社",
        )
        self.location_a = Location.objects.create(name="保管場所A")
        self.location_b = Location.objects.create(name="保管場所B")

    def _login_with_permissions(self, codenames):
        """指定したcodenameの権限(Bookモデル対象)を持つユーザーでログインする。"""
        user = User.objects.create_user(username="tester", password="pass1234")
        book_ct = ContentType.objects.get_for_model(Book)
        permissions = Permission.objects.filter(
            content_type=book_ct, codename__in=codenames
        )
        user.user_permissions.add(*permissions)
        self.client.login(username="tester", password="pass1234")
        return user

    def _create_book_items(self, location, status, count):
        """指定した状態のBookItemをcount件作成する。"""
        return [
            BookItem.objects.create(book=self.book, location=location, status=status)
            for _ in range(count)
        ]


class DecreaseStockServiceTests(BookEditTestCaseBase):
    """services.py: decrease_stock のテスト。"""

    @tag("UT-EDIT-SVC-001")
    def test_decreases_available_items_by_quantity(self):
        """[UT-EDIT-SVC-001] AVAILABLE状態の個体がquantity分だけDISPOSEDになる(正常系)"""
        items = self._create_book_items(self.location_a, BookItem.Status.AVAILABLE, 5)

        decrease_stock(self.book, 3)

        disposed_count = BookItem.objects.filter(
            pk__in=[i.pk for i in items], status=BookItem.Status.DISPOSED
        ).count()
        available_count = BookItem.objects.filter(
            pk__in=[i.pk for i in items], status=BookItem.Status.AVAILABLE
        ).count()
        self.assertEqual(disposed_count, 3)
        self.assertEqual(available_count, 2)

    @tag("UT-EDIT-SVC-002")
    def test_excludes_loaned_and_reserved_items(self):
        """[UT-EDIT-SVC-002] LOANED・RESERVED状態の個体は対象から除外される"""
        available_items = self._create_book_items(
            self.location_a, BookItem.Status.AVAILABLE, 2
        )
        loaned_item = self._create_book_items(
            self.location_a, BookItem.Status.LOANED, 1
        )[0]
        reserved_item = self._create_book_items(
            self.location_a, BookItem.Status.RESERVED, 1
        )[0]

        decrease_stock(self.book, 2)

        for item in available_items:
            item.refresh_from_db()
            self.assertEqual(item.status, BookItem.Status.DISPOSED)

        loaned_item.refresh_from_db()
        reserved_item.refresh_from_db()
        self.assertEqual(loaned_item.status, BookItem.Status.LOANED)
        self.assertEqual(reserved_item.status, BookItem.Status.RESERVED)

    @tag("UT-EDIT-SVC-003")
    def test_raises_value_error_when_insufficient_stock(self):
        """テスト3: 在庫不足時にValueErrorが発生し、何も変更されない"""
        items = self._create_book_items(self.location_a, BookItem.Status.AVAILABLE, 2)

        with self.assertRaises(ValueError):
            decrease_stock(self.book, 3)

        for item in items:
            item.refresh_from_db()
            self.assertEqual(item.status, BookItem.Status.AVAILABLE)

    @tag("UT-EDIT-SVC-004")
    def test_does_not_raise_protected_error_when_loan_history_exists(self):
        """テスト4: 貸出履歴を持つAVAILABLE個体でもProtectedErrorが起きずDISPOSEDにできる"""
        item = self._create_book_items(self.location_a, BookItem.Status.AVAILABLE, 1)[0]
        borrower = User.objects.create_user(username="borrower", password="pass1234")
        # 返却済み(RETURNED)の貸出履歴。BORROWED状態はbook_itemごとに1件しか
        # 存在できない制約(unique_active_loan_per_book_item)があるため、
        # 「過去に貸し出されて返却済み」というテストの意図に合わせてRETURNEDにする。
        Loan.objects.create(
            user=borrower,
            book_item=item,
            loaned_at=date.today() - timedelta(days=10),
            due_date=date.today() - timedelta(days=3),
            returned_at=timezone.now(),
            status=LoanStatus.RETURNED,
        )

        try:
            decrease_stock(self.book, 1)
        except Exception as e:
            self.fail(f"ProtectedError等の例外が発生してはならない: {e}")

        item.refresh_from_db()
        self.assertEqual(item.status, BookItem.Status.DISPOSED)


class HelperFunctionTests(BookEditTestCaseBase):
    """views.py: _build_stock_summary, _get_existing_location のテスト。"""

    @tag("UT-EDIT-SVC-005")
    def test_build_stock_summary_excludes_disposed(self):
        """テスト5: _build_stock_summaryがDISPOSED状態を集計から除外する"""
        self._create_book_items(self.location_a, BookItem.Status.AVAILABLE, 3)
        self._create_book_items(self.location_a, BookItem.Status.DISPOSED, 2)

        summary = _build_stock_summary(self.book)

        self.assertEqual(summary, [(self.location_a.name, 3)])

    @tag("UT-EDIT-SVC-006")
    def test_get_existing_location_returns_none_when_no_stock(self):
        """テスト6: 在庫ゼロの本に対してNoneを返す"""
        location = _get_existing_location(self.book)
        self.assertIsNone(location)

    @tag("UT-EDIT-SVC-007")
    def test_get_existing_location_returns_none_when_only_disposed(self):
        """テスト7: DISPOSEDのみ残っている本に対してNoneを返す(実質在庫なし扱い)"""
        self._create_book_items(self.location_a, BookItem.Status.DISPOSED, 2)

        location = _get_existing_location(self.book)

        self.assertIsNone(location)

    @tag("UT-EDIT-SVC-008")
    def test_get_existing_location_returns_correct_location(self):
        """テスト8: AVAILABLE在庫がある本に対して正しいlocationを返す"""
        self._create_book_items(self.location_a, BookItem.Status.AVAILABLE, 1)

        location = _get_existing_location(self.book)

        self.assertEqual(location, self.location_a)


class BookItemIncreaseViewTests(BookEditTestCaseBase):
    """views.py: book_item_increase_view のテスト。"""

    def setUp(self):
        super().setUp()
        self._login_with_permissions(["change_book"])
        self.url = reverse("management:book_item_increase", args=[self.book.id])

    @tag("UT-EDIT-SVC-009")
    def test_requires_location_when_no_existing_stock(self):
        """テスト9: 既存在庫がない場合、location未指定だとバリデーションエラーになる"""
        response = self.client.post(self.url, {"quantity": 1}, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        form = response.context["increase_form"]
        self.assertFalse(form.is_valid())
        self.assertIn("location", form.errors)
        self.assertEqual(BookItem.objects.filter(book=self.book).count(), 0)

    @tag("UT-EDIT-SVC-010")
    def test_adds_to_existing_location_with_quantity_only(self):
        """テスト10: 既存在庫がある場合、quantityのみで既存locationに追加される"""
        self._create_book_items(self.location_a, BookItem.Status.AVAILABLE, 1)

        response = self.client.post(self.url, {"quantity": 2}, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        new_items = BookItem.objects.filter(
            book=self.book, location=self.location_a, status=BookItem.Status.AVAILABLE
        )
        self.assertEqual(new_items.count(), 3)  # 既存1件 + 追加2件


class BookItemDecreaseViewTests(BookEditTestCaseBase):
    """views.py: book_item_decrease_view のテスト。"""

    def setUp(self):
        super().setUp()
        self._login_with_permissions(["change_book"])
        self.url = reverse("management:book_item_decrease", args=[self.book.id])

    @tag("UT-EDIT-SVC-011")
    def test_decreases_stock_successfully(self):
        """テスト11: 正常に減少し、対象個体がDISPOSEDになる"""
        items = self._create_book_items(self.location_a, BookItem.Status.AVAILABLE, 3)

        response = self.client.post(self.url, {"quantity": 2}, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        disposed_count = BookItem.objects.filter(
            pk__in=[i.pk for i in items], status=BookItem.Status.DISPOSED
        ).count()
        self.assertEqual(disposed_count, 2)

    @tag("UT-EDIT-SVC-012")
    def test_shows_error_on_insufficient_stock(self):
        """テスト12: 在庫不足時、quantityフィールドにエラーが表示される"""
        self._create_book_items(self.location_a, BookItem.Status.AVAILABLE, 1)

        response = self.client.post(self.url, {"quantity": 5}, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        form = response.context["decrease_form"]
        self.assertIn("quantity", form.errors)
        # 何も変更されていないことの確認
        self.assertEqual(
            BookItem.objects.filter(
                book=self.book, status=BookItem.Status.AVAILABLE
            ).count(),
            1,
        )


class BookUpdateViewTests(BookEditTestCaseBase):
    """views.py: book_update_view のテスト。"""

    def setUp(self):
        super().setUp()
        self._login_with_permissions(["change_book"])
        self.url = reverse("management:book_update", args=[self.book.id])

    @tag("UT-EDIT-SVC-013")
    def test_updates_book_with_valid_input(self):
        """テスト13: 有効な入力でBookの書誌情報が更新される"""
        response = self.client.post(
            self.url,
            {
                "title": "更新後タイトル",
                "author": "更新後著者",
                "publisher": "更新後出版社",
                "published_date": "",
                "thumbnail_url": "",
                "category": "",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.book.refresh_from_db()
        self.assertEqual(self.book.title, "更新後タイトル")
        self.assertEqual(self.book.author, "更新後著者")

    @tag("UT-EDIT-SVC-014")
    def test_does_not_update_with_invalid_input(self):
        """テスト14: 無効な入力(必須項目欠如)では更新されない"""
        original_title = self.book.title

        response = self.client.post(
            self.url,
            {
                "title": "",  # 必須項目を空にする
                "author": "更新後著者",
                "publisher": "更新後出版社",
                "published_date": "",
                "thumbnail_url": "",
                "category": "",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["book_form"]
        self.assertIn("title", form.errors)
        self.book.refresh_from_db()
        self.assertEqual(self.book.title, original_title)
