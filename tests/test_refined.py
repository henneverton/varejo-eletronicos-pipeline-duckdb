import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

import refined

COLUNAS_RAW = {
    "sales": [
        "Order Number", "Line Item", "Order Date", "Delivery Date", "CustomerKey",
        "StoreKey", "ProductKey", "Quantity", "Currency Code",
    ],
    "customers": [
        "CustomerKey", "Gender", "Name", "City", "State Code", "State", "Zip Code",
        "Country", "Continent", "Birthday",
    ],
    "products": [
        "ProductKey", "Product Name", "Brand", "Color", "Unit Cost USD",
        "Unit Price USD", "SubcategoryKey", "Subcategory", "CategoryKey", "Category",
    ],
    "stores": ["StoreKey", "Country", "State", "Square Meters", "Open Date"],
    "exchange_rates": ["Date", "Currency", "Exchange"],
    "data_dictionary": ["Table", "Field", "Description"],
}

LINHAS_RAW = {
    "sales": [
        ("1", "1", "1/5/2020", "1/9/2020", "1", "0", "1", "2", "USD"),
        ("2", "1", "12/31/2020", None, "2", "1", "2", "1", "USD"),
    ],
    "customers": [
        ("1", "Female", "Ashley Dane?", "BAMBER'S GREEN", "NA", "Napoli", "800", "Australia", "Oceania", "2/3/1990"),
        ("2", "Male", "Martin ?Novák", "BRIG O'TURK", "SC", "Perthshire", "2000", "Australia", "Oceania", "12/25/1980"),
        ("3", "Male", " Ana ", "BÉZIERS", "34", "Hérault", "123", "France", "Europe", "1/1/1975"),
        ("4", "Female", "Bia", "AIX-LES-BAINS", "TX", "Texas", "9999", "United States", "North America", "5/5/1985"),
        ("5", "Male", "Caio", "Sydney", "NSW", "New South Wales", "SW1A 1AA", "United Kingdom", "Europe", "6/6/1960"),
        ("6", "Female", "Dora", "toronto", "ON", "Ontario", "K1A 0B1", "Canada", "North America", "7/7/1970"),
    ],
    "products": [
        ("1", "Contoso MP3", "Contoso", "Silver", "$6.62 ", "$12.99 ", "0101", "MP4&MP3", "01", "Audio"),
        ("2", "Adventure TV", "Adventure Works", "Black", "$960.82 ", "$2,899.99 ", "0301", "TV", "03", "TV"),
    ],
    "stores": [
        ("0", "Online", "Online", None, "1/1/2010"),
        ("1", "United States", "CA", "500", "12/5/2015"),
    ],
    "exchange_rates": [
        ("1/1/2015", "USD", "1"),
        ("1/2/2015", "EUR", "0.8123"),
    ],
}

# Esperado nas tabelas pequenas: cep 800, 123, 9999; nome c1, c2 e c3 (o trim de
# ' Ana ' também conta como mudança); cidade c1 a c4.
ESPERADO_TESTE = (3, 3, 4)

