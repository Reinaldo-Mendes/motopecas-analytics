"""Dados brutos: os CSVs exatamente como saíram do ERP e exemplos do que a limpeza corrigiu."""

import streamlit as st

from componentes import cabecalho, secao
from dados import RAIZ, consultar
from formatacao import formatar_data, formatar_moeda, formatar_numero

URL_CSVS = "https://github.com/Reinaldo-Mendes/motopecas-analytics/tree/main/data/raw"
# rótulo na tela -> nome da tabela (e do arquivo .csv)
TABELAS = {
    "Vendas": "vendas",
    "Ordens de serviço": "ordens_servico",
    "Itens das OS": "itens_os",
    "Clientes": "clientes",
    "Produtos": "produtos",
}

cabecalho(
    "Dados brutos",
    "Como os dados saem do sistema da loja (ERP), antes de qualquer limpeza. Tudo fictício, "
    "gerado por script, mas com a bagunça de uma exportação real.",
)

contagens = consultar(
    " UNION ALL ".join(
        f"SELECT '{t}' AS tabela, count(*) AS linhas FROM bruto.{t}" for t in TABELAS.values()
    )
)
correcoes = consultar("SELECT sum(quantidade) AS total FROM analise.qualidade_dados").total.iloc[0]
col1, col2 = st.columns(2)
col1.metric(
    "Linhas recebidas", formatar_numero(contagens.linhas.sum()), border=True, help="Nos 5 CSVs."
)
col2.metric(
    "Problemas tratados",
    formatar_numero(correcoes),
    border=True,
    help="Soma do relatório de qualidade dos dados (ver Visão geral).",
)

# ---- Antes x depois ----
secao("Antes × depois da limpeza", "Um exemplo de cada problema, lado a lado.")
aba_datas, aba_telefones, aba_duplicados, aba_precos = st.tabs(
    ["Datas", "Telefones", "Cadastros duplicados", "Preços zerados"]
)

with aba_datas:
    st.write(
        "A mesma data chega em 4 formatos diferentes (aaaa-mm-dd é o padrão ISO), às vezes no "
        "mesmo pedido. O formato é "
        "reconhecido pelo padrão do texto: '27/11/24' lido como dd/mm/aaaa viraria o ano 24."
    )
    datas = consultar("SELECT * FROM analise.exemplo_datas")
    st.dataframe(
        datas.assign(
            Formato=datas.formato,
            Linhas=datas.qtd_linhas.map(formatar_numero),
            **{
                "Como veio": datas.valor_bruto,
                "Data entendida": datas.valor_limpo.map(formatar_data),
            },
        )[["Formato", "Linhas", "Como veio", "Data entendida"]],
        hide_index=True,
    )

with aba_telefones:
    st.write(
        "Cada atendente digita de um jeito. Tudo vira só dígitos com DDD; quem veio sem DDD "
        "ganha o 35 da cidade. Padrão: 9 = um dígito."
    )
    telefones = consultar("SELECT * FROM analise.exemplo_telefones")
    st.dataframe(
        telefones.assign(
            Padrão=telefones.padrao,
            Clientes=telefones.qtd_clientes.map(formatar_numero),
            **{
                "Como veio": telefones.valor_bruto.fillna("—"),
                "Padronizado": telefones.valor_limpo.fillna("sem telefone"),
            },
        )[["Padrão", "Clientes", "Como veio", "Padronizado"]],
        hide_index=True,
    )

with aba_duplicados:
    st.write(
        "O mesmo cliente cadastrado duas vezes, com outra grafia ou outro telefone. Os cadastros "
        "são juntados quando batem o CPF/CNPJ, o telefone + primeiro nome ou o nome completo "
        "(se não houver outro cliente com o mesmo nome). Um exemplo de cada critério:"
    )
    duplicados = consultar("SELECT * FROM analise.exemplo_duplicados")
    st.dataframe(
        duplicados.assign(
            **{
                "Juntado por": duplicados.motivo,
                "Cliente final": duplicados.id_cliente_unificado,
                "Código no ERP": duplicados.id_cliente,
                "Nome como veio": duplicados.nome,
                "CPF/CNPJ": duplicados.cpf_cnpj.fillna("—"),
                "Telefone": duplicados.telefone.fillna("—"),
                "Cadastro": duplicados.data_cadastro,
            }
        )[
            [
                "Juntado por",
                "Cliente final",
                "Código no ERP",
                "Nome como veio",
                "CPF/CNPJ",
                "Telefone",
                "Cadastro",
            ]
        ],
        hide_index=True,
    )

with aba_precos:
    precos = consultar("SELECT * FROM analise.exemplo_precos")
    st.write(
        f"{formatar_numero(len(precos))} itens vendidos com preço R$ 0,00 (o item saiu, mas "
        "o preço não foi lançado). O preço volta pelo valor mais comum do mesmo item, com o mesmo "
        "desconto, em outras vendas; se não houver, pelo preço de tabela com o desconto."
    )
    st.dataframe(
        precos.assign(
            Pedido=precos.numero_pedido,
            Item=precos.descricao,
            Desconto=precos.desconto_bruto,
            **{
                "Como veio": precos.valor_bruto,
                "Preço corrigido": precos.valor_limpo.map(formatar_moeda),
            },
        )[["Pedido", "Item", "Desconto", "Como veio", "Preço corrigido"]],
        hide_index=True,
    )

# ---- Arquivos completos ----
secao(
    "Os arquivos como chegaram",
    "Separados por ponto e vírgula, decimal com vírgula, sem nenhum tratamento.",
)
rotulo = st.pills("Arquivo", list(TABELAS), default="Vendas") or "Vendas"
tabela = TABELAS[rotulo]
bruto = consultar(f"SELECT * FROM bruto.{tabela}")
st.caption(f"`{tabela}.csv`: {formatar_numero(len(bruto))} linhas, {len(bruto.columns)} colunas.")
# célula vazia no CSV aparece vazia (e não "None")
st.dataframe(bruto.fillna(""), hide_index=True, height=420)
st.download_button(
    f"Baixar {tabela}.csv",
    (RAIZ / "data" / "raw" / f"{tabela}.csv").read_bytes(),
    file_name=f"{tabela}.csv",
    mime="text/csv",
    icon=":material/download:",
)
st.markdown(f"Os mesmos arquivos estão no [GitHub do projeto]({URL_CSVS}).")
