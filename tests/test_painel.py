from pathlib import Path

import duckdb
import pandas as pd
import pytest

import painel

RAIZ = Path(__file__).resolve().parent.parent
PASTA_SQL = RAIZ / "sql" / "marts"


# --- Formatação ------------------------------------------------------------
def test_usd_milhar_com_ponto_e_decimal_com_virgula():
    assert painel.usd(1003862.14) == "US$ 1.003.862,14"
    assert painel.usd(0.5) == "US$ 0,50"
    assert painel.usd(1234.5, casas=0) == "US$ 1.234" or painel.usd(1234.5, casas=0) == "US$ 1.235"


def test_usd_curto_mi_e_mil():
    assert painel.usd_curto(55_755_479.59) == "US$ 55,76 mi"
    assert painel.usd_curto(612_000) == "US$ 612 mil"
    assert painel.usd_curto(950) == "US$ 950"


def test_usd_eixo_sem_casas_quando_redondo():
    assert painel.usd_eixo(5_000_000) == "US$ 5 mi"
    assert painel.usd_eixo(2_500_000) == "US$ 2,5 mi"
    assert painel.usd_eixo(500_000) == "US$ 500 mil"
    assert painel.usd_eixo(0) == "US$ 0"


def test_pct_e_numero():
    assert painel.pct(93.2) == "93,2%"
    assert painel.pct(0.63, casas=2) == "0,63%"
    assert painel.numero(197757) == "197.757"
    assert painel.numero(1234.567, casas=2) == "1.234,57"


def test_pct_sinal():
    assert painel.pct_sinal(42.8) == "+42,8%"
    assert painel.pct_sinal(-49.1) == "−49,1%"


def test_ausencia_vira_nd_e_nao_zero():
    for f in (painel.usd, painel.usd_curto, painel.pct, painel.pct_sinal, painel.numero):
        assert f(None) == "n/d"
        assert f(float("nan")) == "n/d"


def test_formatacao_nao_depende_de_locale():
    import locale

    antigo = locale.setlocale(locale.LC_ALL)
    try:
        for nome in ("pt_BR.UTF-8", "de_DE.UTF-8", "C"):
            try:
                locale.setlocale(locale.LC_ALL, nome)
            except locale.Error:
                continue
            assert painel.numero(1234567.5, 1) == "1.234.567,5"
    finally:
        locale.setlocale(locale.LC_ALL, antigo)


# --- Leitura ---------------------------------------------------------------
def criar_banco(tmp_path):
    arquivo = tmp_path / "t.duckdb"
    con = duckdb.connect(str(arquivo))
    con.execute("CREATE SCHEMA marts")
    con.execute("CREATE TABLE marts.a AS SELECT 1 AS x")
    con.execute("CREATE TABLE marts.b AS SELECT 2 AS y")
    con.close()
    return arquivo


def test_ler_devolve_so_as_tabelas_pedidas(tmp_path):
    arquivo = criar_banco(tmp_path)
    dados = painel.ler(["a"], arquivo)
    assert list(dados) == ["a"]
    assert dados["a"]["x"].tolist() == [1]


def test_ler_fecha_a_conexao(tmp_path):
    arquivo = criar_banco(tmp_path)
    painel.ler(["a", "b"], arquivo)
    # Se a conexão somente leitura ainda estivesse aberta, abrir para escrita falharia.
    con = duckdb.connect(str(arquivo))
    con.execute("CREATE TABLE marts.c AS SELECT 3 AS z")
    con.close()


def test_tabelas_faltando_lista_o_que_falta(tmp_path):
    arquivo = criar_banco(tmp_path)
    assert painel.tabelas_faltando(["a", "b", "c", "d"], arquivo) == ["c", "d"]


def test_sem_banco_tudo_falta_e_nada_e_criado(tmp_path):
    arquivo = tmp_path / "nao_existe.duckdb"
    assert painel.tabelas_faltando(["a", "b"], arquivo) == ["a", "b"]
    assert not arquivo.exists()


def test_ler_sem_sql_alem_de_select_estrela():
    fonte = (RAIZ / "painel.py").read_text(encoding="utf-8")
    # duas consultas no total: a lista de tabelas (information_schema) e o SELECT * de ler()
    assert fonte.count(".execute(") == 2
    assert 'con.execute(f"SELECT * FROM marts.{nome}")' in fonte


def test_proibicoes_de_calculo_nos_arquivos_do_painel():
    for nome in ("painel.py", "app.py"):
        texto = (RAIZ / nome).read_text(encoding="utf-8")
        for proibido in ("groupby", ".sum(", ".mean(", ".median(", "merge", "pivot", "polyfit"):
            assert proibido not in texto, f"{proibido} em {nome}"


