from django.urls import path
from . import views

app_name = "management"

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("books/", views.BookListView.as_view(), name="book_list"),
]
