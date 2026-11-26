"""Gera os CSVs brutos (fictícios) da Motopeças, simulando a exportação "suja" de um ERP.

ERP (Enterprise Resource Planning) é o sistema de gestão da loja (Bling, Tiny etc.).
O processo tem duas fases:
1. `simular_dados`: cria dados limpos e coerentes (catálogo, clientes, vendas, oficina).
2. `aplicar_sujeira`: estraga os dados como um ERP real faria (datas mistas, telefones
   faltando, nomes duplicados, preços zerados, decimal com vírgula).

Uso:
    uv run python src/gerar_dados.py
    uv run python src/gerar_dados.py --seed 7 --data-fim 2026-06-30
    uv run python src/gerar_dados.py --data-fim hoje

Os CSVs ficam versionados no git; por isso a data final padrão é fixa (DATA_FIM_PADRAO).
Para "rejuvenescer" os dados, mude essa constante e gere de novo.
"""

from __future__ import annotations

import argparse
import math
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

SEED_PADRAO = 42
DATA_FIM_PADRAO = date(2026, 11, 26)
MESES_HISTORICO = 24
PASTA_SAIDA = Path(__file__).resolve().parent.parent / "data" / "raw"
CIDADE = "Serra Alta"  # cidade fictícia de porte médio
UF = "MG"
DDD = "35"

# Modelo da moto -> participação na frota da cidade (soma 1)
MOTOS: dict[str, float] = {
    "Honda CG 160": 0.30,
    "Honda Biz 125": 0.15,
    "Honda Pop 110i": 0.15,
    "Honda NXR 160 Bros": 0.15,
    "Yamaha Factor 150": 0.10,
    "Yamaha Fazer 250": 0.08,
    "Yamaha XRE 300": 0.07,
}
MOTOS_SEM_EMBREAGEM = ("Honda Biz 125", "Honda Pop 110i")  # câmbio semiautomático
MOTOS_2_LITROS_OLEO = ("Yamaha Fazer 250", "Yamaha XRE 300")

PREFIXO_SKU = {
    "Óleo e lubrificantes": "OLE",
    "Pneus e câmaras": "PNE",
    "Relação (kit transmissão)": "REL",
    "Freios": "FRE",
    "Elétrica": "ELE",
    "Cabos": "CAB",
    "Filtros": "FIL",
    "Acessórios": "ACE",
}

MESES_CHUVA = {11, 12, 1, 2, 3}


@dataclass(frozen=True)
class TipoProduto:
    """Modelo de produto; vira um SKU para cada marca (e para cada moto, se `por_moto`)."""

    grupo: str  # chave usada pelos serviços da oficina
    categoria: str
    nome: str
    marcas: tuple[str, ...]
    custo: tuple[float, float]  # faixa de custo em R$
    markup: tuple[float, float]  # acréscimo sobre o custo (0.5 = +50%)
    demanda: float  # peso relativo de saída no balcão
    por_moto: bool = False
    excluir_motos: tuple[str, ...] = ()


OLEO, PNEU, REL, FRE, ELE, CAB, FIL, ACE = PREFIXO_SKU  # nomes das categorias