# --- Gráficos --------------------------------------------------------------
def df_anual():
    return pd.DataFrame(
        {
            "ano": [2016, 2017, 2018],
            "meses_com_venda": [12, 12, 2],
            "pedidos": [10, 20, 5],
            "receita_usd": [1_000_000.0, 3_000_000.0, 500_000.0],
            "variacao_pct": [None, 200.0, None],
            "melhor_ano": [False, True, False],
        }
    )


def test_grafico_01_destaca_melhor_ano_e_marca_parcial_e_nd():
    fig = painel.grafico_01(df_anual())
    barra = fig.data[0]
    assert list(barra.x) == ["2016", "2017", "2018 (parcial)"]
    assert list(barra.marker.color) == [painel.ROXO_ESCURO, painel.PRINCIPAL, painel.ROXO_ESCURO]
    assert "n/d" in barra.text[0] and "+200,0%" in barra.text[1]
    # anos em texto não podem virar eixo numérico (o "2021 (parcial)" sumiria)
    assert fig.layout.xaxis.type == "category"


def test_grafico_02_uma_serie_por_ano_com_2021_tracejada_e_marca_extremos():
    df = pd.DataFrame(
        {
            "ano": [2020, 2020, 2021, 2021],
            "mes": [1, 2, 1, 2],
            "receita_usd": [100.0, 400.0, 50.0, 200.0],
            "pedidos": [1, 2, 1, 2],
        }
    )
    fig = painel.grafico_02(df)
    linhas = [t for t in fig.data if t.mode == "lines+markers"]
    assert [t.name for t in linhas] == ["2020", "2021"]
    assert linhas[1].line.dash == "dash" and linhas[0].line.dash == "solid"
    textos = [t.text[0] for t in fig.data if t.mode == "markers+text"]
    assert any("máx" in x and "Fev/2020" in x for x in textos)
    assert any("mín" in x and "Jan/2021" in x for x in textos)


def df_categorias():
    return pd.DataFrame(
        {
            "categoria": ["A", "B", "C"],
            "receita_usd": [10.0, 30.0, 20.0],
            "participacao_pct": [16.7, 50.0, 33.3],
            "itens": [1, 3, 2],
        }
    )


def test_grafico_03_ordenado_do_maior_para_o_menor():
    fig = painel.grafico_03(df_categorias())
    assert list(fig.data[0].y) == ["B", "C", "A"]
    assert fig.layout.yaxis.autorange == "reversed"


def test_grafico_04_ordenado_da_maior_para_a_menor_margem_e_destaca_extremos():
    margem = pd.DataFrame(
        {
            "categoria": ["A", "B", "C"],
            "receita_usd": [10.0, 30.0, 20.0],
            "lucro_usd": [5.0, 15.0, 12.0],
            "margem_pct": [50.0, 60.0, 55.0],
        }
    )
    fig = painel.grafico_04(margem)
    assert list(fig.data[0].y) == ["B", "C", "A"]  # 60,0 > 55,0 > 50,0
    assert list(fig.data[0].marker.color) == [painel.PRINCIPAL, painel.NEUTRO, painel.CIANO]
    assert fig.layout.yaxis.autorange == "reversed"  # maior em cima


def test_grafico_05_tem_duas_linhas_de_referencia():
    df = pd.DataFrame(
        {
            "subcategoria": ["s1", "s2"],
            "categoria": ["c", "c"],
            "receita_usd": [100.0, 300.0],
            "margem_pct": [55.0, 60.0],
            "itens": [10, 30],
        }
    )
    ref = pd.DataFrame({"mediana_receita_usd": [200.0], "margem_global_pct": [58.0]})
    fig = painel.grafico_05(df, ref)
    assert len(fig.layout.shapes) == 2
    assert sorted(s.x0 for s in fig.layout.shapes if s.x0 is not None and s.x0 == s.x1) == [200.0]


def test_grafico_06_ordem_decrescente():
    df = pd.DataFrame(
        {"marca": ["x", "y"], "receita_usd": [5.0, 9.0], "participacao_pct": [35.0, 65.0], "itens": [1, 2]}
    )
    assert list(painel.grafico_06(df).data[0].x) == ["y", "x"]


def df_canais():
    return pd.DataFrame(
        {
            "ano": ["Total", "Total", "2016", "2016", "2017", "2017"],
            "canal": ["Loja física", "Online"] * 3,
            "receita_usd": [80.0, 20.0, 40.0, 10.0, 40.0, 10.0],
            "participacao_pct": [80.0, 20.0, 80.0, 20.0, 80.0, 20.0],
        }
    )


