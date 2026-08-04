from django.contrib import admin
from .models import Book, BookItem, Location, Category


# Register your models here.
@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "author",
        "isbn",
        "category",
    )
    search_fields = ("title", "author", "isbn")


@admin.register(BookItem)
class BookItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "book",
        "location",
        "status",
    )
    list_filter = ("status", "location")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
    )


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
    )