TIPOS_ESPERADOS = {
    "vendas": [
        ("numero_pedido", "INTEGER"), ("item_pedido", "INTEGER"), ("data_pedido", "DATE"),
        ("data_entrega", "DATE"), ("chave_cliente", "INTEGER"), ("chave_loja", "INTEGER"),
        ("chave_produto", "INTEGER"), ("quantidade", "INTEGER"), ("codigo_moeda", "VARCHAR"),
    ],
    "clientes": [
        ("chave_cliente", "INTEGER"), ("genero", "VARCHAR"), ("nome", "VARCHAR"),
        ("cidade", "VARCHAR"), ("codigo_estado", "VARCHAR"), ("estado", "VARCHAR"),
        ("cep", "VARCHAR"), ("pais", "VARCHAR"), ("continente", "VARCHAR"),
        ("data_nascimento", "DATE"),
    ],
    "produtos": [
        ("chave_produto", "INTEGER"), ("nome_produto", "VARCHAR"), ("marca", "VARCHAR"),
        ("cor", "VARCHAR"), ("custo_unitario_usd", "DECIMAL(10,2)"),
        ("preco_unitario_usd", "DECIMAL(10,2)"), ("chave_subcategoria", "VARCHAR"),
        ("subcategoria", "VARCHAR"), ("chave_categoria", "VARCHAR"), ("categoria", "VARCHAR"),
    ],
    "lojas": [
        ("chave_loja", "INTEGER"), ("pais", "VARCHAR"), ("estado", "VARCHAR"),
        ("metros_quadrados", "INTEGER"), ("data_abertura", "DATE"),
    ],
    "taxas_cambio": [
        ("data", "DATE"), ("moeda", "VARCHAR"), ("taxa_cambio", "DECIMAL(10,4)"),
    ],
    "dicionario_dados": [
        ("tabela", "VARCHAR"), ("campo", "VARCHAR"), ("descricao", "VARCHAR"),
    ],
}


def linhas_dicionario():
    return [
        (tabela_raw, campo_raw, "original")
        for tabela_raw, (_, campos) in refined.CAMPOS.items()
        for campo_raw in campos
    ]


def montar_raw(arquivo, omitir=()):
    con = duckdb.connect(str(arquivo))
    try:
        con.execute("CREATE SCHEMA raw")
        for tabela, colunas in COLUNAS_RAW.items():
            if tabela in omitir:
                continue
            defs = ", ".join(f'"{c}" VARCHAR' for c in colunas)
            con.execute(f"CREATE TABLE raw.{tabela} ({defs})")
            linhas = linhas_dicionario() if tabela == "data_dictionary" else LINHAS_RAW[tabela]
            marcas = ", ".join("?" for _ in colunas)
            con.executemany(f"INSERT INTO raw.{tabela} VALUES ({marcas})", linhas)
    finally:
        con.close()


@pytest.fixture
def banco(tmp_path, monkeypatch):
    monkeypatch.setattr(refined, "ESPERADO_TRATAMENTOS", ESPERADO_TESTE)
    arquivo = tmp_path / "data" / "projeto.duckdb"
    arquivo.parent.mkdir()
    montar_raw(arquivo)
    return arquivo