TIPOS: tuple[TipoProduto, ...] = (
    # Óleo e lubrificantes (universais)
    TipoProduto(
        "oleo_motor",
        OLEO,
        "Óleo 20W50 mineral 1L",
        ("Mobil", "Castrol", "Lubrax", "Ipiranga", "Yamalube", "Pro Honda"),
        (18, 26),
        (0.5, 0.9),
        10.0,
    ),
    TipoProduto(
        "oleo_motor",
        OLEO,
        "Óleo 10W30 semissintético 1L",
        ("Motul", "Castrol", "Mobil"),
        (28, 40),
        (0.45, 0.8),
        4.0,
    ),
    TipoProduto(
        "oleo_motor",
        OLEO,
        "Óleo 10W40 sintético 1L",
        ("Motul", "Castrol"),
        (45, 60),
        (0.4, 0.7),
        1.5,
    ),
    TipoProduto(
        "lub_corrente",
        OLEO,
        "Lubrificante de corrente spray 300ml",
        ("Motul", "Wurth", "Mundial"),
        (20, 35),
        (0.6, 1.0),
        2.0,
    ),
    TipoProduto(
        "fluido_freio",
        OLEO,
        "Fluido de freio DOT 4 200ml",
        ("Bosch", "Varga", "TRW"),
        (12, 20),
        (0.7, 1.1),
        1.0,
    ),
    # Pneus e câmaras (por moto)
    TipoProduto(
        "pneu_dianteiro",
        PNEU,
        "Pneu dianteiro",
        ("Pirelli", "Levorin", "Rinaldi", "Michelin", "Technic"),
        (110, 220),
        (0.25, 0.45),
        1.5,
        por_moto=True,
    ),
    TipoProduto(
        "pneu_traseiro",
        PNEU,
        "Pneu traseiro",
        ("Pirelli", "Levorin", "Rinaldi", "Michelin", "Technic"),
        (150, 320),
        (0.25, 0.45),
        2.5,
        por_moto=True,
    ),
    TipoProduto(
        "camara",
        PNEU,
        "Câmara de ar dianteira",
        ("Pirelli", "Levorin", "Rinaldi"),
        (20, 30),
        (0.6, 1.0),
        1.5,
        por_moto=True,
    ),
    TipoProduto(
        "camara",
        PNEU,
        "Câmara de ar traseira",
        ("Pirelli", "Levorin", "Rinaldi"),
        (22, 34),
        (0.6, 1.0),
        2.0,
        por_moto=True,
    ),
    # Relação
    TipoProduto(
        "relacao",
        REL,
        "Kit relação",
        ("Vaz", "Riffel", "DID", "Allen"),
        (90, 220),
        (0.4, 0.7),
        1.5,
        por_moto=True,
    ),
    # Freios
    TipoProduto(
        "pastilha",
        FRE,
        "Pastilha de freio dianteira",
        ("Cobreq", "Fras-le", "Vaz", "Syl"),
        (15, 35),
        (0.8, 1.2),
        2.0,
        por_moto=True,
    ),
    TipoProduto(
        "lona",
        FRE,
        "Lona de freio traseira",
        ("Cobreq", "Fras-le"),
        (15, 30),
        (0.8, 1.2),
        1.5,
        por_moto=True,
    ),
    TipoProduto(
        "disco",
        FRE,
        "Disco de freio dianteiro",
        ("Vaz", "Fras-le"),
        (80, 160),
        (0.4, 0.7),
        0.3,
        por_moto=True,
    ),
    # Elétrica
    TipoProduto(
        "vela", ELE, "Vela de ignição", ("NGK", "Bosch"), (12, 25), (0.8, 1.2), 2.0, por_moto=True
    ),
    TipoProduto(
        "bateria",
        ELE,
        "Bateria",
        ("Moura", "Heliar", "Yuasa", "Route"),
        (90, 200),
        (0.35, 0.6),
        0.8,
        por_moto=True,
    ),
    TipoProduto(
        "lampada", ELE, "Lâmpada farol H4 12V", ("Philips", "Osram"), (10, 30), (1.0, 1.5), 2.5
    ),
    TipoProduto(
        "regulador",
        ELE,
        "Regulador retificador",
        ("Magnetron", "Rinaldi"),
        (40, 90),
        (0.6, 0.9),
        0.3,
        por_moto=True,
    ),
    TipoProduto("pisca", ELE, "Pisca LED (par)", ("Sinalsul", "Rinaldi"), (8, 20), (1.0, 1.5), 1.5),
    # Cabos
    TipoProduto(
        "cabo_embreagem",
        CAB,
        "Cabo de embreagem",
        ("Controlflex", "Rinaldi"),
        (12, 25),
        (0.9, 1.3),
        1.0,
        por_moto=True,
        excluir_motos=MOTOS_SEM_EMBREAGEM,
    ),
    TipoProduto(
        "cabo_acelerador",
        CAB,
        "Cabo de acelerador",
        ("Controlflex", "Rinaldi"),
        (12, 25),
        (0.9, 1.3),
        1.0,
        por_moto=True,
    ),
    TipoProduto(
        "cabo_velocimetro",
        CAB,
        "Cabo de velocímetro",
        ("Controlflex", "Rinaldi"),
        (10, 20),
        (0.9, 1.3),
        0.5,
        por_moto=True,
    ),
    # Filtros
    TipoProduto(
        "filtro_oleo",
        FIL,
        "Filtro de óleo",
        ("Tecfil", "Fram", "Vedamotors"),
        (10, 25),
        (0.8, 1.2),
        1.5,
        por_moto=True,
    ),
    TipoProduto(
        "filtro_ar",
        FIL,
        "Filtro de ar",
        ("Tecfil", "Fram", "Vedamotors"),
        (15, 40),
        (0.8, 1.2),
        1.0,
        por_moto=True,
    ),
    TipoProduto(
        "retentor",
        FIL,
        "Retentor de bengala (par)",
        ("Vedamotors", "Sabó"),
        (25, 50),
        (0.7, 1.0),
        0.4,
        por_moto=True,
    ),
    # Acessórios (maior margem)
    TipoProduto(
        "capacete",
        ACE,
        "Capacete fechado",
        ("Pro Tork", "LS2", "Bieffe", "Norisk"),
        (120, 450),
        (0.5, 0.9),
        0.25,
    ),
    TipoProduto(
        "capacete", ACE, "Capacete aberto", ("Pro Tork", "Bieffe"), (90, 200), (0.5, 0.9), 0.2
    ),
    TipoProduto("bau", ACE, "Baú 41L", ("Pro Tork", "Givi"), (150, 350), (0.5, 0.8), 0.08),
    TipoProduto("luva", ACE, "Luva motociclista", ("X11", "Pro Tork"), (30, 80), (0.8, 1.3), 0.6),
    TipoProduto(
        "capa_chuva", ACE, "Capa de chuva", ("Pantaneiro", "Alba"), (40, 90), (0.8, 1.2), 1.0
    ),
    TipoProduto(
        "suporte_celular",
        ACE,
        "Suporte de celular",
        ("Multilaser", "Atrio"),
        (20, 50),
        (1.0, 1.5),
        1.5,
    ),
    TipoProduto(
        "manopla", ACE, "Manopla (par)", ("Pro Tork", "Rinaldi"), (10, 25), (1.0, 1.5), 1.0
    ),
    TipoProduto("antena", ACE, "Antena corta-pipa", ("Genérica",), (8, 15), (1.5, 2.0), 1.0),
    TipoProduto(
        "retrovisor",
        ACE,
        "Retrovisor (par)",
        ("Vision", "GVS"),
        (25, 60),
        (0.9, 1.3),
        1.5,
        por_moto=True,
    ),
)

