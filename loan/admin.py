from django.contrib import admin
from .models import Loan, Reservation


# Register your models here.
@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "book_item",
        "status",
        "loaned_at",
        "returned_at",
        "due_date",
    )
    list_filter = ("status",)
    search_fields = (
        "user__username",
        "book_item__book__title",
    )


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "book",
        "status",
        "reserved_at",
    )
    list_filter = ("status",)
    search_fields = (
        "user__username",
        "book__title",
    )
