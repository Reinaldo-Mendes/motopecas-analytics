"""Formatação no padrão brasileiro, usada pelo dashboard e pelo bot do Telegram."""

from __future__ import annotations

from datetime import date

import pandas as pd

MESES_ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def formatar_numero(valor: float, casas: int = 0) -> str:
    """1234567.8 -> '1.234.568' (ponto no milhar, vírgula no decimal)."""
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_moeda(valor: float, casas: int = 2) -> str:
    """1234.5 -> 'R$ 1.234,50'; negativos ficam '-R$ 10,00'."""
    sinal = "-" if valor < 0 else ""
    return f"{sinal}R$ {formatar_numero(abs(valor), casas)}"


def formatar_moeda_curta(valor: float) -> str:
    """Valor resumido para KPIs: 'R$ 950', 'R$ 12,3 mil', 'R$ 1,2 mi'."""
    absoluto = abs(valor)
    sinal = "-" if valor < 0 else ""
    if absoluto >= 1_000_000:
        return f"{sinal}R$ {formatar_numero(absoluto / 1_000_000, 1)} mi"
    if absoluto >= 1_000:
        return f"{sinal}R$ {formatar_numero(absoluto / 1_000, 1)} mil"
    return f"{sinal}R$ {formatar_numero(absoluto, 0)}"


def formatar_pct(fracao: float, casas: int = 1) -> str:
    """0.3934 -> '39,3%'."""
    return f"{formatar_numero(fracao * 100, casas)}%"


def formatar_data(d: date | None) -> str:
    """date(2026, 11, 26) -> '26/11/2026'; None/NaT -> ''."""
    return "" if d is None or pd.isna(d) else d.strftime("%d/%m/%Y")


def formatar_mes(d: date) -> str:
    """date(2026, 11, 1) -> 'nov/2026'."""
    return f"{MESES_ABREV[d.month - 1]}/{d.year}"


def formatar_telefone(digitos: str | None) -> str:
    """'35912345678' -> '(35) 91234-5678'; vazio -> 'sem telefone'."""
    if not isinstance(digitos, str) or len(digitos) != 11:  # None ou NaN do pandas
        return "sem telefone"
    return f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}"