def test_grafico_08_separa_total_dos_anos():
    total = painel.grafico_08_total(painel_df := df_canais())
    assert sorted(total.data[0].values) == [20.0, 80.0]
    evolucao = painel.grafico_08_evolucao(painel_df)
    assert evolucao.layout.barnorm == "percent"
    assert evolucao.layout.xaxis.type == "category"
    for barra in evolucao.data:
        assert list(barra.x) == ["2016", "2017"]


def test_grafico_07_e_tabela_07_ordenados_por_receita():
    df = pd.DataFrame(
        {
            "pais": ["Germany", "United States"],
            "continente": ["Europe", "North America"],
            "receita_usd": [5_000_000.0, 29_000_000.0],
            "participacao_pct": [9.7, 53.6],
            "clientes": [1150, 5706],
            "pedidos": [2440, 14221],
        }
    )
    tabela = painel.tabela_07(df)
    assert tabela["País"].tolist() == ["United States", "Germany"]
    assert tabela["Receita"].tolist() == ["US$ 29,00 mi", "US$ 5,00 mi"]
    assert tabela["Clientes"].tolist() == ["5.706", "1.150"]
    assert painel.grafico_07(df).data[0].locationmode == "country names"


def df_lojas(n=15):
    return pd.DataFrame(
        {
            "chave_loja": list(range(1, n + 1)),
            "pais": ["P"] * n,
            "estado": [f"E{i}" for i in range(1, n + 1)],
            "metros_quadrados": [100 * i for i in range(1, n + 1)],
            "data_abertura": [None] * n,
            "receita_usd": [1000.0 * i for i in range(1, n + 1)],
            "receita_por_m2": [float(i) for i in range(1, n + 1)],
            "ranking_top": list(range(n, 0, -1)),
            "ranking_bottom": list(range(1, n + 1)),
        }
    )


def test_lista_lojas_top_e_bottom_10():
    df = df_lojas()
    top, bottom = painel.lista_lojas(df, "top"), painel.lista_lojas(df, "bottom")
    assert len(top) == len(bottom) == 10
    assert top["#"].tolist() == list(range(1, 11))
    assert top["Loja"].iloc[0] == "P · E15"      # a de maior receita por m²
    assert bottom["Loja"].iloc[0] == "P · E1"    # a de menor


def test_grafico_09_reta_usa_inclinacao_e_intercepto_do_mart():
    tend = pd.DataFrame({"lojas": [15], "inclinacao": [10.0], "intercepto": [5.0], "r2": [0.3627]})
    fig = painel.grafico_09(df_lojas(), tend)
    reta = fig.data[1]
    assert list(reta.x) == [100, 1500]
    assert list(reta.y) == [1005.0, 15005.0]
    assert "0,36" in reta.name


def df_perfil():
    return pd.DataFrame(
        {
            "faixa_etaria": ["18–24", "18–24", "75+", "75+"],
            "genero": ["Female", "Male", "Female", "Male"],
            "clientes": [10, 20, 30, 40],
            "receita_usd": [100.0, 200.0, 300.0, 400.0],
            "pedidos": [5, 6, 7, 8],
            "ticket_medio_usd": [20.0, 33.33, 42.86, 50.0],
        }
    )


def test_grafico_10_masculino_a_esquerda_e_eixo_em_valor_absoluto():
    fig = painel.grafico_10(df_perfil(), "Clientes distintos")
    masculino, feminino = fig.data
    assert masculino.name == "Masculino" and feminino.name == "Feminino"
    assert list(masculino.x) == [-20, -40]
    assert list(feminino.x) == [10, 30]
    assert list(fig.data[0].y) == ["18–24", "75+"]  # mais jovem primeiro (embaixo)
    assert all(not t.startswith("−") and not t.startswith("-") for t in fig.layout.xaxis.ticktext)


def test_grafico_10_troca_de_metrica_altera_as_barras():
    cli = painel.grafico_10(df_perfil(), "Clientes distintos").data[1].x
    rec = painel.grafico_10(df_perfil(), "Receita").data[1].x
    tic = painel.grafico_10(df_perfil(), "Ticket médio").data[1].x
    assert list(cli) != list(rec) != list(tic)
    assert list(tic) == [20.0, 42.86]


