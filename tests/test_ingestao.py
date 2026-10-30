import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

import ingestao

CABECALHOS = {
    "Sales.csv": "Order Number,Line Item,Delivery Date",
    "Customers.csv": "CustomerKey,Name,Zip Code",
    "Products.csv": "ProductKey,Unit Price USD,SubcategoryKey",
    "Stores.csv": "StoreKey,Country",
    "Exchange_Rates.csv": "Date,Currency,Exchange",
    "Data_Dictionary.csv": "Table,Field,Description",
}

LINHAS = {
    "Sales.csv": ["1,1,", "2,1,1/2/2016", "3,1,NA"],
    "Customers.csv": ["1,José,01234", "2,\"Silva, João\",5523"],
    "Products.csv": ["1,$6.62 ,0101"],
    "Stores.csv": ["1,Brasil"],
    "Exchange_Rates.csv": ["1/1/2015,USD,1"],
    "Data_Dictionary.csv": ["Sales,Order Number,\"linha\nquebrada\""],
}


@pytest.fixture
def raw(tmp_path):
    pasta = tmp_path / "RAW"
    pasta.mkdir()
    for arquivo, _, encoding in ingestao.TABELAS:
        texto = "\n".join([CABECALHOS[arquivo], *LINHAS[arquivo]]) + "\n"
        (pasta / arquivo).write_bytes(texto.encode(encoding))
    return pasta


def rodar(raw, tmp_path):
    banco = tmp_path / "data" / "projeto.duckdb"
    ingestao.main(pasta_raw=raw, arquivo_banco=banco)
    return banco


def consulta(banco, sql):
    con = duckdb.connect(str(banco), read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_contagens_colunas_e_tipos(raw, tmp_path, capsys):
    banco = rodar(raw, tmp_path)
    esperado = {"sales": 3, "customers": 2, "products": 1, "stores": 1, "exchange_rates": 1, "data_dictionary": 1}
    for tabela, n in esperado.items():
        assert consulta(banco, f"SELECT count(*) FROM raw.{tabela}") == [(n,)]
    assert len(consulta(banco, "SELECT table_name FROM information_schema.tables WHERE table_schema='raw'")) == 6

    for arquivo, tabela, _ in ingestao.TABELAS:
        colunas = consulta(
            banco,
            "SELECT column_name, data_type FROM information_schema.columns "
            f"WHERE table_schema='raw' AND table_name='{tabela}' ORDER BY ordinal_position",
        )
        assert [c for c, _ in colunas] == CABECALHOS[arquivo].split(",")
        assert {t for _, t in colunas} == {"VARCHAR"}

    saida = capsys.readouterr().out.splitlines()
    assert saida[0] == "raw.sales: 3 linhas"
    assert saida[-1] == "Total: 9 registros"
    assert len(saida) == 7


def test_nulos_zeros_e_textos(raw, tmp_path):
    banco = rodar(raw, tmp_path)
    delivery = consulta(banco, 'SELECT "Delivery Date" FROM raw.sales ORDER BY "Order Number"')
    assert delivery == [(None,), ("1/2/2016",), ("NA",)]
    assert consulta(banco, "SELECT \"Unit Price USD\", SubcategoryKey FROM raw.products") == [("$6.62 ", "0101")]
    assert consulta(banco, 'SELECT "Zip Code" FROM raw.customers ORDER BY CustomerKey')[0] == ("01234",)


def test_encoding_e_aspas(raw, tmp_path):
    banco = rodar(raw, tmp_path)
    nomes = [n for (n,) in consulta(banco, "SELECT Name FROM raw.customers ORDER BY CustomerKey")]
    assert nomes == ["José", "Silva, João"]
    assert consulta(banco, "SELECT Description FROM raw.data_dictionary") == [("linha\nquebrada",)]


def test_reexecucao_nao_acumula(raw, tmp_path, capsys):
    rodar(raw, tmp_path)
    primeira = capsys.readouterr().out
    rodar(raw, tmp_path)
    assert capsys.readouterr().out == primeira


def test_arquivo_ausente_para_sem_criar_nada(raw, tmp_path, capsys):
    (raw / "Stores.csv").unlink()
    banco = tmp_path / "data" / "projeto.duckdb"
    with pytest.raises(SystemExit) as erro:
        ingestao.main(pasta_raw=raw, arquivo_banco=banco)
    assert erro.value.code == 1
    err = capsys.readouterr().err
    assert "Stores.csv" in err and str(raw) in err
    assert not banco.parent.exists()


def test_caminhos_nao_dependem_do_diretorio_corrente(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    raiz = Path(ingestao.__file__).resolve().parent
    assert ingestao.PASTA_RAW == raiz / "RAW"
    assert ingestao.ARQUIVO_BANCO == raiz / "data" / "projeto.duckdb"


def test_importar_nao_toca_o_disco(tmp_path):
    raiz = Path(ingestao.__file__).resolve().parent
    codigo = f"import sys; sys.path.insert(0, r'{raiz}'); import ingestao"
    r = subprocess.run(
        [sys.executable, "-c", codigo], check=False, cwd=tmp_path, capture_output=True, text=True
    )
    assert r.returncode == 0
    assert r.stdout == ""
    assert list(tmp_path.iterdir()) == []
