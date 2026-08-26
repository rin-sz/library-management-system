from django.urls import path
from .views import BookDetailview, Booklistview

app_name = "books"

urlpatterns = [
    path("", Booklistview.as_view(), name="book_list"),
    path("<int:pk>/", BookDetailview.as_view(), name="book_detail"),
]
