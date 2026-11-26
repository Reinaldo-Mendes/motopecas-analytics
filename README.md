# Motopeças Analytics

Projeto de portfólio: diagnóstico de dados para uma loja **fictícia** de motopeças com oficina
mecânica própria, em Serra Alta (MG, cidade fictícia). Mostra a pequenas e médias empresas o que dá
para descobrir com os dados que elas já têm no ERP (Enterprise Resource Planning, o sistema de
gestão da loja).

> Todos os dados são gerados por script. Nenhum dado real de cliente entra neste repositório.

## Como rodar

```bash
uv sync                                  # cria o ambiente e instala as dependências
uv run python src/gerar_dados.py         # (opcional) regera os CSVs "sujos" em data/raw/
uv run python src/pipeline.py            # limpa os CSVs e monta data/motopecas.duckdb
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
| `analise` | Views prontas para o dashboard: `itens_vendidos`, `ordens_concluidas`, `qualidade_dados` |

Os arquivos SQL rodam em ordem numérica:

- `01_limpeza.sql`: datas em 4 formatos, decimal com vírgula, "R$" no meio do número, telefones
  sem DDD, preços zerados (corrigidos pelo preço mais comum do mesmo item).
- `02_clientes_unificados.sql`: junta cadastros duplicados por CPF/CNPJ, telefone ou nome,
  recusando nomes ambíguos. Nos dados de teste: 92% dos duplicados encontrados, nenhum falso.
- `03_base_analitica.sql`: une balcão e oficina numa visão única de faturamento (OS canceladas
  ficam de fora) e gera o relatório de qualidade dos dados.

Os testes conferem a limpeza contra o "gabarito" do gerador: o faturamento depois da limpeza
tem que bater com o dos dados originais, antes da sujeira.

## Próximas etapas

1. Views de métricas (curva ABC, estoque parado, perfil de cliente por frequência)
2. Dashboard Streamlit (Estoque, Vendas e Margem, Oficina, Clientes)
3. Bot do Telegram com resumo semanal no GitHub Actions
4. Deploy no Streamlit Community Cloud
