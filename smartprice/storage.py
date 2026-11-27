"""Persistência em SQLite. Preços são armazenados em centavos inteiros."""

from collections.abc import Callable
from pathlib import Path
import sqlite3

import pandas as pd

from .sources import Product


def open_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
    return connection


def save_quotes(connection: sqlite3.Connection, quotes: pd.DataFrame, products: list[Product]) -> None:
    catalog = {product.app_id: product for product in products}
    latest = quotes.drop_duplicates("app_id", keep="last")
    with connection:
        connection.executemany(
            """
            INSERT INTO products (app_id, name, currency, url, target_cents)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (app_id) DO UPDATE SET name = excluded.name,
                currency = excluded.currency, url = excluded.url, target_cents = excluded.target_cents
            WHERE products.name <> excluded.name OR products.target_cents <> excluded.target_cents
            """,
            (
                (row.app_id, row.name, row.currency, catalog[row.app_id].url, catalog[row.app_id].target_cents)
                for row in latest.itertuples(index=False)
            ),
        )
        connection.executemany(
            """
            INSERT INTO price_history (app_id, day, price_cents) VALUES (?, ?, ?)
            ON CONFLICT (app_id, day) DO UPDATE SET price_cents = excluded.price_cents
            WHERE price_history.price_cents <> excluded.price_cents
            """,
            ((row.app_id, row.day, row.cents) for row in quotes.itertuples(index=False)),
        )


def read_history(connection: sqlite3.Connection, app_id: int, through_day: str) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT day, price_cents FROM price_history WHERE app_id = ? AND day <= ? ORDER BY day
        """,
        connection,
        params=(app_id, through_day),
        parse_dates=["day"],
        index_col="day",
    )


def send_once(
    connection: sqlite3.Connection, product: Product, episode_start: str, deliver: Callable[[], None]
) -> bool:
    with connection:
        # Reserva a chave antes de enviar. Uma falha no envio desfaz a reserva.
        cursor = connection.execute(
            """
            INSERT INTO sent_alerts (app_id, target_cents, episode_start) VALUES (?, ?, ?)
            ON CONFLICT (app_id, target_cents, episode_start) DO NOTHING
            """,
            (product.app_id, product.target_cents, episode_start),
        )
        if cursor.rowcount == 0:
            return False
        deliver()
    return True
