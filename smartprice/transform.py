"""Validação tabular das observações antes de gravá-las."""

from dataclasses import asdict

import pandas as pd

from .sources import Quote


def clean_quotes(quotes: list[Quote]) -> tuple[pd.DataFrame, set[int]]:
    frame = pd.DataFrame.from_records(
        (asdict(quote) for quote in quotes), columns=["app_id", "name", "day", "cents", "currency"]
    )
    frame["day"] = pd.to_datetime(frame["day"], errors="coerce")
    frame["name"] = frame["name"].astype("string").str.split().str.join(" ")
    frame["currency"] = frame["currency"].astype("string").str.strip().str.upper()
    frame["cents"] = pd.to_numeric(frame["cents"], errors="coerce")
    valid = (
        frame["day"].notna()
        & frame["name"].str.len().between(1, 256)
        & frame["currency"].eq("BRL")
        & frame["cents"].between(0, 2**31 - 1)
        & frame["cents"].mod(1).eq(0)
    ).fillna(False)
    rejected = set(frame.loc[~valid, "app_id"])
    cleaned = frame.loc[valid].drop_duplicates(["app_id", "day"], keep="last").copy()
    cleaned["day"] = cleaned["day"].dt.strftime("%Y-%m-%d")
    cleaned["cents"] = cleaned["cents"].astype("int64")
    return cleaned.sort_values(["app_id", "day"]), rejected
