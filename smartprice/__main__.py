"""Executa o pipeline com `python -m smartprice`."""

import argparse
from contextlib import closing
from datetime import datetime
import logging
import os
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from .analysis import analyze, brl
from .reporting import DeliveryError, render_chart, send_discord
from .sources import collect_steam, demo_data, load_products
from .storage import open_database, read_history, save_quotes, send_once
from .transform import clean_quotes


ROOT = Path(__file__).resolve().parent.parent
LOG = logging.getLogger("smartprice")


def run(args: argparse.Namespace) -> int:
    load_dotenv(ROOT / ".env")
    day = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    day_text = day.isoformat()
    mode = "demo" if args.demo else "steam"
    database = args.db or ROOT / "data" / ("demo.sqlite3" if args.demo else "prices.sqlite3")
    chart_dir = args.chart_dir or ROOT / "charts" / mode
    webhook = "" if args.demo else os.getenv("DISCORD_WEBHOOK_URL", "").strip()

    if args.demo:
        products, raw = demo_data(day)
        failures = {}
    else:
        products = load_products(args.products)
        raw, failures = collect_steam(products, day)

    quotes, rejected = clean_quotes(raw)
    for app_id in rejected:
        failures[app_id] = "observação rejeitada durante a validação"
    for app_id, reason in failures.items():
        LOG.warning("Produto %d: %s.", app_id, reason)
    if quotes.empty:
        LOG.error("Nenhuma observação válida foi coletada.")
        return 1

    today = quotes.loc[quotes["day"].eq(day_text)].set_index("app_id")
    failed = bool(failures)
    with closing(open_database(database)) as connection:
        save_quotes(connection, quotes, products)
        LOG.info("%d observações processadas em %s.", len(quotes), database)
        for product in products:
            if product.app_id not in today.index:
                continue
            name = today.at[product.app_id, "name"]
            history = read_history(connection, product.app_id, day_text)
            result, average = analyze(history, product.target_cents)
            chart = chart_dir / f"{product.app_id}.png"
            render_chart(name, history, average, result, product.target_cents, chart, args.demo)

            mean = "sem observações anteriores" if result.mean_30d is None else brl(result.mean_30d)
            LOG.info(
                "%s | %s | atual %s | média 30d %s (%d obs.) | mínimo %s | gráfico %s",
                name, result.classification, brl(result.current), mean,
                result.samples_30d, brl(result.minimum), chart,
            )
            if result.episode_start is None:
                continue
            if not webhook:
                LOG.info("Preço-alvo atingido para %s (%s). Envio desativado.", name, brl(product.target_cents))
                continue
            try:
                sent = send_once(
                    connection, product, result.episode_start,
                    lambda: send_discord(webhook, product, name, day_text, result, chart),
                )
                LOG.info("%s | %s.", name, "Alerta publicado" if sent else "Alerta já registrado")
            except DeliveryError as exc:
                LOG.error("Produto %d: %s", product.app_id, exc)
                failed = True
    return int(failed)


def main() -> int:
    parser = argparse.ArgumentParser(description="Coleta e compara preços diários da Steam no Brasil.")
    parser.add_argument("--demo", action="store_true", help="Gera 90 dias fictícios e simula os alertas.")
    parser.add_argument("--products", type=Path, default=ROOT / "config" / "products.json")
    parser.add_argument("--db", type=Path, help="Caminho alternativo para o banco SQLite.")
    parser.add_argument("--chart-dir", type=Path, help="Diretório alternativo para os gráficos.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        return run(args)
    except (OSError, ValueError, sqlite3.Error) as exc:
        LOG.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
