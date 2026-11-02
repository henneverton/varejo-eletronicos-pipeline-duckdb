"""Camada refined no DuckDB (spec 002).

Executar com:  uv run python refined.py

Lê o schema `raw` de data/projeto.duckdb (nunca os CSVs) e grava o schema
`refined`: mesmas seis tabelas, nomes em português, tipos corretos, texto
aparado e três tratamentos de qualidade. A etapa 3 só consulta a refined.

Regras e por que existem
------------------------
1. Nomes: tabelas e colunas em português, snake_case, sem acento nem espaço,
   mesma ordem do raw. Só os nomes mudam; os valores continuam em inglês.
   Motivo: o nome é digitado de memória nos JOINs; traduzir valores seria
   alterar o dado e quebraria filtros como pais = 'United States'.
2. Transformações permitidas (e só estas): trim; conversão de tipo; renomear;
   T1, T2 e T3.
   - Datas M/D/AAAA com formato explícito, nunca inferido (evita M/D x D/M).
   - Preço e custo: trim, remover `$` e vírgula de milhar, DECIMAL(10,2).
   - Câmbio DECIMAL(10,4); chaves, quantidade e m² INTEGER.
   - chave_subcategoria, chave_categoria e cep ficam VARCHAR: têm zero à
     esquerda (0101, 01) e o CEP tem 2 a 8 caracteres conforme o país.
   - T1: CEP completado com zeros à esquerda até o tamanho oficial do país
     (Australia 4; France, Germany, Italy, United States 5), só quando tem
     menos dígitos. Motivo: o zero foi perdido na origem e é parte do CEP.
   - T2: remove `?` de nomes e aparar. Motivo: o caractere não é do nome.
   - T3: cidade inteira em CAIXA ALTA vira Title Case (início, depois de
     espaço, de hífen e de apóstrofo logo após uma única letra). Caixa mista
     não muda. Motivo: sem isso um gráfico separaria SYDNEY de Sydney.
     Limitação aceita: partículas também ficam maiúsculas (Aix-En-Provence).
   A conversão é estrita: valor que não converte interrompe a execução e
   nunca vira nulo. Motivo: nulo só pode existir se já existia no raw.
3. Proibições: nenhuma linha descartada ou deduplicada, nenhuma coluna nova,
   nenhum outro valor corrigido, nulo continua nulo. Chave repetida não é
   resolvida: a execução falha. Motivo: deduplicar é decisão de negócio.
4. Reexecução e atomicidade: CREATE OR REPLACE TABLE dentro de uma única
   transação; qualquer falha faz ROLLBACK. Motivo: nunca um refined com
   metade das tabelas novas. Nada é escrito em raw.
5. Dicionário: refined.dicionario_dados tem as 37 linhas do raw com os novos
   nomes e a descrição traduzida (tabela fixa no código). Motivo: o dicionário
   só serve se cita os nomes que existem no banco.
6. Conferências antes do COMMIT: contagem refined = raw; pares (tabela,
   campo) do dicionário = colunas de refined; nulos de data_entrega e
   metros_quadrados iguais aos do raw; linhas mudadas por T1/T2/T3 = 836/3/
   3.885; 0 chaves repetidas. Motivo: provar o que foi gravado.
7. Erro: antes de qualquer escrita verifica o banco e as seis tabelas de raw;
   faltando algo, lista, sugere `uv run python ingestao.py` e sai com 1, sem
   criar banco, pasta ou schema. Lock de outro processo também sai com 1.
8. Caminhos: calculados a partir deste arquivo; main() recebe o banco como
   parâmetro. Ordem: verificar arquivo -> conectar -> verificar raw ->
   transação -> fechar. Importar o módulo não toca o disco.

Achados de qualidade (documentação oficial; números de 2026-11-02)
------------------------------------------------------------------
Q1  Delivery Date nulo em 49.719 vendas (79,07%): todas de loja física
    (chave_loja <> 0); as 13.165 online têm data. Mantido nulo.
Q2  Square Meters nulo em 1 loja: a online (chave_loja = 0). Mantido nulo.
Q3  State Code = texto 'NA' em 10 clientes de Napoli. Não é nulo. Mantido.
Q4  No Reino Unido (1.944 clientes) State Code traz nome de condado, não
    sigla (igual a State). Mantido.
Q5  CEP sem zero à esquerda: AU 13, FR 42, DE 118, IT 70, US 593. TRATADO (T1).
Q6  Três nomes com `?` espúrio. TRATADO (T2).
Q7  3.885 cidades em CAIXA ALTA (AU 1.360, FR 636, UK 1.879, CA 10) e 11.381
    em caixa mista. TRATADO (T3).
Q8  114 itens vendidos a clientes de 14-15 anos na data do pedido. Mantido.
Q9  3.379 clientes sem compra; 25 produtos nunca vendidos; 9 lojas físicas
    sem venda. Mantido.
Q10 taxa_cambio = unidades da moeda por 1 USD (converter para USD = dividir).
    Cobre 2.243 dias; as vendas usam 1.641. Mantido.
Q11 vendas não tem preço: receita = quantidade x preco_unitario_usd, preço de
    lista atual, sem histórico nem desconto. Mantido (sem coluna derivada).
Q12 O dicionário original chama a tabela de "Exchange Rates"; no banco é
    exchange_rates (raw) e taxas_cambio (refined). Resolvido pela tradução.
Q13 Preço e custo com vírgula de milhar ($2,899.99) em 158 produtos (custo em
    14 deles). Convertido: a vírgula é removida na conversão de tipo.
"""

