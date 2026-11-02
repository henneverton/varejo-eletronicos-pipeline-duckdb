import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

import marts

RAIZ = Path(__file__).resolve().parent.parent

TABELAS_REFINED = [
    "vendas", "clientes", "produtos", "lojas", "taxas_cambio", "dicionario_dados",
]

SQL_A = "-- Gráfico A; com ponto e vírgula no comentário\nselect chave, 'Câmbio – ok' as txt from refined.vendas;\n"
SQL_B = "select count(*) as n from refined.vendas"


def criar_banco(tmp_path, ausentes=()):
    arquivo = tmp_path / "data" / "projeto.duckdb"
    arquivo.parent.mkdir()
    con = duckdb.connect(str(arquivo))
    con.execute("CREATE SCHEMA raw")
    con.execute("CREATE TABLE raw.sales AS SELECT '1' AS x")
    con.execute("CREATE SCHEMA refined")
    for t in TABELAS_REFINED:
        if t in ausentes:
            continue
        con.execute(f"CREATE TABLE refined.{t} AS SELECT * FROM range(1, 4) t(chave)")
    con.close()
    return arquivo


def criar_pasta(tmp_path, arquivos):
    pasta = tmp_path / "sql" / "marts"
    pasta.mkdir(parents=True)
    for nome, texto in arquivos.items():
        (pasta / nome).write_text(texto, encoding="utf-8")
    return pasta


