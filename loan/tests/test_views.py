from datetime import timedelta
from django.contrib.auth import get_user_model
from django.conf import settings
from django.contrib.messages import get_messages
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from loan.models import Loan
from books.models import Book, BookItem, Location

User = get_user_model()


class BorrowViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="password123"
        )
        self.location = Location.objects.create(name="中央図書館")
        self.book = Book.objects.create(title="テスト対象書籍")
        self.book_item = BookItem.objects.create(
            book=self.book,
            status=BookItem.Status.AVAILABLE,
            location=self.location,
        )
        self.url = reverse("loan:borrow")

        self.success_url = reverse("loan:my_loans")

    @tag("UT-LOAN-VIEW-001")
    def test_borrow_view_requires_login(self):
        """[UT-LOAN-VIEW-001] 未ログインユーザーはログイン画面へリダイレクトされるか"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        # LOGIN_URLへリダイレクトされることを確認
        self.assertIn(settings.LOGIN_URL, response.url)

    @tag("UT-LOAN-VIEW-002")
    def test_borrow_view_get_redirects_to_book_list(self):
        """[UT-LOAN-VIEW-002] ログイン済ユーザーのGETアクセスで書籍一覧へリダイレクトされるか"""
        self.client.login(username="testuser", password="password123")
        response = self.client.get(self.url)

        self.assertRedirects(response, reverse("books:book_list"))

    @tag("UT-LOAN-VIEW-003")
    def test_borrow_view_post_invalid_form(self):
        """[UT-LOAN-VIEW-003] 不正なフォームデータ（空データ）送信時にリダイレクトとエラーメッセージがセットされるか"""
        self.client.login(username="testuser", password="password123")
        response = self.client.post(self.url, data={})

        self.assertRedirects(response, reverse("books:book_list"))

        # エラーメッセージがセットされているか検証
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any(m.level_tag == "error" for m in messages))

    @tag("UT-LOAN-VIEW-004")
    def test_borrow_view_post_non_existent_book_item_returns_404(self):
        """[UT-LOAN-VIEW-004] 存在しない book_item_id 指定時に404が返るか"""
        self.client.login(username="testuser", password="password123")
        today = timezone.localdate().strftime("%Y-%m-%d")

        response = self.client.post(
            self.url, data={"book_item_id": 99999, "start_date": today}
        )

        self.assertEqual(response.status_code, 404)

    @tag("UT-LOAN-VIEW-005")
    def test_borrow_view_post_success(self):
        """[UT-LOAN-VIEW-005] 貸出成功時に貸出完了画面へリダイレクトされるか"""
        self.client.login(username="testuser", password="password123")
        today = timezone.localdate().strftime("%Y-%m-%d")

        response = self.client.post(
            self.url, data={"book_item_id": self.book_item.id, "start_date": today}
        )

        # 作成された Loan レコードからリダイレクト先のURLを確認
        loan = Loan.objects.get(user__username="testuser", book_item=self.book_item)

        self.assertRedirects(
            response, reverse("loan:borrow_success", kwargs={"pk": loan.pk})
        )

    @tag("UT-LOAN-VIEW-006")
    def test_borrow_view_post_validation_error_from_service(self):
        """[UT-LOAN-VIEW-006] サービス層でValidationErrorが発生した場合に詳細画面へリダイレクトされエラーが表示されるか"""
        self.client.login(username="testuser", password="password123")

        # 事前に蔵書を貸出中にしてサービス層でエラーが出る状態を作る
        self.book_item.status = BookItem.Status.LOANED
        self.book_item.save()

        today = timezone.localdate().strftime("%Y-%m-%d")
        response = self.client.post(
            self.url, data={"book_item_id": self.book_item.id, "start_date": today}
        )

        expected_url = reverse("books:book_detail", kwargs={"pk": self.book.pk})
        self.assertRedirects(response, expected_url)

        # エラーメッセージがセットされていることを確認
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any(m.level_tag == "error" for m in messages))
