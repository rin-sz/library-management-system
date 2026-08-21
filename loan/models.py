from django.db import models
from django.conf import settings
from django.utils import timezone

from books.models import BookItem
from books.models import Book


# Create your models here.
class LoanStatus(models.IntegerChoices):
    BORROWED = 1, "貸出中"
    RETURNED = 2, "返却済み"


class Loan(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name="利用者",
        related_name="loans",
    )

    book_item = models.ForeignKey(
        BookItem, on_delete=models.PROTECT, verbose_name="蔵書", related_name="loans"
    )

    loaned_at = models.DateTimeField(default=timezone.now, verbose_name="貸出日時")

    due_date = models.DateField(verbose_name="返却期限日")

    returned_at = models.DateTimeField(null=True, blank=True, verbose_name="返却日時")

    status = models.IntegerField(
        choices=LoanStatus.choices,
        default=LoanStatus.BORROWED,
        verbose_name="ステータス",
        db_index=True,
    )

    class Meta:
        verbose_name = "貸出履歴"
        verbose_name_plural = "貸出履歴"

        ordering = ["-loaned_at"]

        constraints = [
            # 同じ蔵書（BookItem）が同時に二重貸出されるのを防止する制約
            # ※ 返却済み（RETURNED）になれば制約対象外となるため、過去の貸出履歴は同一蔵書でも複数保持可能
            models.UniqueConstraint(
                fields=["book_item"],
                condition=models.Q(status=LoanStatus.BORROWED),
                name="unique_active_loan_per_book_item",
            )
        ]

    def __str__(self):
        return f"{self.user} - {self.book_item} ({self.get_status_display()})"


class ReservationStatus(models.IntegerChoices):
    WAITING = 1, "予約中"
    READY = 2, "貸出可能"
    COMPLETED = 3, "貸出完了"
    CANCELED = 4, "キャンセル"


class Reservation(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reservations",
        verbose_name="利用者",
    )

    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name="reservations",
        verbose_name="書籍",
    )

    status = models.IntegerField(
        choices=ReservationStatus.choices,
        default=ReservationStatus.WAITING,
        verbose_name="予約状況",
        db_index=True,
    )

    reserved_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="予約日時",
    )

    def __str__(self):
        return f"{self.user} - {self.book} ({self.get_status_display()})"

    class Meta:
        ordering = ["-reserved_at"]

        verbose_name = "予約"
        verbose_name_plural = "予約"

        constraints = [
            # 同一ユーザーが同じ書籍に対して有効な予約を複数作成するのを防止する
            # WAITING・READY を有効な予約とし、COMPLETED・CANCELED は履歴として扱うため再予約を許可する。
            models.UniqueConstraint(
                fields=["user", "book"],
                condition=models.Q(
                    status__in=[ReservationStatus.WAITING, ReservationStatus.READY]
                ),
                name="unique_active_reservation_per_user_and_book",
            )
        ]
