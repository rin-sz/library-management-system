from django.shortcuts import render
from django.views.generic import ListView, DetailView
from django.db.models import Q
from django.contrib.auth.mixins import LoginRequiredMixin

from .models import Book, BookItem, Category
from loan.forms import BorrowForm
from loan.models import Reservation, ReservationStatus


# Create your views here.
class BooklistView(LoginRequiredMixin, ListView):
    model = Book
    template_name = "books/book_list.html"
    context_object_name = "books"
    paginate_by = 20

    def get_queryset(self):
        queryset = Book.objects.filter(
            items__status__in=[
                BookItem.Status.AVAILABLE,
                BookItem.Status.LOANED,
                BookItem.Status.RESERVED,
            ]
        ).distinct()

        query = self.request.GET.get("q", "").strip()
        category_id = self.request.GET.get("category", "").strip()

        if query:
            queryset = queryset.filter(
                Q(title__icontains=query) | Q(author__icontains=query)
            )

        if category_id.isdigit():
            queryset = queryset.filter(category_id=category_id)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["page_range"] = context["page_obj"].paginator.get_elided_page_range(
            number=context["page_obj"].number,
            on_each_side=2,
            on_ends=1,
        )

        context["query"] = self.request.GET.get("q", "").strip()
        context["categories"] = Category.objects.all()
        context["selected_category"] = self.request.GET.get("category", "")

        querystring = self.request.GET.copy()
        querystring.pop("page", None)
        context["querystring"] = querystring.urlencode()

        return context


class BookDetailView(LoginRequiredMixin, DetailView):
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
