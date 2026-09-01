from django import forms
from django.utils import timezone


class BorrowForm(forms.Form):
    book_item_id = forms.IntegerField(widget=forms.HiddenInput())
    start_date = forms.DateField(
        label="貸出開始日",
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "class": "form-control form-control-sm",
                "min": timezone.localdate().isoformat(),
            }
        ),
        initial=timezone.localdate,
    )


class ReturnForm(forms.Form):
    loan_id = forms.IntegerField(widget=forms.HiddenInput())


class ReserveForm(forms.Form):
    book_id = forms.IntegerField(widget=forms.HiddenInput())
