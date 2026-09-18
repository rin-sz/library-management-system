from django.shortcuts import render
from django.views.generic import ListView, DetailView
from .models import Book, BookItem
from loan.forms import BorrowForm
from loan.models import Reservation, ReservationStatus


# Create your views here.
class BooklistView(ListView):
    model = Book
    template_name = "books/book_list.html"
    context_object_name = "books"

    def get_queryset(self):
        return Book.objects.filter(
            items__status__in=[
                BookItem.Status.AVAILABLE,
                BookItem.Status.LOANED,
                BookItem.Status.RESERVED,
            ]
        ).distinct()


class BookDetailView(DetailView):
    model = Book
    template_name = "books/book_detail.html"
    context_object_name = "book"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["form"] = BorrowForm()

        # 貸出可能な蔵書を1冊取得
        context["available_item"] = self.object.items.filter(
            status=BookItem.Status.AVAILABLE
        ).first()

        user_reservation = None
        if self.request.user.is_authenticated:
            user_reservation = Reservation.objects.filter(
                user=self.request.user,
                book=self.object,
                status__in=[
                    ReservationStatus.WAITING,
                    ReservationStatus.READY,
                ],
            ).first()

        context["user_reservation"] = user_reservation

        return context
