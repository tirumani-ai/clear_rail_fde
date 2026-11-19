"""Master data: what the payment provider already knows before a payment arrives. Plain data, read by plain code."""
import json
from dataclasses import dataclass
from decimal import Decimal
from functools import cache
from pathlib import Path

from app.rules.normalize import money


@dataclass
class Master:
    clients: dict[str, dict]        # by client_id
    beneficiaries: dict[str, dict]  # by vendor_id: legal name, country and the SAVED bank details
    watchlist_entities: list[str]
    watchlist_people: list[str]
    fx_per_usd: dict[str, float]
    approval_limits_usd: dict[str, float | None]
    tolerances: dict[str, float]
    purpose_codes: dict[str, str]
    payment_history: list[dict]     # earlier payments, for invoices paid in parts


@cache
def load(root: str = "data/master") -> Master:
    data = json.loads(Path(root, "master_data.json").read_text())
    return Master(
        clients={c["client_id"]: c for c in data["clients"]},
        beneficiaries={b["vendor_id"]: b for b in data["beneficiaries"]},
        watchlist_entities=data["watchlist"]["entities"],
        watchlist_people=data["watchlist"]["people"],
        fx_per_usd=data["fx_rates_per_usd"],
        approval_limits_usd=data["approval_limits_usd"],
        tolerances=data["tolerances"],
        purpose_codes=data["purpose_codes"],
        payment_history=json.loads(Path(root, "payment_history.json").read_text()),
    )


def to_usd(amount, currency: str, master: Master) -> Decimal:
    return money(Decimal(str(amount)) / Decimal(str(master.fx_per_usd[currency])))


def convert(amount, from_currency: str, to_currency: str, master: Master) -> Decimal:
    if from_currency == to_currency:
        return money(amount)
    usd = Decimal(str(amount)) / Decimal(str(master.fx_per_usd[from_currency]))
    return money(usd * Decimal(str(master.fx_per_usd[to_currency])))
