from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Order:
    id: int
    buyer_id: int
    buyer_username: str | None
    recipient_username: str
    stars: int
    amount_rub: str
    receipt_file_id: str
    receipt_type: str
    status: str
    created_at: str


class OrderRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    buyer_id INTEGER NOT NULL,
                    buyer_username TEXT,
                    recipient_username TEXT NOT NULL,
                    stars INTEGER NOT NULL,
                    amount_rub TEXT NOT NULL,
                    receipt_file_id TEXT NOT NULL,
                    receipt_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS managers (
                    user_id INTEGER PRIMARY KEY,
                    added_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

    def get_setting(self, key: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return str(row["value"]) if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def get_price_per_star(self, default: Decimal) -> Decimal:
        value = self.get_setting("price_per_star_rub")
        return Decimal(value) if value is not None else default

    def set_price_per_star(self, value: Decimal) -> None:
        self.set_setting("price_per_star_rub", str(value.quantize(Decimal("0.01"))))

    def get_payment_details(self, default: str) -> str:
        value = self.get_setting("payment_details")
        return value if value is not None else default

    def set_payment_details(self, value: str) -> None:
        self.set_setting("payment_details", value)

    def get_star_limits(self, default_min: int, default_max: int) -> tuple[int, int]:
        min_value = self.get_setting("min_stars")
        max_value = self.get_setting("max_stars")
        return (
            int(min_value) if min_value is not None else default_min,
            int(max_value) if max_value is not None else default_max,
        )

    def set_star_limits(self, min_stars: int, max_stars: int) -> None:
        self.set_setting("min_stars", str(min_stars))
        self.set_setting("max_stars", str(max_stars))

    def get_star_presets(self, default: tuple[int, ...] = (50, 100, 500)) -> tuple[int, ...]:
        value = self.get_setting("star_presets")
        if value is None:
            return default
        return tuple(int(item) for item in value.split(","))

    def set_star_presets(self, values: tuple[int, ...]) -> None:
        self.set_setting("star_presets", ",".join(str(value) for value in values))

    def add_manager(self, user_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO managers (user_id, added_at) VALUES (?, ?)",
                (user_id, datetime.now(UTC).isoformat(timespec="seconds")),
            )
            return cursor.rowcount == 1

    def remove_manager(self, user_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM managers WHERE user_id = ?", (user_id,)
            )
            return cursor.rowcount == 1

    def list_manager_ids(self) -> tuple[int, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT user_id FROM managers ORDER BY added_at, user_id"
            ).fetchall()
        return tuple(int(row["user_id"]) for row in rows)

    def is_staff(self, user_id: int, owner_id: int) -> bool:
        return user_id == owner_id or user_id in self.list_manager_ids()

    def create(
        self,
        *,
        buyer_id: int,
        buyer_username: str | None,
        recipient_username: str,
        stars: int,
        amount_rub: str,
        receipt_file_id: str,
        receipt_type: str,
    ) -> Order:
        created_at = datetime.now(UTC).isoformat(timespec="seconds")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO orders (
                    buyer_id, buyer_username, recipient_username, stars,
                    amount_rub, receipt_file_id, receipt_type, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    buyer_id,
                    buyer_username,
                    recipient_username,
                    stars,
                    amount_rub,
                    receipt_file_id,
                    receipt_type,
                    created_at,
                ),
            )
            order_id = int(cursor.lastrowid)

        order = self.get(order_id)
        if order is None:  # pragma: no cover - defensive check
            raise RuntimeError("Не удалось прочитать созданную заявку")
        return order

    def get(self, order_id: int) -> Order | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM orders WHERE id = ?", (order_id,)
            ).fetchone()
        return Order(**dict(row)) if row else None

    def set_status(self, order_id: int, status: str) -> bool:
        transitions = {
            "approved": ("pending",),
            "completed": ("approved",),
            "rejected": ("pending", "approved"),
        }
        if status not in transitions:
            raise ValueError("Недопустимый статус заявки")
        allowed_statuses = transitions[status]
        placeholders = ", ".join("?" for _ in allowed_statuses)
        with self._connect() as connection:
            cursor = connection.execute(
                f"""
                UPDATE orders
                SET status = ?
                WHERE id = ? AND status IN ({placeholders})
                """,
                (status, order_id, *allowed_statuses),
            )
            return cursor.rowcount == 1
