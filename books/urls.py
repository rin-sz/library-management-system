from django.urls import path
from .views import BookDetailView, BooklistView

app_name = "books"

urlpatterns = [
    path("", BooklistView.as_view(), name="book_list"),
    path("<int:pk>/", BookDetailView.as_view(), name="book_detail"),
]
