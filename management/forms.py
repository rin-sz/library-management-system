from django import forms
from books.models import Book, Location


class BookRegisterForm(forms.ModelForm):
    """新規ISBN登録用フォーム。Bookの各フィールドに加えて、
    蔵書登録に必要な保管場所・冊数をモデル外フィールドとして持つ。
    """

    location = forms.ModelChoiceField(
        queryset=Location.objects.all(),
        label="保管場所",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    quantity = forms.IntegerField(
        label="冊数",
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    class Meta:
        model = Book
        fields = [
            "isbn",
            "title",
            "author",
            "publisher",
            "published_date",
            "thumbnail_url",
            "category",
        ]
        widgets = {
            "isbn": forms.TextInput(attrs={"class": "form-control"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "author": forms.TextInput(attrs={"class": "form-control"}),
            "publisher": forms.TextInput(attrs={"class": "form-control"}),
            "published_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "thumbnail_url": forms.HiddenInput(),
            "category": forms.Select(attrs={"class": "form-select"}),
        }


class BookItemAddForm(forms.Form):
    """既存Bookに対して蔵書(BookItem)を追加登録するためのフォーム。

    Bookモデル自体は編集しないため、ModelFormではなく単純なFormとして
    location・quantityの2フィールドのみを持つ。
    """

    location = forms.ModelChoiceField(
        queryset=Location.objects.all(),
        label="保管場所",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    quantity = forms.IntegerField(
        label="追加冊数",
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )


class BookUpdateForm(forms.ModelForm):
    """既存Bookの書誌情報を編集するためのフォーム。

    isbnは書籍を一意に識別する項目であり、登録フロー側の重複判定の前提
    となっているため、編集対象から意図的に除外する。
    """

    class Meta:
        model = Book
        fields = [
            "title",
            "author",
            "publisher",
            "published_date",
            "thumbnail_url",
            "category",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "author": forms.TextInput(attrs={"class": "form-control"}),
            "publisher": forms.TextInput(attrs={"class": "form-control"}),
            "published_date": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}
            ),
            "thumbnail_url": forms.URLInput(attrs={"class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-select"}),
        }


class BookItemRemoveForm(forms.Form):
    """既存Bookの蔵書(BookItem)を減らすためのフォーム。quantityのみで完結する。"""

    quantity = forms.IntegerField(
        label="減らす冊数",
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )


class BookItemIncreaseQuantityForm(forms.Form):
    """既に在庫がある本に、蔵書を追加するためのフォーム。

    locationは既存在庫の場所に固定されるため、quantityのみを受け取る。
    """

    quantity = forms.IntegerField(
        label="追加冊数",
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
