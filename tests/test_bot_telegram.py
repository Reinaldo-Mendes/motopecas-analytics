"""Testes do bot: conteúdo da mensagem e envio (sem chamar o Telegram de verdade)."""

from types import SimpleNamespace

import pytest

import bot_telegram
from bot_telegram import LIMITE_TELEGRAM, comparar, enviar, montar_mensagem, prazo_troca
from diagnostico import clientes_para_ligar, itens_em_falta, resumo_semana

TOKEN_FALSO = "123456:TOKEN-DE-TESTE"


def test_comparar():
    assert comparar(110, 100) == " (▲ 10,0% vs semana anterior)"
    assert comparar(90, 100) == " (▼ 10,0% vs semana anterior)"
    assert comparar(50, 0) == ""


def test_prazo_troca():
    assert prazo_troca(-1) == "atrasada há 1 dia"
    assert prazo_troca(-6) == "atrasada há 6 dias"
    assert prazo_troca(0) == "vence hoje"
    assert prazo_troca(1) == "vence amanhã"
    assert prazo_troca(5) == "vence em 5 dias"


def test_semana_sao_os_ultimos_7_dias(con):
    semana = resumo_semana(con)
    assert (semana["fim"] - semana["inicio"]).days == 6
    assert semana["faturamento"] > 0 and semana["faturamento_anterior"] > 0


def test_listas_respeitam_limite_e_ordem(con):
    falta = itens_em_falta(con, limite=3)
    assert len(falta) <= 3
    assert [i["classe_abc"] for i in falta] == sorted(i["classe_abc"] for i in falta)
    ligar = clientes_para_ligar(con, limite=3)
    assert len(ligar) <= 3
    gastos = [c["gasto_12m"] for c in ligar]
    assert gastos == sorted(gastos, reverse=True)


def test_mensagem_completa_e_dentro_do_limite(con):
    texto = montar_mensagem(con, "https://exemplo.streamlit.app")
    assert len(texto) <= LIMITE_TELEGRAM
    for trecho in [
        "Faturamento:",
        "OS concluídas:",
        "Troca de óleo para chamar",
        "Estoque parado:",
        "Abrir o dashboard",
    ]:
        assert trecho in texto
    assert "R$ " in texto


def test_nomes_com_caracteres_especiais_sao_escapados(con, monkeypatch):
    monkeypatch.setattr(
        bot_telegram,
        "clientes_para_ligar",
        lambda _con: [
            {
                "nome": "Silva & Filhos <ME>",
                "telefone": None,
                "perfil": "Frota",
                "dias_desde_ultima_visita": 70,
                "gasto_12m": 1000.0,
            }
        ],
    )
    texto = montar_mensagem(con)
    assert "Silva &amp; Filhos &lt;ME&gt;" in texto
    assert "sem telefone" in texto


def test_enviar_monta_a_chamada_certa(monkeypatch):
    chamadas = []

    def post_falso(url, json, timeout):
        chamadas.append((url, json))
        return SimpleNamespace(status_code=200, content=b"{}", json=lambda: {"ok": True})

    monkeypatch.setattr(bot_telegram.requests, "post", post_falso)
    enviar("olá", TOKEN_FALSO, "42")
    url, corpo = chamadas[0]
    assert url.endswith("/sendMessage")
    assert corpo["chat_id"] == "42" and corpo["parse_mode"] == "HTML"


def test_erro_do_telegram_nao_vaza_o_token(monkeypatch):
    def post_falso(url, json, timeout):
        return SimpleNamespace(
            status_code=401,
            content=b"{}",
            json=lambda: {"ok": False, "description": "Unauthorized"},
        )

    monkeypatch.setattr(bot_telegram.requests, "post", post_falso)
    with pytest.raises(RuntimeError) as erro:
        enviar("olá", TOKEN_FALSO, "42")
    assert "Unauthorized" in str(erro.value)
    assert TOKEN_FALSO not in str(erro.value)