# Serviço -> (mão de obra base em R$, [(grupo de peça, probabilidade de usar)])
SERVICOS: dict[str, tuple[float, list[tuple[str, float]]]] = {
    "Troca de óleo": (25.0, [("oleo_motor", 1.0), ("filtro_oleo", 0.35)]),
    "Revisão geral": (
        120.0,
        [
            ("oleo_motor", 1.0),
            ("filtro_ar", 0.7),
            ("vela", 0.6),
            ("lub_corrente", 0.5),
            ("fluido_freio", 0.3),
        ],
    ),
    "Troca de relação": (60.0, [("relacao", 1.0)]),
    "Troca de pastilha/lona": (35.0, [("pastilha", 0.6), ("lona", 0.6)]),
    "Troca de pneu": (25.0, [("pneu_traseiro", 0.65), ("pneu_dianteiro", 0.5), ("camara", 0.5)]),
    "Serviço elétrico": (
        50.0,
        [("bateria", 0.4), ("lampada", 0.5), ("regulador", 0.25), ("pisca", 0.3)],
    ),
    "Troca de cabo": (
        30.0,
        [("cabo_embreagem", 0.5), ("cabo_acelerador", 0.5), ("cabo_velocimetro", 0.3)],
    ),
    "Troca de retentor de bengala": (80.0, [("retentor", 1.0)]),
}
SERVICOS_CHUVA = ("Troca de pneu", "Troca de pastilha/lona")

# Probabilidade de cada serviço numa visita de cliente "uso pessoal"
MIX_SERVICOS_PESSOAL = {
    "Troca de óleo": 0.42,
    "Revisão geral": 0.15,
    "Troca de pastilha/lona": 0.12,
    "Troca de pneu": 0.10,
    "Troca de relação": 0.08,
    "Serviço elétrico": 0.05,
    "Troca de cabo": 0.05,
    "Troca de retentor de bengala": 0.03,
}

FORMAS_PAGAMENTO = ["PIX", "Cartão de crédito", "Cartão de débito", "Dinheiro"]
PESOS_PAGAMENTO = [0.40, 0.25, 0.15, 0.20]


@dataclass
class DadosSimulados:
    """Tabelas limpas, antes da sujeira. Datas como `date`, valores como float."""

    produtos: pd.DataFrame
    clientes: pd.DataFrame
    vendas: pd.DataFrame  # uma linha por item vendido no balcão
    ordens_servico: pd.DataFrame
    itens_os: pd.DataFrame
    data_inicio: date
    data_fim: date


# --------------------------------------------------------------------------------------
# Utilitários
# --------------------------------------------------------------------------------------