import sys
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parent
ARQUIVO_BANCO = RAIZ / "data" / "projeto.duckdb"

ORIGEM = "raw"
DESTINO = "refined"

# Linhas mudadas por T1 (cep), T2 (nome) e T3 (cidade) no banco real.
# Constante de módulo para os testes (que usam dados pequenos) poderem trocá-la.
ESPERADO_TRATAMENTOS = (836, 3, 3885)

# (origem, destino), na ordem em que a saída é impressa.
TABELAS = [
    ("sales", "vendas"),
    ("customers", "clientes"),
    ("products", "produtos"),
    ("stores", "lojas"),
    ("exchange_rates", "taxas_cambio"),
    ("data_dictionary", "dicionario_dados"),
]

CHAVES = {
    "vendas": ["numero_pedido", "item_pedido"],
    "clientes": ["chave_cliente"],
    "produtos": ["chave_produto"],
    "lojas": ["chave_loja"],
    "taxas_cambio": ["data", "moeda"],
    "dicionario_dados": ["tabela", "campo"],
}

# SELECTs validados em modo leitura antes de escrever este script.
SELECTS = {
    "vendas": """
        SELECT
            CAST(trim("Order Number") AS INTEGER) AS numero_pedido,
            CAST(trim("Line Item") AS INTEGER) AS item_pedido,
            CAST(strptime(trim("Order Date"), '%m/%d/%Y') AS DATE) AS data_pedido,
            CAST(strptime(trim("Delivery Date"), '%m/%d/%Y') AS DATE) AS data_entrega,
            CAST(trim("CustomerKey") AS INTEGER) AS chave_cliente,
            CAST(trim("StoreKey") AS INTEGER) AS chave_loja,
            CAST(trim("ProductKey") AS INTEGER) AS chave_produto,
            CAST(trim("Quantity") AS INTEGER) AS quantidade,
            trim("Currency Code") AS codigo_moeda
        FROM raw.sales
    """,
    "clientes": """
        WITH b AS (
            SELECT
                trim("CustomerKey") AS k, trim("Gender") AS g, trim("Name") AS n,
                trim("City") AS c, trim("State Code") AS sc, trim("State") AS st,
                trim("Zip Code") AS z, trim("Country") AS p,
                trim("Continent") AS co, trim("Birthday") AS bd
            FROM raw.customers
        )
        SELECT
            CAST(k AS INTEGER) AS chave_cliente,
            g AS genero,
            trim(replace(n, '?', '')) AS nome,
            CASE WHEN c = upper(c) THEN array_to_string(
                list_transform(str_split(lower(c), ''), lambda ch, i: CASE
                    WHEN i = 1 OR lower(c)[i-1] IN (' ', '-')
                        OR (lower(c)[i-1] = '''' AND i >= 3
                            AND (i = 3 OR lower(c)[i-3] IN (' ', '-')))
                    THEN upper(ch) ELSE ch END), '')
                ELSE c END AS cidade,
            sc AS codigo_estado,
            st AS estado,
            CASE
                WHEN p = 'Australia' AND length(z) < 4 THEN lpad(z, 4, '0')
                WHEN p IN ('France', 'Germany', 'Italy', 'United States')
                    AND length(z) < 5 THEN lpad(z, 5, '0')
                ELSE z END AS cep,
            p AS pais,
            co AS continente,
            CAST(strptime(bd, '%m/%d/%Y') AS DATE) AS data_nascimento
        FROM b
    """,
    "produtos": """
        SELECT
            CAST(trim("ProductKey") AS INTEGER) AS chave_produto,
            trim("Product Name") AS nome_produto,
            trim("Brand") AS marca,
            trim("Color") AS cor,
            CAST(replace(replace(trim("Unit Cost USD"), '$', ''), ',', '')
                AS DECIMAL(10,2)) AS custo_unitario_usd,
            CAST(replace(replace(trim("Unit Price USD"), '$', ''), ',', '')
                AS DECIMAL(10,2)) AS preco_unitario_usd,
            trim("SubcategoryKey") AS chave_subcategoria,
            trim("Subcategory") AS subcategoria,
            trim("CategoryKey") AS chave_categoria,
            trim("Category") AS categoria
        FROM raw.products
    """,
    "lojas": """
        SELECT
            CAST(trim("StoreKey") AS INTEGER) AS chave_loja,
            trim("Country") AS pais,
            trim("State") AS estado,
            CAST(trim("Square Meters") AS INTEGER) AS metros_quadrados,
            CAST(strptime(trim("Open Date"), '%m/%d/%Y') AS DATE) AS data_abertura
        FROM raw.stores
    """,
    "taxas_cambio": """
        SELECT
            CAST(strptime(trim("Date"), '%m/%d/%Y') AS DATE) AS data,
            trim("Currency") AS moeda,
            CAST(trim("Exchange") AS DECIMAL(10,4)) AS taxa_cambio
        FROM raw.exchange_rates
    """,
}