def consultar(arquivo, sql):
    con = duckdb.connect(str(arquivo), read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def tabelas_marts(arquivo):
    return sorted(
        r[0]
        for r in consultar(
            arquivo,
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'marts'",
        )
    )


def rodar(arquivo, pasta):
    marts.main(arquivo_banco=arquivo, pasta_sql=pasta)


def sair_com_erro(arquivo, pasta, capsys):
    with pytest.raises(SystemExit) as e:
        rodar(arquivo, pasta)
    assert e.value.code == 1
    return capsys.readouterr().err


def test_sucesso(tmp_path, capsys):
    banco = criar_banco(tmp_path)
    pasta = criar_pasta(tmp_path, {"01_a.sql": SQL_A, "02_b.sql": SQL_B})
    rodar(banco, pasta)
    saida = capsys.readouterr().out.splitlines()
    assert saida[0].startswith("✓ marts.a") and saida[0].endswith("3 linhas")
    assert saida[1].startswith("✓ marts.b") and saida[1].endswith("1 linhas")
    assert saida[2] == "2 marts, 4 linhas"
    assert tabelas_marts(banco) == ["a", "b"]


def test_milhar_com_ponto(tmp_path, capsys):
    banco = criar_banco(tmp_path)
    pasta = criar_pasta(tmp_path, {"01_a.sql": "select * from range(1500) t(x)"})
    rodar(banco, pasta)
    assert "1.500 linhas" in capsys.readouterr().out


def test_ordem_alfabetica(tmp_path, capsys):
    banco = criar_banco(tmp_path)
    pasta = criar_pasta(tmp_path, {"02_b.sql": SQL_B, "01_a.sql": SQL_A})
    rodar(banco, pasta)
    saida = capsys.readouterr().out.splitlines()
    assert "marts.a" in saida[0] and "marts.b" in saida[1]


def test_ponto_e_virgula_em_comentario_e_utf8(tmp_path):
    banco = criar_banco(tmp_path)
    pasta = criar_pasta(tmp_path, {"01_a.sql": SQL_A})
    rodar(banco, pasta)
    assert consultar(banco, "SELECT DISTINCT txt FROM marts.a") == [("Câmbio – ok",)]


def test_idempotencia(tmp_path, capsys):
    banco = criar_banco(tmp_path)
    pasta = criar_pasta(tmp_path, {"01_a.sql": SQL_A, "02_b.sql": SQL_B})
    rodar(banco, pasta)
    primeira = capsys.readouterr().out
    rodar(banco, pasta)
    assert capsys.readouterr().out == primeira


def test_arquivo_apagado_remove_a_tabela(tmp_path):
    banco = criar_banco(tmp_path)
    pasta = criar_pasta(tmp_path, {"00_teste.sql": "SELECT 1 AS x", "01_a.sql": SQL_A})
    rodar(banco, pasta)
    assert consultar(banco, "SELECT count(*) FROM marts.teste") == [(1,)]
    (pasta / "00_teste.sql").unlink()
    rodar(banco, pasta)
    assert tabelas_marts(banco) == ["a"]


def test_falta_banco_nao_cria_arquivo(tmp_path, capsys):
    pasta = criar_pasta(tmp_path, {"01_a.sql": SQL_A})
    banco = tmp_path / "data" / "projeto.duckdb"
    err = sair_com_erro(banco, pasta, capsys)
    assert "Banco não encontrado" in err
    assert not banco.exists() and not banco.parent.exists()


def test_falta_tabela_em_refined(tmp_path, capsys):
    banco = criar_banco(tmp_path, ausentes=("lojas", "taxas_cambio"))
    pasta = criar_pasta(tmp_path, {"01_a.sql": SQL_A})
    err = sair_com_erro(banco, pasta, capsys)
    assert "refined.lojas" in err and "refined.taxas_cambio" in err
    assert "refined.py" in err
    assert tabelas_marts(banco) == []
    assert consultar(banco, "SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'marts'") == [(0,)]


def test_pasta_vazia_ou_inexistente(tmp_path, capsys):
    banco = criar_banco(tmp_path)
    vazia = tmp_path / "vazia"
    vazia.mkdir()
    assert "Nenhum arquivo .sql" in sair_com_erro(banco, vazia, capsys)
    assert "Nenhum arquivo .sql" in sair_com_erro(banco, tmp_path / "nao_existe", capsys)


def test_nome_fora_do_padrao_para_antes_de_executar(tmp_path, capsys):
    banco = criar_banco(tmp_path)
    pasta = criar_pasta(tmp_path, {"01_a.sql": SQL_A, "teste.sql": "SELECT 1"})
    err = sair_com_erro(banco, pasta, capsys)
    assert "teste.sql" in err
    assert tabelas_marts(banco) == []


def test_nome_duplicado_para_antes_de_executar(tmp_path, capsys):
    banco = criar_banco(tmp_path)
    pasta = criar_pasta(tmp_path, {"01_x.sql": SQL_A, "02_x.sql": SQL_B})
    err = sair_com_erro(banco, pasta, capsys)
    assert "marts.x" in err and "01_x.sql" in err and "02_x.sql" in err
    assert tabelas_marts(banco) == []


def test_sql_invalido_desfaz_tudo_e_mantem_o_anterior(tmp_path, capsys):
    banco = criar_banco(tmp_path)
    pasta = criar_pasta(tmp_path, {"01_a.sql": SQL_A, "02_b.sql": SQL_B})
    rodar(banco, pasta)
    capsys.readouterr()

    (pasta / "01_a.sql").write_text("select 99 as novo from refined.vendas", encoding="utf-8")
    (pasta / "02_b.sql").write_text("select de_propósito from tabela_que_nao_existe", encoding="utf-8")
    (pasta / "03_c.sql").write_text(SQL_B, encoding="utf-8")
    err = sair_com_erro(banco, pasta, capsys)
    assert "02_b.sql" in err and "ROLLBACK" in err
    # marts como antes: 01_a antigo (coluna chave), 03_c não executado
    assert tabelas_marts(banco) == ["a", "b"]
    assert [c[0] for c in consultar(banco, "DESCRIBE marts.a")] == ["chave", "txt"]


def test_sql_invalido_na_primeira_execucao_nao_deixa_schema(tmp_path, capsys):
    banco = criar_banco(tmp_path)
    pasta = criar_pasta(tmp_path, {"01_a.sql": SQL_A, "02_b.sql": "selecione tudo"})
    sair_com_erro(banco, pasta, capsys)
    assert consultar(banco, "SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'marts'") == [(0,)]


def test_mart_vazio_e_erro(tmp_path, capsys):
    banco = criar_banco(tmp_path)
    pasta = criar_pasta(tmp_path, {"01_a.sql": SQL_A})
    rodar(banco, pasta)
    capsys.readouterr()
    (pasta / "02_vazio.sql").write_text("select * from refined.vendas where 1 = 0", encoding="utf-8")
    err = sair_com_erro(banco, pasta, capsys)
    assert "marts.vazio" in err and "zero linhas" in err
    assert tabelas_marts(banco) == ["a"]


def test_raw_e_refined_inalterados(tmp_path):
    banco = criar_banco(tmp_path)
    antes = consultar(
        banco,
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_schema IN ('raw', 'refined') ORDER BY 1, 2",
    )
    pasta = criar_pasta(tmp_path, {"01_a.sql": SQL_A})
    rodar(banco, pasta)
    depois = consultar(
        banco,
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_schema IN ('raw', 'refined') ORDER BY 1, 2",
    )
    assert antes == depois
    assert consultar(banco, "SELECT count(*) FROM refined.vendas") == [(3,)]
    assert consultar(banco, "SELECT x FROM raw.sales") == [("1",)]


def test_importar_nao_tem_efeito_colateral(tmp_path):
    r = subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(RAIZ)!r}); import marts"],
        check=False,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert r.stdout == "" and r.stderr == ""
    assert list(tmp_path.iterdir()) == []