def subtrair_meses(d: date, meses: int) -> date:
    """Volta `meses` meses a partir de `d` (ajusta o dia para meses mais curtos)."""
    ano, mes = divmod(d.year * 12 + d.month - 1 - meses, 12)
    mes += 1
    ultimo_dia = (date(ano + mes // 12, mes % 12 + 1, 1) - timedelta(days=1)).day
    return date(ano, mes, min(d.day, ultimo_dia))


def arredondar_preco(valor: float) -> float:
    """Arredonda para o padrão de vitrine: R$ xx,90."""
    return max(math.ceil(valor) - 0.10, 0.90)


def proximo_dia_util(d: date) -> date:
    """A loja fecha no domingo: empurra para segunda."""
    return d + timedelta(days=1) if d.weekday() == 6 else d


def remover_acentos(texto: str) -> str:
    """'José' -> 'Jose'."""
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normalizado if not unicodedata.combining(c))


def fator_sazonal(categoria: str, mes: int) -> float:
    """Pneus e freios vendem mais na chuva; acessórios explodem em dezembro."""
    fator = 1.0
    if categoria in (PNEU, FRE) and mes in MESES_CHUVA:
        fator *= 1.6
    if categoria == ACE and mes == 12:
        fator *= 2.5
    return fator


# --------------------------------------------------------------------------------------
# Catálogo de produtos
# --------------------------------------------------------------------------------------


def gerar_produtos(rng: np.random.Generator, inicio: date, fim: date) -> pd.DataFrame:
    """Monta o catálogo (~400 SKUs) com custo, preço e popularidade de cada item."""
    linhas = []
    contador = dict.fromkeys(PREFIXO_SKU.values(), 0)
    for tipo in TIPOS:
        motos = [m for m in MOTOS if m not in tipo.excluir_motos] if tipo.por_moto else [None]
        pesos_marca = np.array([(1 / (i + 1)) ** 0.8 for i in range(len(tipo.marcas))])
        pesos_marca /= pesos_marca.sum()
        for moto in motos:
            for marca, peso_marca in zip(tipo.marcas, pesos_marca, strict=True):
                prefixo = PREFIXO_SKU[tipo.categoria]
                contador[prefixo] += 1
                custo = round(rng.uniform(*tipo.custo), 2)
                participacao = MOTOS[moto] if moto else 1.0
                nome = f"{tipo.nome} {marca}" + (f" - {moto.split(' ', 1)[1]}" if moto else "")
                linhas.append(
                    {
                        "sku": f"{prefixo}-{contador[prefixo]:04d}",
                        "descricao": nome,
                        "categoria": tipo.categoria,
                        "grupo": tipo.grupo,
                        "marca": marca,
                        "compatibilidade": moto or "Universal",
                        "custo": custo,
                        "preco_venda": arredondar_preco(custo * (1 + rng.uniform(*tipo.markup))),
                        # lognormal = cauda longa: poucos itens campeões, muitos que quase não saem
                        "popularidade": tipo.demanda
                        * participacao
                        * peso_marca
                        * rng.lognormal(0, 1.1),
                    }
                )
    produtos = pd.DataFrame(linhas)
    return definir_ciclo_de_vida(produtos, rng, inicio, fim)


def definir_ciclo_de_vida(
    produtos: pd.DataFrame, rng: np.random.Generator, inicio: date, fim: date
) -> pd.DataFrame:
    """Define cadastro e, para ~13% dos SKUs, a data a partir da qual o item parou de girar."""
    n = len(produtos)
    dias_antes = rng.integers(30, 5 * 365, size=n)
    cadastro = [inicio - timedelta(days=int(x)) for x in dias_antes]
    # 15% dos itens foram cadastrados durante o período (lançamentos)
    novos = rng.random(n) < 0.15
    dias_periodo = (fim - inicio).days
    for i in np.flatnonzero(novos):
        cadastro[i] = inicio + timedelta(days=int(rng.integers(0, dias_periodo - 60)))
    produtos["data_cadastro"] = cadastro

    # Itens sem giro: sorteados entre os 60% menos populares (o "encalhe" típico)
    ordem = produtos["popularidade"].rank(pct=True)
    candidatos = np.flatnonzero((ordem <= 0.6).to_numpy() & ~novos)
    encalhados = rng.choice(candidatos, size=round(n * 0.13), replace=False)
    ultima_venda = [fim + timedelta(days=1)] * n  # padrão: vende até o fim
    for i in encalhados:
        ultima_venda[i] = fim - timedelta(days=int(rng.integers(185, 800)))
    produtos["vende_ate"] = ultima_venda
    produtos["sem_giro"] = False
    produtos.loc[encalhados, "sem_giro"] = True
    return produtos


# --------------------------------------------------------------------------------------
# Clientes
# --------------------------------------------------------------------------------------


def gerar_nome(fake: Faker, rng: np.random.Generator) -> str:
    """Nome completo com um ou dois sobrenomes."""
    sobrenomes = [fake.last_name() for _ in range(1 + int(rng.random() < 0.5))]
    return " ".join([fake.first_name(), *sobrenomes])


def gerar_telefone(rng: np.random.Generator) -> str:
    """Celular fictício só com dígitos: DDD + 9 + 8 dígitos."""
    return DDD + "9" + "".join(str(d) for d in rng.integers(0, 10, size=8))


def sortear_moto(rng: np.random.Generator) -> str:
    """Sorteia um modelo de moto conforme a participação na frota da cidade."""
    return str(rng.choice(list(MOTOS), p=list(MOTOS.values())))


def gerar_clientes(fake: Faker, rng: np.random.Generator, inicio: date, fim: date) -> pd.DataFrame:
    """Cria clientes dos perfis motoboy, uso pessoal e frota de empresa."""
    perfis = ["motoboy"] * 220 + ["pessoal"] * 1100 + ["frota"] * 12
    linhas = []
    for id_cliente, perfil in enumerate(perfis, start=1):
        # Base de clientes cresce: parte já existia, parte chega ao longo do período
        cadastro = inicio - timedelta(days=int(rng.integers(0, 3 * 365)))
        if rng.random() < 0.45:
            cadastro = inicio + timedelta(days=int(rng.integers(0, (fim - inicio).days - 20)))
        saida = None
        if rng.random() < (0.25 if perfil == "motoboy" else 0.15):  # clientes que somem
            saida = cadastro + timedelta(days=int(rng.integers(60, 600)))
        n_motos = int(rng.integers(3, 9)) if perfil == "frota" else 1
        motos = [sortear_moto(rng) for _ in range(n_motos)]
        if perfil == "motoboy":  # motoboy prefere CG, Factor e Bros
            motos = [
                str(
                    rng.choice(
                        ["Honda CG 160", "Yamaha Factor 150", "Honda NXR 160 Bros"],
                        p=[0.6, 0.25, 0.15],
                    )
                )
            ]
        linhas.append(
            {
                "id_cliente": id_cliente,
                "nome": fake.company() if perfil == "frota" else gerar_nome(fake, rng),
                "cpf_cnpj": fake.cnpj() if perfil == "frota" else fake.cpf(),
                "tipo_pessoa": "PJ" if perfil == "frota" else "PF",
                "telefone": gerar_telefone(rng),
                "email": None,
                "cidade": CIDADE,
                "uf": UF,
                "data_cadastro": cadastro,
                "perfil": perfil,  # não sai no CSV: o ERP não sabe o perfil, a análise descobre
                "motos": motos,
                "placas": [fake.license_plate() for _ in motos],
                "data_saida": saida,
                "id_duplicado": None,
            }
        )
    clientes = pd.DataFrame(linhas)
    tem_email = rng.random(len(clientes)) < 0.35
    clientes.loc[tem_email, "email"] = [
        remover_acentos(n.split()[0].lower()) + f"{rng.integers(1, 999)}@exemplo.com.br"
        for n in clientes.loc[tem_email, "nome"]
    ]
    return criar_duplicados(clientes, rng, fim)


def variar_grafia(nome: str, rng: np.random.Generator) -> str:
    """Cria uma grafia alternativa do mesmo nome, como um atendente digitaria."""
    partes = nome.split()
    opcoes = [
        lambda: nome.upper(),
        lambda: remover_acentos(nome),
        lambda: nome.replace(" ", "  ", 1),
        lambda: " ".join([partes[0], *(p[0] + "." for p in partes[1:-1]), partes[-1]]),
        lambda: " ".join(partes[:2]),
        lambda: nome.lower() + " ",
    ]
    for indice in rng.permutation(len(opcoes)):
        variante = opcoes[indice]()
        if variante != nome:
            return variante
    return nome.upper()


def criar_duplicados(clientes: pd.DataFrame, rng: np.random.Generator, fim: date) -> pd.DataFrame:
    """Recadastra ~6% das pessoas físicas com outra grafia e outro código."""
    pf = clientes[clientes["tipo_pessoa"] == "PF"]
    originais = pf.sample(frac=0.06, random_state=rng)
    proximo_id = clientes["id_cliente"].max() + 1
    novos = []
    for idx, original in originais.iterrows():
        recadastro = original["data_cadastro"] + timedelta(days=int(rng.integers(30, 400)))
        if recadastro >= fim:
            continue
        copia = original.copy()
        copia["id_cliente"] = proximo_id
        copia["nome"] = variar_grafia(original["nome"], rng)
        copia["data_cadastro"] = recadastro
        copia["telefone"] = original["telefone"] if rng.random() < 0.5 else gerar_telefone(rng)
        copia["cpf_cnpj"] = original["cpf_cnpj"] if rng.random() < 0.4 else None
        clientes.at[idx, "id_duplicado"] = proximo_id
        novos.append(copia)
        proximo_id += 1
    return pd.concat([clientes, pd.DataFrame(novos)], ignore_index=True)


# --------------------------------------------------------------------------------------
# Simulação do movimento (balcão + oficina)
# --------------------------------------------------------------------------------------


class Simulador:
    """Gera pedidos de balcão e ordens de serviço dia a dia, respeitando as regras."""

    def __init__(self, produtos: pd.DataFrame, rng: np.random.Generator, inicio: date, fim: date):
        self.rng = rng
        self.inicio = inicio
        self.fim = fim
        self.popularidade = produtos["popularidade"].to_numpy()
        self.preco = produtos["preco_venda"].to_numpy()
        self.skus = produtos["sku"].to_numpy()
        self.grupo_do_sku = produtos["grupo"].to_numpy()
        self.cadastro = np.array([d.toordinal() for d in produtos["data_cadastro"]])
        self.vende_ate = np.array([d.toordinal() for d in produtos["vende_ate"]])
        self.sazonal = {
            mes: np.array([fator_sazonal(c, mes) for c in produtos["categoria"]])
            for mes in range(1, 13)
        }
        compat = produtos["compatibilidade"].to_numpy()
        grupo = produtos["grupo"].to_numpy()
        self.compativel = {m: (compat == m) | (compat == "Universal") for m in MOTOS}
        self.grupo = {g: grupo == g for g in np.unique(grupo)}
        self.data_reajuste = subtrair_meses(fim, 12)
        self.pedidos: list[dict] = []
        self.itens_pedido: list[dict] = []
        self.ordens: list[dict] = []
        self.itens_ordem: list[dict] = []
        # 3 mecânicos desde o início; o 4º é contratado no 10º mês
        self.mecanicos = [
            ("Marcos Pereira", 1.3, inicio),
            ("Anderson Lima", 1.0, inicio),
            ("Rafael Souza", 1.0, inicio),
            ("Diego Santos", 0.9, subtrair_meses(inicio, -10)),
        ]

    # ---- escolha de SKUs ----
    def pesos(self, d: date, filtro: np.ndarray | None = None) -> np.ndarray:
        """Peso de cada SKU na data: popularidade x sazonalidade x disponibilidade."""
        o = d.toordinal()
        disponivel = (self.cadastro <= o) & (self.vende_ate >= o)
        w = self.popularidade * self.sazonal[d.month] * disponivel
        return w if filtro is None else w * filtro

    def sortear_skus(self, w: np.ndarray, k: int) -> list[int]:
        """Sorteia até k SKUs distintos proporcionalmente aos pesos."""
        validos = np.count_nonzero(w)
        if validos == 0:
            return []
        return list(self.rng.choice(len(w), size=min(k, validos), replace=False, p=w / w.sum()))

    def quantidade(self, i: int, moto: str | None) -> int:
        """Quantidade vendida: óleo pode sair em 2 litros; resto quase sempre 1."""
        if self.grupo_do_sku[i] == "oleo_motor":
            return 2 if moto in MOTOS_2_LITROS_OLEO or self.rng.random() < 0.1 else 1
        return 1 if self.rng.random() < 0.93 else 2

    def desconto(self, perfil: str | None) -> float:
        """Frota tem 10% fixo; balcão às vezes dá 5% ou 10%."""
        if perfil == "frota":
            return 0.10
        return float(self.rng.choice([0.0, 0.05, 0.10], p=[0.85, 0.10, 0.05]))

    def pagamento(self, perfil: str | None) -> str:
        """Frota paga no boleto; demais conforme o mix da cidade."""
        if perfil == "frota":
            return "Boleto 28 dias"
        return str(self.rng.choice(FORMAS_PAGAMENTO, p=PESOS_PAGAMENTO))

    # ---- registros ----
    def registrar_pedido(self, d: date, cliente_id, perfil, skus: list[int], moto=None):
        """Grava um pedido de balcão e seus itens."""
        if not skus:
            return
        chave = len(self.pedidos)
        desconto = self.desconto(perfil)
        self.pedidos.append(
            {
                "chave": chave,
                "data": d,
                "id_cliente": cliente_id,
                "forma_pagamento": self.pagamento(perfil),
            }
        )
        for i in skus:
            self.itens_pedido.append(
                {
                    "chave": chave,
                    "sku": self.skus[i],
                    "quantidade": self.quantidade(i, moto),
                    "preco_unitario": round(self.preco[i] * (1 - desconto), 2),
                    "desconto_pct": desconto,
                }
            )

    def registrar_os(self, d: date, cliente_id, perfil, moto, placa, servico: str):
        """Grava uma OS com mão de obra e as peças do serviço."""
        mao_obra_base, pecas = SERVICOS[servico]
        reajuste = 1.10 if d >= self.data_reajuste else 1.0  # tabela reajustada há 1 ano
        mao_obra = round(mao_obra_base * reajuste * self.rng.uniform(0.9, 1.2) / 5) * 5
        desconto = self.desconto(perfil)
        skus = []
        for grupo, prob in pecas:
            if self.rng.random() < prob or (not skus and grupo == pecas[-1][0]):
                filtro = self.grupo[grupo] & self.compativel[moto]
                skus += self.sortear_skus(self.pesos(d, filtro), 1)
        chave = len(self.ordens)
        self.ordens.append(
            {
                "chave": chave,
                "data_abertura": d,
                "id_cliente": cliente_id,
                "moto": moto,
                "placa": placa,
                "servico": servico,
                "mecanico": self.escolher_mecanico(d),
                "valor_mao_obra": float(mao_obra),
                "forma_pagamento": self.pagamento(perfil),
            }
        )
        for i in skus:
            self.itens_ordem.append(
                {
                    "chave": chave,
                    "sku": self.skus[i],
                    "quantidade": self.quantidade(i, moto),
                    "preco_unitario": round(self.preco[i] * (1 - desconto), 2),
                }
            )

    def escolher_mecanico(self, d: date) -> str:
        """Sorteia entre os mecânicos já contratados na data."""
        ativos = [(nome, peso) for nome, peso, desde in self.mecanicos if desde <= d]
        pesos = np.array([p for _, p in ativos])
        return ativos[self.rng.choice(len(ativos), p=pesos / pesos.sum())][0]

    # ---- comportamento ----
    def balcao_anonimo(self):
        """Vendas de 'consumidor final' sem cadastro, com tendência de crescimento."""
        total_dias = (self.fim - self.inicio).days
        for n in range(total_dias + 1):
            d = self.inicio + timedelta(days=n)
            if d.weekday() == 6:
                continue
            lam = 20 * (0.6 if d.weekday() == 5 else 1.0) * (1 + 0.18 * n / total_dias)
            lam *= 1.2 if d.month == 12 else 1.0
            w = self.pesos(d)
            for _ in range(self.rng.poisson(lam)):
                k = 1 + self.rng.poisson(0.4)
                self.registrar_pedido(d, None, None, self.sortear_skus(w, k))

    def visitas(self, inicio: date, fim: date, media: float, desvio: float, minimo: int):
        """Datas de visita de um cliente, com intervalos aleatórios entre elas."""
        datas = []
        d = inicio + timedelta(days=int(self.rng.integers(0, max(int(media), 1))))
        while d <= fim:
            d = proximo_dia_util(d)
            if d <= fim:
                datas.append(d)
            d += timedelta(days=max(minimo, int(self.rng.normal(media, desvio))))
        return datas

    def id_na_data(self, cliente: pd.Series, d: date):
        """Depois do recadastro, metade das compras cai no código duplicado."""
        dup = cliente["id_duplicado"]
        if dup is not None and not pd.isna(dup) and d >= self.data_dup[int(dup)]:
            return int(dup) if self.rng.random() < 0.5 else cliente["id_cliente"]
        return cliente["id_cliente"]

    def clientes_cadastrados(self, clientes: pd.DataFrame):
        """Simula as visitas de cada cliente conforme o perfil."""
        self.data_dup = dict(zip(clientes["id_cliente"], clientes["data_cadastro"], strict=True))
        originais = clientes[~clientes["id_cliente"].isin(clientes["id_duplicado"].dropna())]
        for _, c in originais.iterrows():
            ini = max(c["data_cadastro"], self.inicio)
            fim = self.fim if pd.isna(c["data_saida"]) else min(c["data_saida"], self.fim)
            if ini > fim:
                continue
            {"motoboy": self.motoboy, "pessoal": self.pessoal, "frota": self.frota}[c["perfil"]](
                c, ini, fim
            )

    def servico_extra_motoboy(self, d: date) -> str | None:
        """Motoboy roda muito: às vezes junta outro serviço à troca de óleo."""
        chuva = 1.6 if d.month in MESES_CHUVA else 1.0
        r = self.rng.random()
        for servico, prob in (
            ("Troca de pneu", 0.06 * chuva),
            ("Troca de pastilha/lona", 0.06 * chuva),
            ("Troca de relação", 0.05),
            ("Troca de cabo", 0.02),
        ):
            if r < prob:
                return servico
            r -= prob
        return None

    def motoboy(self, c: pd.Series, ini: date, fim: date):
        """Troca de óleo a cada ~30 dias, na oficina ou comprando no balcão."""
        moto, placa = c["motos"][0], c["placas"][0]
        for d in self.visitas(ini, fim, media=30, desvio=5, minimo=18):
            cid = self.id_na_data(c, d)
            if self.rng.random() < 0.65:
                self.registrar_os(d, cid, "motoboy", moto, placa, "Troca de óleo")
            else:
                skus = self.sortear_skus(self.pesos(d, self.grupo["oleo_motor"]), 1)
                if self.rng.random() < 0.2:
                    skus += self.sortear_skus(self.pesos(d, self.grupo["lub_corrente"]), 1)
                self.registrar_pedido(d, cid, "motoboy", skus, moto)
            extra = self.servico_extra_motoboy(d)
            if extra:
                self.registrar_os(d, cid, "motoboy", moto, placa, extra)

    def pessoal(self, c: pd.Series, ini: date, fim: date):
        """Visitas espaçadas: serviço na oficina ou compra de peça/acessório no balcão."""
        moto, placa = c["motos"][0], c["placas"][0]
        servicos = list(MIX_SERVICOS_PESSOAL)
        for d in self.visitas(ini, fim, media=95, desvio=40, minimo=20):
            cid = self.id_na_data(c, d)
            if self.rng.random() < 0.55:
                pesos = np.array(
                    [
                        MIX_SERVICOS_PESSOAL[s]
                        * (1.6 if s in SERVICOS_CHUVA and d.month in MESES_CHUVA else 1.0)
                        for s in servicos
                    ]
                )
                servico = servicos[self.rng.choice(len(servicos), p=pesos / pesos.sum())]
                self.registrar_os(d, cid, "pessoal", moto, placa, servico)
            else:
                k = 1 + self.rng.poisson(0.5)
                skus = self.sortear_skus(self.pesos(d, self.compativel[moto]), k)
                self.registrar_pedido(d, cid, "pessoal", skus, moto)

    def frota(self, c: pd.Series, ini: date, fim: date):
        """Empresa manda as motos uma vez por mês para manutenção preventiva."""
        for d in self.visitas(ini, fim, media=30, desvio=4, minimo=20):
            for moto, placa in zip(c["motos"], c["placas"], strict=True):
                if self.rng.random() < 0.7:
                    servico = "Revisão geral" if self.rng.random() < 0.3 else "Troca de óleo"
                    self.registrar_os(d, c["id_cliente"], "frota", moto, placa, servico)


def montar_tabelas(sim: Simulador) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Ordena por data, numera pedidos/OS e define status e data de conclusão."""
    pedidos = pd.DataFrame(sim.pedidos).sort_values(["data", "chave"], kind="stable")
    pedidos["numero_pedido"] = np.arange(10001, 10001 + len(pedidos))
    vendas = pd.DataFrame(sim.itens_pedido).merge(pedidos, on="chave")
    vendas = vendas.sort_values(["numero_pedido", "sku"]).drop(columns="chave")
    vendas = vendas[
        [
            "numero_pedido",
            "data",
            "id_cliente",
            "sku",
            "quantidade",
            "preco_unitario",
            "desconto_pct",
            "forma_pagamento",
        ]
    ]

    ordens = pd.DataFrame(sim.ordens).sort_values(["data_abertura", "chave"], kind="stable")
    ordens["numero_os"] = np.arange(1, 1 + len(ordens))
    rng = sim.rng
    dias = rng.choice([0, 0, 0, 1, 1, 2, 3], size=len(ordens))
    longos = (
        ordens["servico"]
        .isin(["Troca de relação", "Troca de retentor de bengala", "Revisão geral"])
        .to_numpy()
    )
    dias = dias + longos * rng.integers(0, 2, size=len(ordens))
    conclusao = [
        proximo_dia_util(a + timedelta(days=int(x)))
        for a, x in zip(ordens["data_abertura"], dias, strict=True)
    ]
    status = np.where(rng.random(len(ordens)) < 0.03, "Cancelada", "Concluída").astype(object)
    em_aberto = np.array([c > sim.fim for c in conclusao])
    status[em_aberto] = "Em andamento"
    ordens["status"] = status
    ordens["data_conclusao"] = [
        None if s != "Concluída" else c for s, c in zip(status, conclusao, strict=True)
    ]
    itens_os = pd.DataFrame(sim.itens_ordem).merge(ordens[["chave", "numero_os"]], on="chave")
    itens_os = itens_os.sort_values(["numero_os", "sku"]).drop(columns="chave")
    itens_os = itens_os[["numero_os", "sku", "quantidade", "preco_unitario"]]
    ordens = ordens[
        [
            "numero_os",
            "data_abertura",
            "data_conclusao",
            "status",
            "id_cliente",
            "moto",
            "placa",
            "servico",
            "mecanico",
            "valor_mao_obra",
            "forma_pagamento",
        ]
    ]
    return vendas, ordens, itens_os


def calcular_estoque(
    produtos: pd.DataFrame,
    vendas: pd.DataFrame,
    ordens: pd.DataFrame,
    itens_os: pd.DataFrame,
    rng: np.random.Generator,
    fim: date,
) -> pd.DataFrame:
    """Estoque atual coerente com o giro recente; encalhados ficam com saldo parado."""
    corte = fim - timedelta(days=180)
    os_recentes = ordens.loc[ordens["data_abertura"] >= corte, "numero_os"]
    recentes = pd.concat(
        [
            vendas.loc[vendas["data"] >= corte, ["sku", "quantidade"]],
            itens_os.loc[itens_os["numero_os"].isin(os_recentes), ["sku", "quantidade"]],
        ]
    )
    giro = recentes.groupby("sku")["quantidade"].sum() / 6
    media_mensal = produtos["sku"].map(giro).fillna(0).to_numpy()
    n = len(produtos)
    estoque = np.maximum(1, rng.poisson(media_mensal * rng.uniform(0.3, 2.5, size=n)))
    parado = produtos["sem_giro"].to_numpy() | (media_mensal == 0)
    caro = produtos["custo"].to_numpy() > 100
    estoque[parado] = np.where(
        caro[parado], rng.integers(2, 7, size=parado.sum()), rng.integers(3, 16, size=parado.sum())
    )
    ruptura = (~parado) & (rng.random(n) < 0.06)  # itens que acabaram e ninguém repôs
    estoque[ruptura] = 0
    produtos["estoque_atual"] = estoque
    produtos["estoque_minimo"] = np.maximum(1, np.ceil(media_mensal * 0.5)).astype(int)
    return produtos


def simular_dados(seed: int = SEED_PADRAO, data_fim: date = DATA_FIM_PADRAO) -> DadosSimulados:
    """Gera todas as tabelas limpas de forma reproduzível."""
    fim = data_fim
    inicio = subtrair_meses(fim, MESES_HISTORICO) + timedelta(days=1)
    rng = np.random.default_rng(seed)
    fake = Faker("pt_BR")
    fake.seed_instance(seed)

    produtos = gerar_produtos(rng, inicio, fim)
    clientes = gerar_clientes(fake, rng, inicio, fim)
    sim = Simulador(produtos, rng, inicio, fim)
    sim.balcao_anonimo()
    sim.clientes_cadastrados(clientes)
    vendas, ordens, itens_os = montar_tabelas(sim)
    produtos = calcular_estoque(produtos, vendas, ordens, itens_os, rng, fim)
    return DadosSimulados(produtos, clientes, vendas, ordens, itens_os, inicio, fim)


# --------------------------------------------------------------------------------------
# Sujeira de ERP
# --------------------------------------------------------------------------------------


def formatar_data_suja(d: date | None, rng: np.random.Generator) -> str:
    """Mistura formatos de data como acontece em exportações de sistemas diferentes."""
    if d is None or pd.isna(d):
        return ""
    formato = rng.choice(
        ["%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%Y"], p=[0.70, 0.18, 0.07, 0.05]
    )
    return d.strftime(formato)


def formatar_decimal_br(valor: float) -> str:
    """1234.5 -> '1234,50' (decimal com vírgula, padrão de ERP brasileiro)."""
    return f"{valor:.2f}".replace(".", ",")


def formatar_moeda_br(valor: float) -> str:
    """1234.5 -> 'R$ 1.234,50'."""
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def formatar_telefone_sujo(digitos: str | None, rng: np.random.Generator) -> str:
    """Cada atendente digita o telefone de um jeito."""
    if not isinstance(digitos, str) or not digitos:  # None ou NaN do pandas
        return ""
    ddd, numero = digitos[:2], digitos[2:]
    formatos = [
        f"({ddd}) {numero[:5]}-{numero[5:]}",
        digitos,
        f"{ddd} {numero[0]} {numero[1:5]} {numero[5:]}",
        f"{numero[:5]}-{numero[5:]}",  # sem DDD
    ]
    return formatos[rng.choice(len(formatos), p=[0.5, 0.25, 0.15, 0.10])]


def zerar_alguns(valores: pd.Series, rng: np.random.Generator, taxa: float) -> pd.Series:
    """Zera uma fração dos preços (cadastro incompleto / erro de digitação)."""
    valores = valores.copy()
    valores[rng.random(len(valores)) < taxa] = 0.0
    return valores


def aplicar_sujeira(dados: DadosSimulados, seed: int = SEED_PADRAO) -> dict[str, pd.DataFrame]:
    """Converte as tabelas limpas no formato 'sujo' que sai do ERP."""
    rng = np.random.default_rng(seed + 1)

    produtos = dados.produtos.copy()
    preco = zerar_alguns(produtos["preco_venda"], rng, 0.015)
    com_rs = rng.random(len(produtos)) < 0.10  # alguns preços exportados como texto "R$"
    produtos["preco_venda"] = [
        formatar_moeda_br(v) if rs else formatar_decimal_br(v)
        for v, rs in zip(preco, com_rs, strict=True)
    ]
    produtos["custo"] = produtos["custo"].map(formatar_decimal_br)
    produtos["data_cadastro"] = [d.isoformat() for d in produtos["data_cadastro"]]
    produtos = produtos[
        [
            "sku",
            "descricao",
            "categoria",
            "marca",
            "compatibilidade",
            "custo",
            "preco_venda",
            "estoque_atual",
            "estoque_minimo",
            "data_cadastro",
        ]
    ]

    clientes = dados.clientes.copy()
    sem_telefone = rng.random(len(clientes)) < 0.15
    clientes.loc[sem_telefone, "telefone"] = None
    clientes["telefone"] = [formatar_telefone_sujo(t, rng) for t in clientes["telefone"]]
    clientes["data_cadastro"] = [formatar_data_suja(d, rng) for d in clientes["data_cadastro"]]
    clientes = clientes[
        [
            "id_cliente",
            "nome",
            "cpf_cnpj",
            "tipo_pessoa",
            "telefone",
            "email",
            "cidade",
            "uf",
            "data_cadastro",
        ]
    ]

    vendas = dados.vendas.copy()
    vendas["data"] = [formatar_data_suja(d, rng) for d in vendas["data"]]
    vendas["id_cliente"] = vendas["id_cliente"].astype("Int64")
    vendas["preco_unitario"] = zerar_alguns(vendas["preco_unitario"], rng, 0.007).map(
        formatar_decimal_br
    )
    vendas["desconto_pct"] = vendas["desconto_pct"].map(formatar_decimal_br)

    ordens = dados.ordens_servico.copy()
    ordens["data_abertura"] = [formatar_data_suja(d, rng) for d in ordens["data_abertura"]]
    ordens["data_conclusao"] = [formatar_data_suja(d, rng) for d in ordens["data_conclusao"]]
    ordens["valor_mao_obra"] = ordens["valor_mao_obra"].map(formatar_decimal_br)

    itens_os = dados.itens_os.copy()
    itens_os["preco_unitario"] = zerar_alguns(itens_os["preco_unitario"], rng, 0.005).map(
        formatar_decimal_br
    )

    return {
        "produtos": produtos,
        "clientes": clientes,
        "vendas": vendas,
        "ordens_servico": ordens,
        "itens_os": itens_os,
    }


def salvar_csvs(tabelas: dict[str, pd.DataFrame], pasta: Path = PASTA_SAIDA) -> None:
    """Grava cada tabela como CSV com ';' (padrão de Excel/ERP no Brasil)."""
    pasta.mkdir(parents=True, exist_ok=True)
    for nome, df in tabelas.items():
        caminho = pasta / f"{nome}.csv"
        df.to_csv(caminho, sep=";", index=False, encoding="utf-8-sig", lineterminator="\r\n")
        print(f"  {caminho.name:<22} {len(df):>7} linhas")


def main() -> None:
    """Ponto de entrada da linha de comando."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=SEED_PADRAO)
    parser.add_argument(
        "--data-fim",
        type=lambda t: date.today() if t == "hoje" else date.fromisoformat(t),
        default=DATA_FIM_PADRAO,
        help=f"último dia do histórico (aaaa-mm-dd ou 'hoje'); padrão: {DATA_FIM_PADRAO}",
    )
    args = parser.parse_args()
    dados = simular_dados(args.seed, args.data_fim)
    print(f"Período: {dados.data_inicio:%d/%m/%Y} a {dados.data_fim:%d/%m/%Y}")
    salvar_csvs(aplicar_sujeira(dados, args.seed))


if __name__ == "__main__":
    main()