# Nome da tabela no dicionário original -> (tabela refined, {campo raw: campo refined})
CAMPOS = {
    "Sales": ("vendas", {
        "Order Number": "numero_pedido", "Line Item": "item_pedido",
        "Order Date": "data_pedido", "Delivery Date": "data_entrega",
        "CustomerKey": "chave_cliente", "StoreKey": "chave_loja",
        "ProductKey": "chave_produto", "Quantity": "quantidade",
        "Currency Code": "codigo_moeda",
    }),
    "Customers": ("clientes", {
        "CustomerKey": "chave_cliente", "Gender": "genero", "Name": "nome",
        "City": "cidade", "State Code": "codigo_estado", "State": "estado",
        "Zip Code": "cep", "Country": "pais", "Continent": "continente",
        "Birthday": "data_nascimento",
    }),
    "Products": ("produtos", {
        "ProductKey": "chave_produto", "Product Name": "nome_produto",
        "Brand": "marca", "Color": "cor", "Unit Cost USD": "custo_unitario_usd",
        "Unit Price USD": "preco_unitario_usd", "SubcategoryKey": "chave_subcategoria",
        "Subcategory": "subcategoria", "CategoryKey": "chave_categoria",
        "Category": "categoria",
    }),
    "Stores": ("lojas", {
        "StoreKey": "chave_loja", "Country": "pais", "State": "estado",
        "Square Meters": "metros_quadrados", "Open Date": "data_abertura",
    }),
    "Exchange Rates": ("taxas_cambio", {
        "Date": "data", "Currency": "moeda", "Exchange": "taxa_cambio",
    }),
}

# Tradução literal e fixa (não há tradutor automático no projeto).
DESCRICOES = {
    ("vendas", "numero_pedido"): "Identificador único de cada pedido",
    ("vendas", "item_pedido"): "Identifica cada produto comprado dentro de um pedido",
    ("vendas", "data_pedido"): "Data em que o pedido foi feito",
    ("vendas", "data_entrega"): "Data em que o pedido foi entregue",
    ("vendas", "chave_cliente"): "Chave única que identifica o cliente que fez o pedido",
    ("vendas", "chave_loja"): "Chave única que identifica a loja que processou o pedido",
    ("vendas", "chave_produto"): "Chave única que identifica o produto comprado",
    ("vendas", "quantidade"): "Número de itens comprados",
    ("vendas", "codigo_moeda"): "Moeda usada no processamento do pedido",
    ("clientes", "chave_cliente"): "Chave primária que identifica os clientes",
    ("clientes", "genero"): "Gênero do cliente",
    ("clientes", "nome"): "Nome completo do cliente",
    ("clientes", "cidade"): "Cidade do cliente",
    ("clientes", "codigo_estado"): "Estado do cliente (abreviado)",
    ("clientes", "estado"): "Estado do cliente (nome completo)",
    ("clientes", "cep"): "CEP do cliente",
    ("clientes", "pais"): "País do cliente",
    ("clientes", "continente"): "Continente do cliente",
    ("clientes", "data_nascimento"): "Data de nascimento do cliente",
    ("produtos", "chave_produto"): "Chave primária que identifica os produtos",
    ("produtos", "nome_produto"): "Nome do produto",
    ("produtos", "marca"): "Marca do produto",
    ("produtos", "cor"): "Cor do produto",
    ("produtos", "custo_unitario_usd"): "Custo de produção do produto em USD",
    ("produtos", "preco_unitario_usd"): "Preço de lista do produto em USD",
    ("produtos", "chave_subcategoria"): "Chave que identifica as subcategorias de produto",
    ("produtos", "subcategoria"): "Nome da subcategoria do produto",
    ("produtos", "chave_categoria"): "Chave que identifica as categorias de produto",
    ("produtos", "categoria"): "Nome da categoria do produto",
    ("lojas", "chave_loja"): "Chave primária que identifica as lojas",
    ("lojas", "pais"): "País da loja",
    ("lojas", "estado"): "Estado da loja",
    ("lojas", "metros_quadrados"): "Área da loja em metros quadrados",
    ("lojas", "data_abertura"): "Data de abertura da loja",
    ("taxas_cambio", "data"): "Data",
    ("taxas_cambio", "moeda"): "Código da moeda",
    ("taxas_cambio", "taxa_cambio"): "Taxa de câmbio em relação ao USD",
}


