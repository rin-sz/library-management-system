from django.db import models
from django.urls import reverse


# Create your models here.
class Category(models.Model):
    name = models.CharField("カテゴリ名", max_length=50, unique=True)

    class Meta:
        verbose_name = "カテゴリ"
        verbose_name_plural = "カテゴリ一覧"

    def __str__(self):
        return self.name


class Location(models.Model):
    name = models.CharField("保管場所名", max_length=50)

    class Meta:
        verbose_name = "保管場所"
        verbose_name_plural = "保管場所一覧"

    def __str__(self):
        return self.name


class Book(models.Model):
    isbn = models.CharField("ISBN", max_length=13, unique=True)

    title = models.CharField("タイトル", max_length=255)

    author = models.CharField("著者名", max_length=255)

    publisher = models.CharField("出版社名", max_length=100)

    published_date = models.DateField("出版日", null=True, blank=True)

    thumbnail_url = models.URLField("表紙画像URL", max_length=500, blank=True)

    category = models.ForeignKey(
        Category,
        verbose_name="カテゴリID",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "書誌情報"
        verbose_name_plural = "書誌情報一覧"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("books:book_detail", kwargs={"pk": self.pk})

    @property
    def has_available_items(self) -> bool:
        """貸出可能な蔵書（AVAILABLE）が1冊でも存在するかどうか"""
        return self.items.filter(status=BookItem.Status.AVAILABLE).exists()


class BookItem(models.Model):

    class Status(models.IntegerChoices):
        AVAILABLE = 1, "貸出可能"
        LOANED = 2, "貸出中"
        RESERVED = 3, "取り置き中"

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="items")

    location = models.ForeignKey(Location, on_delete=models.PROTECT)

    status = models.IntegerField(
        "蔵書状況", choices=Status.choices, default=Status.AVAILABLE
    )

    class Meta:
        verbose_name = "蔵書"
        verbose_name_plural = "蔵書一覧"

    def __str__(self):
        return f"{self.book.title} -{self.location.name}"

    @property
    def is_available(self):
        return self.status == self.Status.AVAILABLE

    @property
    def is_reserved(self) -> bool:
        return self.status == self.Status.RESERVED

    @property
    def is_loaned(self) -> bool:
        return self.status == self.Status.LOANED
