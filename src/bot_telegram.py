"""Envia o resumo semanal da loja para um chat do Telegram.

Configuração (variáveis de ambiente; no GitHub Actions elas vêm dos Secrets):
    TELEGRAM_TOKEN    token do bot, dado pelo @BotFather
    TELEGRAM_CHAT_ID  id do chat que recebe a mensagem
    DASHBOARD_URL     (opcional) link do dashboard, incluído no fim da mensagem

Uso:
    uv run python src/bot_telegram.py              # envia (ou só mostra, se faltar token)
    uv run python src/bot_telegram.py --mostrar    # só mostra a mensagem, nunca envia
"""

from __future__ import annotations

import argparse
import os
import sys
from html import escape

import duckdb
import requests

from diagnostico import (
    clientes_para_ligar,
    itens_em_falta,
    resumo_estoque,
    resumo_semana,
    resumo_troca_oleo,
    troca_oleo_semana,
)
from formatacao import (
    formatar_moeda_curta,
    formatar_numero,
    formatar_pct,
    formatar_telefone,
)
from pipeline import CAMINHO_BANCO, banco_atualizado, construir_banco

LIMITE_TELEGRAM = 4096  # tamanho máximo de uma mensagem (conferido nos testes)


def comparar(atual: float, anterior: float) -> str:
    """'▲ 5,2% vs semana anterior' (ou ▼); vazio se não houver base de comparação."""
    if not anterior:
        return ""
    variacao = atual / anterior - 1
    seta = "▲" if variacao >= 0 else "▼"
    return f" ({seta} {formatar_pct(abs(variacao))} vs semana anterior)"


def prazo_troca(dias: int) -> str:
    """-3 -> 'atrasada há 3 dias'; 0 -> 'vence hoje'; 5 -> 'vence em 5 dias'."""
    if dias < 0:
        return f"atrasada há {-dias} {'dia' if dias == -1 else 'dias'}"
    if dias == 0:
        return "vence hoje"
    return "vence amanhã" if dias == 1 else f"vence em {dias} dias"


def montar_mensagem(con: duckdb.DuckDBPyConnection, url_dashboard: str | None = None) -> str:
    """Texto do resumo em HTML simples (o Telegram aceita <b>, <i> e <a>).

    Tudo o que vem dos dados passa por `escape`: um nome como "Silva & Filhos <ME>" quebraria
    o HTML da mensagem (o equivalente a evitar injeção ao montar SQL com strings em Java).
    """
    semana = resumo_semana(con)
    estoque = resumo_estoque(con)
    linhas = [
        "<b>Motopeças · resumo da semana</b>",
        f"{semana['inicio']:%d/%m} a {semana['fim']:%d/%m/%Y}",
        "",
        f"<b>Faturamento:</b> {formatar_moeda_curta(semana['faturamento'])}"
        + comparar(semana["faturamento"], semana["faturamento_anterior"]),
        f"<b>OS concluídas:</b> {formatar_numero(semana['qtd_os'])}"
        + comparar(semana["qtd_os"], semana["qtd_os_anterior"]),
    ]

    oleo = troca_oleo_semana(con)
    if oleo:
        total = resumo_troca_oleo(con)
        qtd = total["qtd_esta_semana"] + total["qtd_atrasada"]
        linhas += ["", f"<b>Troca de óleo para chamar</b> ({qtd} clientes; os 5 que mais gastam)"]
        linhas += [
            f"• {escape(c['nome'])} — {formatar_telefone(c['telefone'])} — "
            + prazo_troca(c["dias_para_troca"])
            for c in oleo
        ]

    falta = itens_em_falta(con)
    if falta:
        linhas += ["", f"<b>Em falta no estoque ({estoque['qtd_em_falta']} itens)</b>"]
        linhas += [
            f"• {escape(i['descricao'])} — curva {i['classe_abc']}, "
            f"{formatar_numero(i['qtd_vendida_90d'])} vendidos em 90 dias"
            for i in falta
        ]

    ligar = clientes_para_ligar(con)
    if ligar:
        linhas += ["", "<b>Clientes para ligar</b> (pararam de vir há pouco tempo)"]
        linhas += [
            f"• {escape(c['nome'])} — {formatar_telefone(c['telefone'])} — "
            f"{c['perfil'].lower()}, sem vir há {formatar_numero(c['dias_desde_ultima_visita'])}"
            " dias"
            for c in ligar
        ]

    linhas += [
        "",
        f"<b>Estoque parado:</b> {formatar_moeda_curta(estoque['valor_parado'])} em "
        f"{estoque['qtd_sem_giro']} itens sem venda há 6+ meses",
    ]
    if url_dashboard:
        linhas += ["", f'<a href="{escape(url_dashboard, quote=True)}">Abrir o dashboard</a>']
    return "\n".join(linhas)  # listas limitadas a 5 itens: fica bem abaixo do limite


def enviar(texto: str, token: str, chat_id: str) -> None:
    """Envia a mensagem pela API do Telegram (método sendMessage)."""
    resposta = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": texto,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        },
        timeout=30,
    )
    corpo = resposta.json() if resposta.content else {}
    if resposta.status_code != 200 or not corpo.get("ok"):
        # Não usamos raise_for_status(): a mensagem de erro dele traz a URL, que contém o token
        raise RuntimeError(
            f"Telegram recusou a mensagem (HTTP {resposta.status_code}): "
            f"{corpo.get('description', 'sem detalhes')}"
        )


def main() -> None:
    """Monta o resumo e envia, ou só mostra se pedido ou se faltar configuração."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Resumo semanal da Motopeças no Telegram.")
    parser.add_argument("--mostrar", action="store_true", help="só mostra, não envia")
    args = parser.parse_args()

    if not banco_atualizado():
        construir_banco()
    with duckdb.connect(CAMINHO_BANCO, read_only=True) as con:
        texto = montar_mensagem(con, os.environ.get("DASHBOARD_URL"))

    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if args.mostrar or not (token and chat_id):
        if not args.mostrar:
            print("TELEGRAM_TOKEN/TELEGRAM_CHAT_ID não definidos: só mostrando a mensagem.\n")
        print(texto)
        return
    enviar(texto, token, chat_id)
    print("Resumo enviado ao Telegram.")


if __name__ == "__main__":
    main()
