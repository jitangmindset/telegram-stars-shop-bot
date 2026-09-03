from pathlib import Path
from decimal import Decimal

from bot.database import OrderRepository


def test_order_lifecycle(tmp_path: Path) -> None:
    repository = OrderRepository(tmp_path / "orders.db")
    repository.initialize()

    order = repository.create(
        buyer_id=42,
        buyer_username="buyer",
        recipient_username="@recipient",
        stars=100,
        amount_rub="200.00",
        receipt_file_id="file-id",
        receipt_type="photo",
    )

    assert order.id == 1
    assert order.status == "pending"
    assert repository.set_status(order.id, "completed") is False
    assert repository.set_status(order.id, "approved") is True
    assert repository.set_status(order.id, "approved") is False
    assert repository.set_status(order.id, "completed") is True
    assert repository.set_status(order.id, "rejected") is False
    assert repository.get(order.id).status == "completed"


def test_receipt_can_be_rejected_before_approval(tmp_path: Path) -> None:
    repository = OrderRepository(tmp_path / "orders.db")
    repository.initialize()
    order = repository.create(
        buyer_id=42,
        buyer_username=None,
        recipient_username="@recipient",
        stars=50,
        amount_rub="100.00",
        receipt_file_id="photo-id",
        receipt_type="photo",
    )

    assert repository.set_status(order.id, "rejected") is True
    assert repository.set_status(order.id, "approved") is False
    assert repository.get(order.id).status == "rejected"


def test_manager_access(tmp_path: Path) -> None:
    repository = OrderRepository(tmp_path / "orders.db")
    repository.initialize()

    assert repository.add_manager(100) is True
    assert repository.add_manager(100) is False
    assert repository.list_manager_ids() == (100,)
    assert repository.is_staff(100, owner_id=1) is True
    assert repository.is_staff(1, owner_id=1) is True
    assert repository.is_staff(999, owner_id=1) is False
    assert repository.remove_manager(100) is True
    assert repository.remove_manager(100) is False


def test_shop_settings_persist(tmp_path: Path) -> None:
    database_path = tmp_path / "orders.db"
    repository = OrderRepository(database_path)
    repository.initialize()

    assert repository.get_price_per_star(Decimal("2.00")) == Decimal("2.00")
    assert repository.get_star_presets() == (50, 100, 500)
    assert repository.get_payment_details("Старые реквизиты") == "Старые реквизиты"
    assert repository.get_star_limits(50, 100000) == (50, 100000)

    repository.set_price_per_star(Decimal("1.75"))
    repository.set_star_presets((25, 250, 1000))
    repository.set_payment_details("Новые реквизиты\nВторая строка")
    repository.set_star_limits(25, 250000)

    reopened = OrderRepository(database_path)
    reopened.initialize()
    assert reopened.get_price_per_star(Decimal("2.00")) == Decimal("1.75")
    assert reopened.get_star_presets() == (25, 250, 1000)
    assert reopened.get_payment_details("Старые") == "Новые реквизиты\nВторая строка"
    assert reopened.get_star_limits(50, 100000) == (25, 250000)
