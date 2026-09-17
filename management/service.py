from books.models import Book, BookItem, Location


def increase_stock(book: Book, location: Location, quantity: int) -> None:
    """指定したlocationの蔵書をquantity件増やす。

    新規に作成されるBookItemはデフォルトのStatus(AVAILABLE)で登録される。
    """
    BookItem.objects.bulk_create(
        [BookItem(book=book, location=location) for _ in range(quantity)]
    )


def decrease_stock(book: Book, quantity: int) -> None:
    """bookのAVAILABLE状態の蔵書をquantity件、廃棄済み(DISPOSED)状態にする。（論理削除）
    LOANED・RESERVED状態の個体は対象から除外する。
    削除可能な個体(AVAILABLE状態)がquantity件に満たない場合はValueErrorを送出する。
    """
    available_items = BookItem.objects.filter(
        book=book,
        status=BookItem.Status.AVAILABLE,
    )
    available_count = available_items.count()

    if available_count < quantity:
        raise ValueError(
            f"貸出可能な蔵書が不足しています(貸出可能: {available_count}件, 指定: {quantity}件)"
        )

    target_ids = list(available_items.values_list("pk", flat=True)[:quantity])
    BookItem.objects.filter(pk__in=target_ids).update(status=BookItem.Status.DISPOSED)
