from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone


class BorrowForm(forms.Form):
    book_item_id = forms.IntegerField(widget=forms.HiddenInput())
    start_date = forms.DateField(
        label="貸出開始日",
        widget=forms.DateInput(
            attrs={"type": "date", "class": "form-contorol form-contorol-sm"}
        ),
        initial=timezone.localdate,
    )


class ReturnForm(forms.Form):
    loan_id = forms.IntegerField(widget=forms.HiddenInput())
