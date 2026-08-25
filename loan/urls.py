from django.urls import path
from . import views

app_name = "loan"

urlpatterns = [
    path("my-loans/", views.my_loans_view, name="my_loans"),
    path("borrow/", views.borrow_view, name="borrow"),
    path("borrow/success/<int:pk>/", views.borrow_success_view, name="borrow_success"),
    path("return/", views.return_view, name="return"),
]
