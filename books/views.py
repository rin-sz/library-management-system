from django.shortcuts import render
from django.views.generic import ListView, DetailView
from .models import Book


# Create your views here.
class Booklistview(ListView):
    model = Book
    template_name = "books/book_list.html"
    context_object_name = "books"


class BookDetailview(DetailView):
    model = Book
    template_name = "books/book_detail.html"
    context_object_name = "book"