def consulta(banco, sql):
    con = duckdb.connect(str(banco), read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def escrever(banco, sql):
    con = duckdb.connect(str(banco))
    try:
        con.execute(sql)
    finally:
        con.close()


def test_sucesso_contagens_e_saida(banco, capsys):
    refined.main(arquivo_banco=banco)
    saida = capsys.readouterr().out.splitlines()
    assert saida == [
        "refined.vendas: 2 linhas (raw: 2)",
        "refined.clientes: 6 linhas (raw: 6)",
        "refined.produtos: 2 linhas (raw: 2)",
        "refined.lojas: 2 linhas (raw: 2)",
        "refined.taxas_cambio: 2 linhas (raw: 2)",
        "refined.dicionario_dados: 37 linhas (raw: 37)",
        "Total: 51 registros",
    ]


def test_idempotencia(banco, capsys):
    refined.main(arquivo_banco=banco)
    primeira = capsys.readouterr().out
    refined.main(arquivo_banco=banco)
    assert capsys.readouterr().out == primeira


def test_tipos_por_tabela(banco):
    refined.main(arquivo_banco=banco)
    tabelas = consulta(
        banco, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'refined'"
    )
    assert {t[0] for t in tabelas} == set(TIPOS_ESPERADOS)
    for tabela, esperado in TIPOS_ESPERADOS.items():
        obtido = consulta(
            banco,
            "SELECT column_name, data_type FROM information_schema.columns "
            f"WHERE table_schema = 'refined' AND table_name = '{tabela}' ORDER BY ordinal_position",
        )
        assert obtido == esperado, tabela


def test_produtos_preco_milhar_e_zeros(banco):
    refined.main(arquivo_banco=banco)
    linhas = consulta(
        banco,
        "SELECT preco_unitario_usd::VARCHAR, custo_unitario_usd::VARCHAR, "
        "chave_subcategoria, chave_categoria FROM refined.produtos ORDER BY chave_produto",
    )
    assert linhas == [("12.99", "6.62", "0101", "01"), ("2899.99", "960.82", "0301", "03")]


def test_datas_e_nulos_legitimos(banco):
    refined.main(arquivo_banco=banco)
    vendas = consulta(
        banco,
        "SELECT data_pedido::VARCHAR, data_entrega::VARCHAR FROM refined.vendas ORDER BY numero_pedido",
    )
    assert vendas == [("2020-01-05", "2020-01-09"), ("2020-12-31", None)]
    assert consulta(banco, "SELECT metros_quadrados FROM refined.lojas ORDER BY chave_loja") == [
        (None,), (500,)
    ]
    assert consulta(banco, "SELECT count(*) FROM refined.clientes WHERE codigo_estado = 'NA'") == [(1,)]


def test_t1_cep(banco):
    refined.main(arquivo_banco=banco)
    ceps = dict(consulta(banco, "SELECT chave_cliente, cep FROM refined.clientes"))
    assert ceps == {
        1: "0800",       # Australia, 3 dígitos -> 4
        2: "2000",       # Australia já com 4: não muda
        3: "00123",      # France, 3 dígitos -> 5
        4: "09999",      # United States, 4 dígitos -> 5
        5: "SW1A 1AA",   # United Kingdom: intocado
        6: "K1A 0B1",    # Canada: intocado
    }


def test_t2_nome(banco):
    refined.main(arquivo_banco=banco)
    nomes = dict(consulta(banco, "SELECT chave_cliente, nome FROM refined.clientes"))
    assert nomes[1] == "Ashley Dane"
    assert nomes[2] == "Martin Novák"
    assert nomes[3] == "Ana"  # trim
    assert not any("?" in n for n in nomes.values())


def test_t3_cidade(banco):
    refined.main(arquivo_banco=banco)
    cidades = dict(consulta(banco, "SELECT chave_cliente, cidade FROM refined.clientes"))
    assert cidades == {
        1: "Bamber's Green",
        2: "Brig O'Turk",
        3: "Béziers",
        4: "Aix-Les-Bains",
        5: "Sydney",   # caixa mista: intocada
        6: "toronto",  # caixa mista: intocada
    }


def test_dicionario_consistente(banco):
    refined.main(arquivo_banco=banco)
    pares = consulta(banco, "SELECT tabela, campo, descricao FROM refined.dicionario_dados")
    assert len(pares) == 37
    assert ("vendas", "numero_pedido", "Identificador único de cada pedido") in pares
    assert ("taxas_cambio", "taxa_cambio", "Taxa de câmbio em relação ao USD") in pares
    assert {p[0] for p in pares} == {"vendas", "clientes", "produtos", "lojas", "taxas_cambio"}


def test_raw_inalterado(banco):
    refined.main(arquivo_banco=banco)
    for tabela, colunas in COLUNAS_RAW.items():
        obtido = consulta(
            banco,
            "SELECT column_name, data_type FROM information_schema.columns "
            f"WHERE table_schema = 'raw' AND table_name = '{tabela}' ORDER BY ordinal_position",
        )
        assert obtido == [(c, "VARCHAR") for c in colunas]
    assert consulta(banco, "SELECT \"Unit Price USD\" FROM raw.products WHERE ProductKey = '2'") == [
        ("$2,899.99 ",)
    ]


def test_falta_banco(tmp_path, capsys):
    banco = tmp_path / "data" / "projeto.duckdb"
    with pytest.raises(SystemExit) as e:
        refined.main(arquivo_banco=banco)
    assert e.value.code == 1
    err = capsys.readouterr().err
    assert str(banco) in err and "ingestao.py" in err
    assert not banco.exists() and not banco.parent.exists()


def test_falta_tabela_raw(tmp_path, capsys):
    banco = tmp_path / "projeto.duckdb"
    montar_raw(banco, omitir=("stores",))
    with pytest.raises(SystemExit) as e:
        refined.main(arquivo_banco=banco)
    assert e.value.code == 1
    assert "raw.stores" in capsys.readouterr().err
    assert consulta(banco, "SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'refined'") == [(0,)]


def test_valor_que_nao_converte_faz_rollback(banco, capsys):
    refined.main(arquivo_banco=banco)
    capsys.readouterr()
    escrever(banco, "UPDATE raw.sales SET \"Quantity\" = 'abc' WHERE \"Order Number\" = '1'")
    with pytest.raises(SystemExit) as e:
        refined.main(arquivo_banco=banco)
    assert e.value.code == 1
    assert "refined.vendas" in capsys.readouterr().err
    assert consulta(banco, "SELECT quantidade FROM refined.vendas ORDER BY numero_pedido") == [(2,), (1,)]


def test_virgula_fora_do_padrao_nao_vira_nulo(banco, capsys):
    escrever(banco, "UPDATE raw.products SET \"Unit Price USD\" = '$1.2.3 ' WHERE ProductKey = '1'")
    with pytest.raises(SystemExit):
        refined.main(arquivo_banco=banco)
    assert "refined.produtos" in capsys.readouterr().err


def test_divergencia_de_contagem_faz_rollback(banco, capsys, monkeypatch):
    refined.main(arquivo_banco=banco)
    capsys.readouterr()
    original = refined.contar

    def contar_errado(con, tabela):
        n = original(con, tabela)
        return n + 1 if tabela == "refined.vendas" else n

    monkeypatch.setattr(refined, "contar", contar_errado)
    escrever(banco, "UPDATE raw.products SET \"Brand\" = 'Mudou' WHERE ProductKey = '1'")
    with pytest.raises(SystemExit) as e:
        refined.main(arquivo_banco=banco)
    assert e.value.code == 1
    assert "refined.vendas" in capsys.readouterr().err
    # refined ficou como antes: a marca nova não chegou
    assert consulta(banco, "SELECT marca FROM refined.produtos WHERE chave_produto = 1") == [("Contoso",)]


def test_chave_repetida_falha(banco, capsys):
    escrever(banco, "UPDATE raw.sales SET \"Order Number\" = '1' WHERE \"Order Number\" = '2'")
    escrever(banco, "UPDATE raw.sales SET \"Line Item\" = '1'")
    with pytest.raises(SystemExit) as e:
        refined.main(arquivo_banco=banco)
    assert e.value.code == 1
    err = capsys.readouterr().err
    assert "refined.vendas" in err and "repetida" in err


def test_tratamentos_divergentes_falham(banco, capsys, monkeypatch):
    monkeypatch.setattr(refined, "ESPERADO_TRATAMENTOS", (836, 3, 3885))
    with pytest.raises(SystemExit) as e:
        refined.main(arquivo_banco=banco)
    assert e.value.code == 1
    assert "Tratamentos divergem" in capsys.readouterr().err


def test_caminho_padrao_aponta_para_a_raiz(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    raiz = Path(refined.__file__).resolve().parent
    assert refined.ARQUIVO_BANCO == raiz / "data" / "projeto.duckdb"


def test_importar_nao_tem_efeito_colateral(tmp_path):
    raiz = Path(refined.__file__).resolve().parent
    r = subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(raiz)!r}); import refined"],
        check=False, cwd=tmp_path, capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert r.stdout == "" and r.stderr == ""
    assert list(tmp_path.iterdir()) == []
