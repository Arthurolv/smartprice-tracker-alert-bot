"""Extração de preços reais e geração de uma série fictícia reproduzível."""

from dataclasses import dataclass
from datetime import date, timedelta
import json
from pathlib import Path
from time import sleep

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


STEAM_DETAILS = "https://store.steampowered.com/api/appdetails"


@dataclass(frozen=True)
class Product:
    app_id: int
    target_cents: int

    @property
    def url(self) -> str:
        return f"https://store.steampowered.com/app/{self.app_id}/?cc=br"


@dataclass(frozen=True)
class Quote:
    app_id: int
    name: str
    day: date
    cents: int
    currency: str


def load_products(path: Path) -> list[Product]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError("O catálogo deve conter uma lista de produtos.")
    products = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Cada item do catálogo deve ser um objeto JSON.")
        app_id = row.get("app_id")
        target = row.get("target_cents")
        if type(app_id) is not int or not 0 < app_id <= 2**32 - 1:
            raise ValueError("app_id deve ser um identificador Steam inteiro positivo.")
        if type(target) is not int or not 0 <= target <= 2**31 - 1:
            raise ValueError("target_cents deve ser um inteiro não negativo em centavos.")
        if app_id in seen:
            raise ValueError(f"app_id duplicado no catálogo: {app_id}.")
        products.append(Product(app_id, target))
        seen.add(app_id)
    return products


def collect_steam(products: list[Product], day: date) -> tuple[list[Quote], dict[int, str]]:
    retry = Retry(
        total=2, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods={"GET"}, respect_retry_after_header=True,
    )
    quotes = []
    failures = {}
    with requests.Session() as session:
        session.mount("https://", HTTPAdapter(max_retries=retry))
        for index, product in enumerate(products):
            if index:
                sleep(1)
            try:
                response = session.get(
                    STEAM_DETAILS,
                    params={"appids": product.app_id, "cc": "br", "l": "portuguese"},
                    timeout=(5, 15),
                )
                response.raise_for_status()
                app = response.json()[str(product.app_id)]
                if app["success"] is not True:
                    raise ValueError("a Steam não retornou dados do jogo")
                details = app["data"]
                price = details.get("price_overview")
                if not isinstance(price, dict):
                    raise ValueError("sem preço de compra publicado")
                cents = price["final"]
                if type(cents) is not int:
                    raise ValueError("preço em centavos inválido")
                quotes.append(Quote(product.app_id, details["name"], day, cents, price["currency"]))
            except requests.RequestException as exc:
                failures[product.app_id] = f"requisição Steam falhou ({type(exc).__name__})"
            except ValueError as exc:
                failures[product.app_id] = str(exc)
            except (KeyError, TypeError, AttributeError):
                failures[product.app_id] = "formato inesperado na resposta Steam"
    return quotes, failures


def demo_data(day: date) -> tuple[list[Product], list[Quote]]:
    # Todos os dias anteriores ao último têm variação e promoções pontuais.
    scenarios = [
        (Product(1, 3500), "Aventura Pixel", 5990, 2990),
        (Product(2, 3500), "Fazenda Solar", 4990, 4990),
        (Product(3, 4500), "Corrida Lunar", 6990, 8990),
    ]
    quotes = []
    for product, name, base, current in scenarios:
        for offset in range(89, -1, -1):
            price = base + ((offset * 7) % 9 - 4) * 90
            if offset and offset % 21 in (1, 2, 3):
                price -= 1000
            quotes.append(
                Quote(product.app_id, name, day - timedelta(days=offset), current if offset == 0 else price, "BRL")
            )
    return [item[0] for item in scenarios], quotes
