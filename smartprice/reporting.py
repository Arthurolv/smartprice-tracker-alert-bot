"""Renderização local e publicação de alertas no Discord."""

import json
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.dates import AutoDateLocator, ConciseDateFormatter
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter
import pandas as pd
import requests

from .analysis import Analysis, brl
from .sources import Product


class DeliveryError(Exception):
    """Falha de entrega com uma mensagem que não expõe a URL do webhook."""


def render_chart(
    name: str, history: pd.DataFrame, average: pd.Series, result: Analysis,
    target: int, destination: Path, demo: bool,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure = Figure(figsize=(10, 5.2), layout="constrained", facecolor="#ffffff")
    FigureCanvasAgg(figure)
    axis = figure.subplots()
    # Dias ausentes interrompem a curva de preços e mantêm as lacunas visíveis.
    daily = history["price_cents"].asfreq("D")
    axis.plot(daily.index, daily / 100, color="#12656c", linewidth=2, label="Preço observado")
    axis.plot(average.index, average / 100, color="#98430a", linestyle="--", label="Média móvel de 30 dias")
    axis.axhline(target / 100, color="#66758b", linewidth=1.2, linestyle=":", label="Preço-alvo")
    axis.scatter(history.index[-1], result.current / 100, color="#12656c", edgecolor="white", s=64, zorder=4)
    axis.set_title(name.replace("$", r"\$"), loc="left", fontsize=17, fontweight="bold", pad=16)
    axis.set_ylabel("Preço em reais")
    axis.yaxis.set_major_formatter(FuncFormatter(lambda amount, _: brl(amount * 100)))
    locator = AutoDateLocator(minticks=3, maxticks=8)
    axis.xaxis.set_major_locator(locator)
    axis.xaxis.set_major_formatter(ConciseDateFormatter(locator))
    if len(history) == 1:
        day = history.index[-1]
        axis.set_xlim(day - pd.Timedelta(days=2), day + pd.Timedelta(days=2))
    axis.set_ylim(bottom=0)
    axis.grid(axis="y", color="#dce4eb", linewidth=0.8)
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.legend(loc="upper left", bbox_to_anchor=(0, -0.14), ncol=3, frameon=False)
    source = "Demonstração · dados fictícios" if demo else "Steam Brasil · preço diário observado"
    figure.supxlabel(source, x=0.99, ha="right", fontsize=9, color="#526172")
    figure.savefig(destination, dpi=144)


def send_discord(
    webhook: str, product: Product, name: str, day: str, result: Analysis, chart: Path
) -> None:
    mean = "histórico em formação" if result.mean_30d is None else brl(result.mean_30d)
    payload = {
        "allowed_mentions": {"parse": []},
        "embeds": [{
            "title": name,
            "url": product.url,
            "description": f"**{result.classification}** · preço-alvo atingido",
            "color": 0x12656C,
            "fields": [
                {"name": "Preço atual", "value": brl(result.current), "inline": True},
                {"name": "Preço-alvo", "value": brl(product.target_cents), "inline": True},
                {"name": "Mínimo observado", "value": brl(result.minimum), "inline": True},
                {"name": "Média de 30 dias", "value": f"{mean} ({result.samples_30d} observações)"},
            ],
            "image": {"url": "attachment://historico.png"},
            "footer": {"text": f"Steam Brasil · {day}"},
        }],
        "attachments": [{"id": 0, "filename": "historico.png"}],
    }
    try:
        with chart.open("rb") as image:
            response = requests.post(
                webhook, params={"wait": "true"}, data={"payload_json": json.dumps(payload)},
                files={"files[0]": ("historico.png", image, "image/png")},
                timeout=(5, 15), allow_redirects=False,
            )
        if response.status_code != 200:
            raise DeliveryError(f"Discord retornou HTTP {response.status_code}.")
        if not response.json().get("id"):
            raise DeliveryError("Discord não confirmou a criação da mensagem.")
    except (requests.RequestException, ValueError, AttributeError) as exc:
        raise DeliveryError(f"Falha na publicação no Discord ({type(exc).__name__}).") from None
