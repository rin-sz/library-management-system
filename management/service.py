from books.models import Book, BookItem, Location


def increase_stock(book: Book, location: Location, quantity: int) -> None:
    """指定したlocationの蔵書をquantity件増やす。

    新規に作成されるBookItemはデフォルトのStatus(AVAILABLE)で登録される。
    """
    BookItem.objects.bulk_create(
        [BookItem(book=book, location=location) for _ in range(quantity)]
    )


# 将来実装予定:
#
# def decrease_stock(book: Book, location: Location, quantity: int) -> None:
#     """指定したlocationの蔵書をquantity件減らす。
#
#     AVAILABLE状態の個体のみを削除対象とし、LOANED/RESERVED状態の個体は
#     削除対象から除外する。対象個体がquantity件に満たない場合はエラーとする。
#
#     書籍情報の編集・削除機能を実装する際に追加予定。
#     """
#     ...
