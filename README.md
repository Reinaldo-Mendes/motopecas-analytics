# Motopeças Analytics

Projeto de portfólio: diagnóstico de dados para uma loja **fictícia** de motopeças com oficina
mecânica própria, em Serra Alta (MG, cidade fictícia). Mostra a pequenas e médias empresas o que dá
para descobrir com os dados que elas já têm no ERP (Enterprise Resource Planning, o sistema de
gestão da loja).

> Todos os dados são gerados por script. Nenhum dado real de cliente entra neste repositório.

**Dashboard no ar:** [motopecas-analytics.streamlit.app](https://motopecas-analytics.streamlit.app/) (feito para abrir bem no celular).

## Como rodar

```bash
uv sync                                  # cria o ambiente e instala as dependências
uv run python src/gerar_dados.py         # (opcional) regera os CSVs "sujos" em data/raw/
uv run python src/pipeline.py            # limpa os CSVs e monta data/motopecas.duckdb
uv run streamlit run app/Home.py         # abre o dashboard em http://localhost:8501
uv run python src/bot_telegram.py --mostrar   # mostra o resumo semanal do bot
uv run ruff check .                      # lint
uv run pytest                            # testes
```

Os CSVs brutos ficam versionados, para você ver no GitHub como os dados chegam "sujos".
O gerador é reproduzível: semente fixa (`--seed`, padrão 42) e histórico de 24 meses terminando
em 26/11/2026 (`--data-fim`, aceita `hoje`).

## Dados brutos (`data/raw/`)

CSVs separados por `;`, decimal com vírgula, como um ERP brasileiro exporta.

| Arquivo | Conteúdo |
|---|---|
| `produtos.csv` | ~400 SKUs (Stock Keeping Unit, código de cada item do estoque), custo, preço e estoque |
| `clientes.csv` | Cadastro de clientes (PF e PJ) |
| `vendas.csv` | Itens vendidos no balcão (uma linha por item; `id_cliente` vazio = consumidor final) |
| `ordens_servico.csv` | OS (ordens de serviço) da oficina, com mão de obra e mecânico |
| `itens_os.csv` | Peças usadas em cada OS |

Sujeira proposital: telefones faltando ou em formatos variados, clientes recadastrados com outra
grafia, datas em formatos mistos, preços zerados, preços com "R$" no meio dos números e OS
canceladas que não devem entrar no faturamento.

## Pipeline (`src/pipeline.py` + `src/sql/`)

O banco DuckDB é montado em três camadas (schemas):

| Schema | O que tem |
|---|---|
| `bruto` | Os CSVs exatamente como chegaram, tudo como texto |
| `limpo` | Tipos corretos, telefones padronizados, preços zerados corrigidos, clientes unificados |
| `analise` | Views prontas para o dashboard e o bot (base e métricas) |

Os arquivos SQL rodam em ordem numérica:

- `01_limpeza.sql`: datas em 4 formatos, decimal com vírgula, "R$" no meio do número, telefones
  sem DDD, preços zerados (corrigidos pelo preço mais comum do mesmo item).
- `02_clientes_unificados.sql`: junta cadastros duplicados por CPF/CNPJ, telefone ou nome,
  recusando nomes ambíguos. Nos dados de teste: 92% dos duplicados encontrados, nenhum falso.
- `03_base_analitica.sql`: une balcão e oficina numa visão única de faturamento (OS canceladas
  ficam de fora) e gera o relatório de qualidade dos dados.
- `04_metricas_estoque.sql`: curva ABC, dias sem venda, cobertura e situação de cada SKU
  (sem giro, em falta, repor) e estoque por modelo de moto x motos atendidas na oficina.
- `05_metricas_vendas.sql`: faturamento e margem mensais, margem por categoria.
- `06_metricas_oficina.sql`: produção e prazo por mecânico, desempenho por serviço,
  orçamentos recusados por faixa de valor e venda casada (peça que combina com cada serviço).
- `07_metricas_clientes.sql`: **perfil descoberto pelo comportamento** (o ERP não sabe quem é
  motoboy) e status ativo / em risco / inativo. Acerta 96,6% dos perfis reais. Também prevê a
  próxima troca de óleo de cada cliente pelo ritmo dele (mediana entre as trocas).
- `08_metricas_comercial.sql`: descontos do balcão (quanto, para quem e efeito no ticket) e
  custo estimado de cada forma de pagamento. As taxas de maquininha e boleto são
  **premissas** declaradas na view `analise.premissas_pagamento`, fáceis de trocar.

As métricas usam como "hoje" a última data com movimento nos dados, não o relógio do
computador, então os números não mudam conforme o dia em que o dashboard é aberto.

Testes em duas frentes:
- **contra o gabarito do gerador**: o faturamento depois da limpeza tem que bater com o dos
  dados originais, e o perfil descoberto com o perfil real;
- **cenário montado à mão** (`tests/test_metricas.py`): 5 produtos e 4 clientes com cada
  resultado calculado nos comentários.

## Dashboard (`app/`)

Pensado para o dono da loja abrir no celular: KPIs (Key Performance Indicators,
indicadores-chave) com minigráfico de tendência no topo, um filtro por página e uma frase
explicando cada gráfico. `app/Home.py` monta o menu (`st.navigation`) e as páginas ficam em
`app/paginas/`; o tema (fonte Inter, cantos arredondados, claro e escuro) está em
`.streamlit/config.toml`.

| Página | O que responde |
|---|---|
| Visão geral | Como foi o último mês, o que fazer esta semana e os achados em cartões, do maior impacto em R$ para o menor |
| Estoque | Dinheiro parado, itens em falta, o que comprar, curva ABC e estoque x motos atendidas |
| Vendas e margem | Faturamento, margem, descontos sem critério, custo das formas de pagamento e chuva x pneus |
| Oficina | Volume de OS, orçamentos recusados, produção e prazo por mecânico, serviços e venda casada |
| Clientes | Troca de óleo prevista para a semana, perfil descoberto pela frequência e quem sumiu |

Os achados vêm de `src/diagnostico.py` (o mesmo que o bot do Telegram usa).
As cores dos gráficos foram validadas para daltonismo e contraste nos temas claro e escuro, e
todo gráfico tem a mesma informação em tabela logo abaixo.

Se o banco não existir (ex.: no primeiro deploy), o dashboard roda o pipeline sozinho a partir
dos CSVs versionados.

## Bot do Telegram (`src/bot_telegram.py`)

Toda segunda-feira às 8h (horário de Brasília), o GitHub Actions monta o banco a partir dos CSVs
e envia ao Telegram um resumo da semana: faturamento e OS contra a semana anterior, clientes
com troca de óleo prevista ou atrasada (para chamar antes que troquem em outro lugar), itens
campeões em falta, clientes que começaram a sumir (com telefone, para ligar) e o estoque parado.

Para ativar no seu repositório:

1. No Telegram, fale com o **@BotFather**, envie `/newbot` e guarde o **token** que ele devolve.
2. Mande qualquer mensagem para o seu bot e abra
   `https://api.telegram.org/bot<TOKEN>/getUpdates` no navegador: o número em `"chat":{"id":...}`
   é o **chat id**.
3. No GitHub: *Settings > Secrets and variables > Actions*. Crie os secrets `TELEGRAM_TOKEN` e
   `TELEGRAM_CHAT_ID` e, se quiser, a variable `DASHBOARD_URL`.
4. Na aba *Actions*, rode "Resumo semanal no Telegram" manualmente para testar.

Sem token configurado, o script só mostra a mensagem no terminal. O token nunca aparece no
código nem nos logs (o erro do Telegram é tratado para não exibir a URL, que contém o token).

Como os dados são fictícios e terminam em 26/11/2026, o resumo é sempre o da mesma semana.
Com dados reais do ERP, ele acompanharia a semana corrente sem nenhuma mudança no código.

## Integração contínua

`.github/workflows/testes.yml` roda `ruff` e `pytest` a cada push e pull request.

## Deploy (Streamlit Community Cloud)

O app publicado está em <https://motopecas-analytics.streamlit.app/> e é atualizado
automaticamente a cada push na `main`. Para publicar uma cópia:

1. Em [share.streamlit.io](https://share.streamlit.io), entre com a conta do GitHub e clique em
   *Create app*.
2. Escolha este repositório, branch `main` e arquivo principal `app/Home.py`.
3. Em *Advanced settings*, selecione Python 3.12.

Não há segredos para configurar no dashboard. Na primeira visita, o app monta o banco a partir
dos CSVs versionados (leva alguns segundos). As dependências vêm do `requirements.txt`,
gerado a partir do `uv.lock`; o CI falha se os dois ficarem diferentes. Para atualizar:

```bash
uv export --no-dev --no-hashes --no-emit-project --format requirements-txt -o requirements.txt
```

## Próximas etapas

- Migrar as transformações SQL para dbt
- Conectar a uma exportação real de ERP (Bling, Tiny) no lugar do gerador