class ErroRefined(Exception):
    """Falha de verificação ou conferência: a transação deve ser desfeita."""


def formatar_milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def contar(con: duckdb.DuckDBPyConnection, tabela_completa: str) -> int:
    # fetchall (não fetchone): fetchone deixa o resultado aberto no DuckDB 2.x
    return con.execute(f"SELECT count(*) FROM {tabela_completa}").fetchall()[0][0]


def tabelas_raw_faltando(con: duckdb.DuckDBPyConnection) -> list[str]:
    existentes = {
        linha[0]
        for linha in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
            [ORIGEM],
        ).fetchall()
    }
    return [f"{ORIGEM}.{origem}" for origem, _ in TABELAS if origem not in existentes]


def criar_tabela(con: duckdb.DuckDBPyConnection, destino: str, select: str) -> None:
    try:
        con.execute(f"CREATE OR REPLACE TABLE {DESTINO}.{destino} AS {select}")
    except duckdb.Error as e:
        raise ErroRefined(f"Falha ao criar {DESTINO}.{destino}: {e}") from e


def criar_dicionario(con: duckdb.DuckDBPyConnection) -> None:
    linhas = con.execute(
        f'SELECT trim("Table"), trim("Field") FROM {ORIGEM}.data_dictionary ORDER BY rowid'
    ).fetchall()
    traduzidas = []
    for tabela_raw, campo_raw in linhas:
        try:
            tabela, campos = CAMPOS[tabela_raw]
            campo = campos[campo_raw]
            traduzidas.append((tabela, campo, DESCRICOES[(tabela, campo)]))
        except KeyError as e:
            raise ErroRefined(
                f"Falha ao criar {DESTINO}.dicionario_dados: sem tradução para "
                f"{tabela_raw}.{campo_raw} ({e})"
            ) from e
    con.execute(
        f"CREATE OR REPLACE TABLE {DESTINO}.dicionario_dados "
        "(tabela VARCHAR, campo VARCHAR, descricao VARCHAR)"
    )
    con.executemany(f"INSERT INTO {DESTINO}.dicionario_dados VALUES (?, ?, ?)", traduzidas)


def criar_refined(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {DESTINO}")
    for _, destino in TABELAS:
        if destino == "dicionario_dados":
            criar_dicionario(con)
        else:
            criar_tabela(con, destino, SELECTS[destino])


def conferir_contagens(con: duckdb.DuckDBPyConnection) -> None:
    for origem, destino in TABELAS:
        m = contar(con, f"{ORIGEM}.{origem}")
        n = contar(con, f"{DESTINO}.{destino}")
        if m != n:
            raise ErroRefined(
                f"Contagem diverge em {DESTINO}.{destino}: raw tem {m}, refined tem {n}"
            )


def conferir_dicionario(con: duckdb.DuckDBPyConnection) -> None:
    no_dicionario = set(
        con.execute(f"SELECT tabela, campo FROM {DESTINO}.dicionario_dados").fetchall()
    )
    dados = [destino for _, destino in TABELAS if destino != "dicionario_dados"]
    colunas = set(
        con.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            f"WHERE table_schema = '{DESTINO}' AND table_name IN "
            f"({', '.join(repr(t) for t in dados)})"
        ).fetchall()
    )
    sem_coluna = sorted(no_dicionario - colunas)
    sem_dicionario = sorted(colunas - no_dicionario)
    if sem_coluna or sem_dicionario:
        raise ErroRefined(
            "Dicionário e colunas não batem. "
            f"No dicionário sem coluna: {sem_coluna}. Coluna sem dicionário: {sem_dicionario}"
        )


