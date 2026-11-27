"""Estatísticas sobre as observações diárias e regras de classificação."""

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Analysis:
    current: int
    mean_30d: float | None
    minimum: int
    samples_30d: int
    classification: str
    episode_start: str | None


def analyze(history: pd.DataFrame, target: int) -> tuple[Analysis, pd.Series]:
    prices = history["price_cents"]
    # Para o dia D, a referência usa [D - 30 dias, D), com peso igual por observação.
    rolling = prices.rolling("30D", closed="left")
    moving_average = rolling.mean()
    current = int(prices.iloc[-1])
    last_day = prices.index[-1]
    window = prices.loc[(prices.index >= last_day - pd.Timedelta(days=30)) & (prices.index < last_day)]
    samples = len(window)
    mean = float(moving_average.iloc[-1]) if samples else None

    classification = "Preço Normal"
    if samples >= 7:
        # Compara inteiros para preservar os limites inclusivos de 15% e 10%.
        previous_total = int(window.sum())
        scaled_current = 100 * samples * current
        if scaled_current <= 85 * previous_total and current * samples < previous_total:
            classification = "Oferta Real"
        elif scaled_current >= 110 * previous_total and current * samples > previous_total:
            classification = "Caro"

    episode_start = None
    if current <= target:
        above_target = prices[prices > target]
        eligible = prices if above_target.empty else prices.loc[prices.index > above_target.index[-1]]
        episode_start = eligible.index[0].date().isoformat()

    return Analysis(current, mean, int(prices.min()), samples, classification, episode_start), moving_average


def brl(cents: float) -> str:
    return "R$ " + f"{cents / 100:,.2f}".translate(str.maketrans(",.", ".,"))
