from django.urls import path
from . import views

app_name = "management"

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("books/", views.BookListView.as_view(), name="book_list"),
    path("books/register/", views.book_register_view, name="book_register"),
    path(
        "books/register/search/", views.book_isbn_search_view, name="book_isbn_search"
    ),
    path("books/register/create/", views.book_create_view, name="book_create"),
    path(
        "books/register/items/<int:book_id>/create/",
        views.book_item_create_view,
        name="book_item_create",
    ),
    path("books/<int:book_id>/edit/", views.book_edit_view, name="book_edit"),
    path("books/<int:book_id>/update/", views.book_update_view, name="book_update"),
    path(
        "books/<int:book_id>/stock/increase/",
        views.book_item_increase_view,
        name="book_item_increase",
    ),
    path(
        "books/<int:book_id>/stock/decrease/",
        views.book_item_decrease_view,
        name="book_item_decrease",
    ),
]