def conferir_nulos(con: duckdb.DuckDBPyConnection) -> None:
    pares = [
        ("vendas", "data_entrega", "sales", '"Delivery Date"'),
        ("lojas", "metros_quadrados", "stores", '"Square Meters"'),
    ]
    for destino, coluna, origem, coluna_raw in pares:
        n_raw = con.execute(
            f"SELECT count(*) FROM {ORIGEM}.{origem} WHERE {coluna_raw} IS NULL"
        ).fetchall()[0][0]
        n_ref = con.execute(
            f"SELECT count(*) FROM {DESTINO}.{destino} WHERE {coluna} IS NULL"
        ).fetchall()[0][0]
        if n_raw != n_ref:
            raise ErroRefined(
                f"Nulos de {DESTINO}.{destino}.{coluna} divergem: raw {n_raw}, refined {n_ref}"
            )


def conferir_tratamentos(con: duckdb.DuckDBPyConnection) -> None:
    obtido = con.execute(
        f"""
        SELECT
            count(*) FILTER (WHERE r."Zip Code" IS DISTINCT FROM c.cep),
            count(*) FILTER (WHERE r."Name" IS DISTINCT FROM c.nome),
            count(*) FILTER (WHERE r."City" IS DISTINCT FROM c.cidade)
        FROM {DESTINO}.clientes c
        JOIN {ORIGEM}.customers r ON c.chave_cliente = CAST(trim(r."CustomerKey") AS INTEGER)
        """
    ).fetchall()[0]
    if tuple(obtido) != tuple(ESPERADO_TRATAMENTOS):
        raise ErroRefined(
            "Tratamentos divergem (cep, nome, cidade): "
            f"esperado {tuple(ESPERADO_TRATAMENTOS)}, obtido {tuple(obtido)}"
        )


def conferir_chaves(con: duckdb.DuckDBPyConnection) -> None:
    for _, destino in TABELAS:
        cols = ", ".join(CHAVES[destino])
        repetidas = con.execute(
            f"SELECT {cols}, count(*) FROM {DESTINO}.{destino} "
            f"GROUP BY {cols} HAVING count(*) > 1 LIMIT 10"
        ).fetchall()
        if repetidas:
            raise ErroRefined(
                f"Chave repetida em {DESTINO}.{destino} ({cols}); primeiras: {repetidas}"
            )


def conferir(con: duckdb.DuckDBPyConnection) -> None:
    conferir_contagens(con)
    conferir_dicionario(con)
    conferir_nulos(con)
    conferir_tratamentos(con)
    conferir_chaves(con)


def falhar(*linhas: str) -> None:
    for linha in linhas:
        print(linha, file=sys.stderr)
    sys.exit(1)


def main(arquivo_banco: Path = ARQUIVO_BANCO) -> None:
    arquivo_banco = Path(arquivo_banco)

    if not arquivo_banco.is_file():
        falhar(
            f"Banco não encontrado: {arquivo_banco}",
            "Rode primeiro: uv run python ingestao.py",
        )

    try:
        con = duckdb.connect(str(arquivo_banco))
    except duckdb.Error as e:
        falhar(f"Não foi possível abrir {arquivo_banco} (outro processo com o arquivo aberto?):", str(e))

    try:
        faltando = tabelas_raw_faltando(con)
        if faltando:
            falhar(
                f"Tabelas ausentes em {arquivo_banco}: {', '.join(faltando)}",
                "Rode primeiro: uv run python ingestao.py",
            )

        con.begin()
        try:
            criar_refined(con)
            conferir(con)
            con.commit()
        except ErroRefined as e:
            con.rollback()
            falhar(str(e), "Nada foi gravado em refined (ROLLBACK).")
        except duckdb.Error as e:
            con.rollback()
            falhar(f"Erro do DuckDB: {e}", "Nada foi gravado em refined (ROLLBACK).")

        total = 0
        for origem, destino in TABELAS:
            n = contar(con, f"{DESTINO}.{destino}")
            m = contar(con, f"{ORIGEM}.{origem}")
            total += n
            print(f"{DESTINO}.{destino}: {formatar_milhar(n)} linhas (raw: {formatar_milhar(m)})")
        print(f"Total: {formatar_milhar(total)} registros")
    finally:
        con.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