# --- Marts novos (11, 12, 13), em banco temporário com refined mínimo -------
def banco_refined_minimo(tmp_path):
    con = duckdb.connect(str(tmp_path / "t.duckdb"))
    con.execute("CREATE SCHEMA refined")
    con.execute(
        """CREATE TABLE refined.produtos AS SELECT * FROM (VALUES
            (1, 'X', 100.00, 90.00),
            (2, 'Y',  10.00,  1.00)
        ) t(chave_produto, subcategoria, preco_unitario_usd, custo_unitario_usd)"""
    )
    # pedido 1 (cliente 1): 1×A + 10×B ; pedido 2 (cliente 2): 1×A ; loja 0 = online
    con.execute(
        """CREATE TABLE refined.vendas AS SELECT * FROM (VALUES
            (1, 1, 1, 0, 1, 1),
            (1, 2, 1, 0, 2, 10),
            (2, 1, 2, 0, 1, 1)
        ) t(numero_pedido, item_pedido, chave_cliente, chave_loja, chave_produto, quantidade)"""
    )
    con.execute("CREATE TABLE refined.lojas AS SELECT 0 AS chave_loja, NULL::INTEGER AS metros_quadrados")
    return con


def rodar(con, nome):
    sql = (PASTA_SQL / nome).read_text(encoding="utf-8").strip().rstrip(";")
    return con.execute(sql).fetchall()


def test_kpis_margem_ponderada_difere_da_media_simples(tmp_path):
    con = banco_refined_minimo(tmp_path)
    receita, lucro, margem, itens, clientes, pedidos = rodar(con, "11_kpis.sql")[0]
    assert (float(receita), float(lucro)) == (300.0, 110.0)
    assert margem == 36.7  # ponderada; a média simples de 10% e 90% daria 50%
    assert (itens, clientes, pedidos) == (12, 2, 2)


def test_referencia_subcategorias_mediana_e_margem_global(tmp_path):
    con = banco_refined_minimo(tmp_path)
    mediana, margem_global = rodar(con, "12_referencia_subcategorias.sql")[0]
    assert float(mediana) == 150.0  # X = 200, Y = 100
    assert margem_global == 36.7


def test_tendencia_lojas_regressao_em_pontos_conhecidos(tmp_path):
    con = duckdb.connect(str(tmp_path / "r.duckdb"))
    con.execute("CREATE SCHEMA refined")
    con.execute(
        "CREATE TABLE refined.produtos AS SELECT 1 AS chave_produto, 1.00 AS preco_unitario_usd"
    )
    con.execute(
        """CREATE TABLE refined.lojas AS SELECT * FROM (VALUES
            (0, NULL::INTEGER), (1, 100), (2, 200), (3, 300), (4, 400)
        ) t(chave_loja, metros_quadrados)"""
    )
    # receita = 10 × m²; loja 4 não tem venda e a loja 0 (online) não entra
    con.execute(
        """CREATE TABLE refined.vendas AS SELECT * FROM (VALUES
            (1, 1, 1, 1000), (2, 1, 1, 1500), (2, 1, 1, 500),
            (3, 1, 1, 3000), (0, 1, 1, 777)
        ) t(chave_loja, chave_produto, item_pedido, quantidade)"""
    )
    lojas, inclinacao, intercepto, r2 = rodar(con, "13_tendencia_lojas.sql")[0]
    assert lojas == 3
    assert inclinacao == pytest.approx(10.0)
    assert intercepto == pytest.approx(0.0, abs=1e-6)
    assert r2 == pytest.approx(1.0)


def test_marts_novos_leem_so_refined():
    for nome in ("11_kpis.sql", "12_referencia_subcategorias.sql", "13_tendencia_lojas.sql"):
        texto = (PASTA_SQL / nome).read_text(encoding="utf-8")
        assert "marts." not in texto.replace("sql/marts", "")
        assert "refined." in texto


def test_marcas_do_eixo_logaritmico_nao_se_amontoam():
    marcas = painel._marcas_log(120_000, 9_900_000)
    assert marcas == [100_000, 300_000, 1_000_000, 3_000_000, 10_000_000]


def test_grafico_05_eixo_logaritmico_e_grafico_04_sem_zero():
    df = pd.DataFrame(
        {
            "subcategoria": ["s1", "s2"], "categoria": ["c", "c"],
            "receita_usd": [120_000.0, 9_900_000.0], "margem_pct": [55.0, 60.0], "itens": [10, 30],
        }
    )
    ref = pd.DataFrame({"mediana_receita_usd": [1_000_000.0], "margem_global_pct": [58.0]})
    assert painel.grafico_05(df, ref).layout.xaxis.type == "log"
    margem = pd.DataFrame(
        {"categoria": ["A", "B"], "receita_usd": [1.0, 2.0], "lucro_usd": [0.5, 1.2], "margem_pct": [54.7, 61.0]}
    )
    base = painel.grafico_04(margem).layout.xaxis.range[0]
    assert 0 < base < 54.7  # eixo começa abaixo do menor valor, mas não em zero
