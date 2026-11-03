"""Leitura, formatação e gráficos do dashboard (spec 004). Não importa streamlit.

Quem usa: app.py (a página). Teste: tests/test_painel.py.

Regras e por que existem
------------------------
1. Leitura: ler(nomes) devolve {nome: DataFrame}, cada um só com
   SELECT * FROM marts.<nome>; nenhuma outra SQL. A conexão é somente leitura e
   é aberta e fechada dentro de ler(); o caminho do banco sai de Path(__file__).
   Motivo: conexão aberta segura o arquivo, e marts.py não consegue gravar com o
   painel de pé; caminho relativo ao arquivo funciona de qualquer pasta.
2. Nenhum cálculo de negócio: nada de agregar, juntar tabelas ou fazer contas
   entre colunas. Permitido: ordenar, filtrar linhas, head(n), renomear coluna,
   formatar texto. Motivo: número novo na tela exige um .sql novo em
   sql/marts/; se faltar um número, o que falta é um mart, não código aqui.
   Exceções de DESENHO (não de negócio), todas pedidas na spec: o sinal da série
   masculina da pirâmide é invertido para ela crescer à esquerda; os pontos
   extremos da reta de tendência usam inclinação e intercepto lidos do mart 13;
   as marcas dos eixos em US$ são escolhidas a partir do maior valor.
3. Formatação: usd, usd_curto, pct e numero são funções puras. Milhar com ponto,
   decimal com vírgula, sempre, sem usar locale. Motivo: o resultado não pode
   depender da máquina de quem roda. Valor completo nos tooltips; abreviado
   (mi/mil) só em KPIs, eixos e rótulos curtos.
4. Uma função por gráfico, recebendo o DataFrame do mart e devolvendo a figura
   Plotly. Motivo: as figuras podem ser testadas sem Streamlit.
5. Identidade visual (D1): paleta literal abaixo, fundo transparente, grade
   leve, sem emojis. Ausência de dado (nulo) aparece como "n/d", nunca como 0.
"""

import math
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

RAIZ = Path(__file__).resolve().parent
ARQUIVO_BANCO = RAIZ / "data" / "projeto.duckdb"

MARTS = [
    "receita_anual",
    "receita_mensal_sazonalidade",
    "receita_por_categoria",
    "margem_por_categoria",
    "receita_x_margem_subcategoria",
    "top5_marcas",
    "receita_por_pais",
    "online_x_lojas_fisicas",
    "desempenho_das_lojas",
    "perfil_de_clientes",
    "kpis",
    "referencia_subcategorias",
    "tendencia_lojas",
]

# --- Paleta (D1) -----------------------------------------------------------
FUNDO = "#101629"
CARTAO = "#171F38"
PRINCIPAL = "#9149F5"
LILAS = "#C4A1FF"
AZUL = "#4F8CFF"
CIANO = "#22D3EE"
TEXTO = "#E6E9F5"
TEXTO_SEC = "#8B93B0"
TEXTO_EIXO = "#AEB6D2"  # eixos e legendas: um tom mais claro que o texto secundário
ROXO_ESCURO = "#4B2A87"
NEUTRO = "#4A5578"
GRADE = "rgba(139,147,176,0.15)"
CORES_ANO = {
    2016: "#5B6B9A",
    2017: AZUL,
    2018: CIANO,
    2019: LILAS,
    2020: PRINCIPAL,
    2021: "#E879F9",
}
ANO_TRACEJADO = 2021
CORES_CANAL = {"Loja física": PRINCIPAL, "Online": CIANO}
MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
METRICAS_PIRAMIDE = {
    "Clientes distintos": "clientes",
    "Receita": "receita_usd",
    "Ticket médio": "ticket_medio_usd",
}
GENERO_ROTULO = {"Male": "Masculino", "Female": "Feminino"}
GENERO_COR = {"Male": AZUL, "Female": PRINCIPAL}


# --- Leitura (D2) ----------------------------------------------------------
def tabelas_faltando(nomes=MARTS, arquivo_banco=ARQUIVO_BANCO):
    """Nomes de `nomes` que não existem em marts. Sem banco, todos faltam
    (e nada é criado: não se conecta a um arquivo que não existe)."""
    arquivo_banco = Path(arquivo_banco)
    if not arquivo_banco.is_file():
        return list(nomes)
    con = duckdb.connect(str(arquivo_banco), read_only=True)
    try:
        existentes = {
            linha[0]
            for linha in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'marts'"
            ).fetchall()
        }
    finally:
        con.close()
    return [n for n in nomes if n not in existentes]


def ler(nomes=MARTS, arquivo_banco=ARQUIVO_BANCO):
    """{nome: DataFrame} com SELECT * FROM marts.<nome>; conexão aberta e fechada aqui."""
    con = duckdb.connect(str(arquivo_banco), read_only=True)
    try:
        return {nome: con.execute(f"SELECT * FROM marts.{nome}").df() for nome in nomes}
    finally:
        con.close()


# --- Formatação (D4) -------------------------------------------------------
def _vazio(valor):
    if valor is None:
        return True
    try:
        return math.isnan(valor)
    except TypeError:
        return False


def _milhar(valor, casas):
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "\0").replace(".", ",").replace("\0", ".")


def usd(valor, casas=2):
    if _vazio(valor):
        return "n/d"
    sinal = "−" if valor < 0 else ""
    return f"{sinal}US$ {_milhar(abs(valor), casas)}"


def usd_curto(valor):
    if _vazio(valor):
        return "n/d"
    sinal = "−" if valor < 0 else ""
    absoluto = abs(valor)
    if absoluto >= 1_000_000:
        return f"{sinal}US$ {_milhar(absoluto / 1_000_000, 2)} mi"
    if absoluto >= 1_000:
        return f"{sinal}US$ {_milhar(absoluto / 1_000, 0)} mil"
    return f"{sinal}US$ {_milhar(absoluto, 0)}"


def usd_eixo(valor):
    """US$ abreviado para marcas de eixo: sem casas quando o valor é redondo."""
    if _vazio(valor):
        return "n/d"
    absoluto = abs(valor)
    if absoluto >= 1_000_000:
        n = absoluto / 1_000_000
        return f"US$ {_milhar(n, 0 if n == int(n) else 1)} mi"
    if absoluto >= 1_000:
        return f"US$ {_milhar(absoluto / 1_000, 0)} mil"
    return f"US$ {_milhar(absoluto, 0)}"


def pct(valor, casas=1):
    if _vazio(valor):
        return "n/d"
    return f"{_milhar(valor, casas)}%"


def pct_sinal(valor, casas=1):
    """Variação com sinal: +42,8% / −49,1%; nulo vira n/d."""
    if _vazio(valor):
        return "n/d"
    sinal = "+" if valor > 0 else "−" if valor < 0 else ""
    return f"{sinal}{_milhar(abs(valor), casas)}%"


def numero(valor, casas=0):
    if _vazio(valor):
        return "n/d"
    return _milhar(valor, casas)


# --- Apoio de desenho ------------------------------------------------------
def _passo(maximo, alvo=4):
    """Passo 'redondo' (1, 2, 2,5 ou 5 × 10^k) para ~alvo marcas até `maximo`."""
    bruto = maximo / alvo
    potencia = 10 ** (len(str(int(bruto))) - 1) if bruto >= 1 else 1
    for fator in (1, 2, 2.5, 5, 10):
        if fator * potencia >= bruto:
            return fator * potencia
    return 10 * potencia


def _marcas_log(minimo, maximo):
    """Marcas 1 e 3 × 10^k (espaçadas por igual no eixo logarítmico) entre minimo e maximo."""
    marcas = []
    potencia = 10 ** (len(str(int(minimo))) - 1)
    while potencia <= maximo * 10:
        marcas.extend(f * potencia for f in (1, 3))
        potencia *= 10
    return [m for m in marcas if minimo / 2 <= m <= maximo * 2]


def _eixo_usd(fig, eixo, maximo, alvo=4):
    """Marcas do eixo em US$ abreviado (mi/mil), pt-BR."""
    passo = _passo(maximo, alvo)
    valores = [passo * i for i in range(int(maximo // passo) + 2)]
    textos = [usd_eixo(v) for v in valores]
    if eixo == "x":
        fig.update_xaxes(tickvals=valores, ticktext=textos, tickangle=0)
    else:
        fig.update_yaxes(tickvals=valores, ticktext=textos)


def _base(fig, altura=340, legenda=False):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": TEXTO, "size": 12},
        margin={"l": 8, "r": 8, "t": 34 if legenda else 8, "b": 8},
        height=altura,
        showlegend=legenda,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.0, "x": 0, "font": {"color": TEXTO_EIXO}},
        hoverlabel={"bgcolor": CARTAO, "font_color": TEXTO, "bordercolor": PRINCIPAL},
    )
    fig.update_xaxes(gridcolor=GRADE, zeroline=False, linecolor=GRADE, tickfont={"color": TEXTO_EIXO})
    fig.update_yaxes(gridcolor=GRADE, zeroline=False, linecolor=GRADE, tickfont={"color": TEXTO_EIXO})
    return fig


# --- Gráficos (D6) ---------------------------------------------------------
def grafico_01(df):
    """Receita Anual: colunas, destaque no melhor ano, variação % sobre cada coluna."""
    df = df.sort_values("ano")
    rotulos = [
        f"{ano} (parcial)" if meses < 12 else str(ano)
        for ano, meses in zip(df["ano"], df["meses_com_venda"])
    ]
    textos = [
        f"{usd_curto(r)}<br>{pct_sinal(v)}" for r, v in zip(df["receita_usd"], df["variacao_pct"])
    ]
    detalhe = [
        [usd(r), numero(p), pct_sinal(v)]
        for r, p, v in zip(df["receita_usd"], df["pedidos"], df["variacao_pct"])
    ]
    cores = [PRINCIPAL if m else ROXO_ESCURO for m in df["melhor_ano"]]
    fig = go.Figure(
        go.Bar(
            x=rotulos,
            y=df["receita_usd"],
            marker_color=cores,
            text=textos,
            textposition="outside",
            cliponaxis=False,
            customdata=detalhe,
            hovertemplate="<b>%{x}</b><br>Receita: %{customdata[0]}<br>Pedidos: %{customdata[1]}"
            "<br>Variação: %{customdata[2]}<extra></extra>",
        )
    )
    _base(fig)
    _eixo_usd(fig, "y", df["receita_usd"].max())
    fig.update_yaxes(range=[0, df["receita_usd"].max() * 1.25])
    fig.update_xaxes(type="category")  # senão "2016"... viram números e o rótulo "2021 (parcial)" some
    return fig


def grafico_02(df):
    """Receita Mensal com Sazonalidade: uma linha por ano; marca o maior e o menor mês."""
    fig = go.Figure()
    for ano, parte in _por_ano(df):
        cor = CORES_ANO.get(int(ano), LILAS)
        fig.add_trace(
            go.Scatter(
                x=[MESES[m - 1] for m in parte["mes"]],
                y=parte["receita_usd"],
                name=str(ano),
                mode="lines+markers",
                line={"color": cor, "width": 2, "dash": "dash" if int(ano) == ANO_TRACEJADO else "solid"},
                marker={"size": 5},
                customdata=[[usd(r), numero(p)] for r, p in zip(parte["receita_usd"], parte["pedidos"])],
                hovertemplate=f"<b>%{{x}}/{ano}</b><br>Receita: %{{customdata[0]}}"
                "<br>Pedidos: %{customdata[1]}<extra></extra>",
            )
        )
    ordenado = df.sort_values("receita_usd")
    for rotulo, linha, posicao in (
        ("máx", ordenado.iloc[-1], "middle left"),
        ("mín", ordenado.iloc[0], "bottom center"),
    ):
        fig.add_trace(
            go.Scatter(
                x=[MESES[int(linha["mes"]) - 1]],
                y=[linha["receita_usd"]],
                mode="markers+text",
                marker={"size": 11, "color": "rgba(0,0,0,0)", "line": {"color": TEXTO, "width": 2}},
                text=[f"{rotulo} {MESES[int(linha['mes']) - 1]}/{int(linha['ano'])} · {usd_curto(linha['receita_usd'])}  "],
                textposition=posicao,
                textfont={"color": TEXTO, "size": 11},
                showlegend=False,
                hoverinfo="skip",
            )
        )
    _base(fig, legenda=True)
    _eixo_usd(fig, "y", df["receita_usd"].max())
    # folga embaixo para o rótulo do menor mês não cair sobre as linhas
    fig.update_yaxes(range=[-df["receita_usd"].max() * 0.1, df["receita_usd"].max() * 1.15])
    return fig


def _por_ano(df):
    """Separa o DataFrame por ano (apenas fatiar linhas, sem agregar)."""
    for ano in sorted(df["ano"].unique()):
        yield ano, df[df["ano"] == ano].sort_values("mes")


def grafico_03(df):
    """Receita por Categoria: barras horizontais, maior em cima."""
    df = df.sort_values("receita_usd", ascending=False)
    fig = go.Figure(
        go.Bar(
            y=df["categoria"],
            x=df["receita_usd"],
            orientation="h",
            marker_color=PRINCIPAL,
            text=[f"{usd_curto(r)} · {pct(p)}" for r, p in zip(df["receita_usd"], df["participacao_pct"])],
            textposition="outside",
            cliponaxis=False,
            customdata=[[usd(r), pct(p), numero(i)] for r, p, i in zip(df["receita_usd"], df["participacao_pct"], df["itens"])],
            hovertemplate="<b>%{y}</b><br>Receita: %{customdata[0]}<br>Participação: %{customdata[1]}"
            "<br>Itens: %{customdata[2]}<extra></extra>",
        )
    )
    _base(fig)
    fig.update_yaxes(autorange="reversed")
    _eixo_usd(fig, "x", df["receita_usd"].max(), alvo=3)
    fig.update_xaxes(range=[0, df["receita_usd"].max() * 1.45])
    return fig


def grafico_04(df):
    """Margem por Categoria: da maior para a menor margem; maior em roxo, menor em ciano."""
    df = df.sort_values("margem_pct", ascending=False)
    maior, menor = df["margem_pct"].max(), df["margem_pct"].min()
    cores = [PRINCIPAL if m == maior else CIANO if m == menor else NEUTRO for m in df["margem_pct"]]
    fig = go.Figure(
        go.Bar(
            y=df["categoria"],
            x=df["margem_pct"],
            orientation="h",
            marker_color=cores,
            text=[pct(m) for m in df["margem_pct"]],
            textposition="outside",
            cliponaxis=False,
            customdata=[[pct(m), usd(r), usd(l)] for m, r, l in zip(df["margem_pct"], df["receita_usd"], df["lucro_usd"])],
            hovertemplate="<b>%{y}</b><br>Margem ponderada: %{customdata[0]}<br>Receita: %{customdata[1]}"
            "<br>Lucro: %{customdata[2]}<extra></extra>",
        )
    )
    _base(fig)
    fig.update_yaxes(autorange="reversed")
    base = int(menor) // 5 * 5 - 5  # eixo não começa em zero: senão 54,7% e 61,0% parecem iguais
    fig.update_xaxes(range=[base, maior + 2.5], ticksuffix="%")
    return fig


def grafico_05(df, referencia):
    """Receita × Margem por Subcategoria (bolhas) com linhas de referência."""
    fig = px.scatter(
        df,
        x="receita_usd",
        y="margem_pct",
        size="itens",
        size_max=38,
        custom_data=["subcategoria", "categoria", "receita_usd", "margem_pct", "itens"],
    )
    fig.update_traces(
        marker={"color": "rgba(145,73,245,0.7)", "line": {"color": LILAS, "width": 1.2}},
        customdata=[
            [s, c, usd(r), pct(m), numero(i)]
            for s, c, r, m, i in zip(df["subcategoria"], df["categoria"], df["receita_usd"], df["margem_pct"], df["itens"])
        ],
        hovertemplate="<b>%{customdata[0]}</b> (%{customdata[1]})<br>Receita: %{customdata[2]}"
        "<br>Margem: %{customdata[3]}<br>Itens: %{customdata[4]}<extra></extra>",
    )
    ref = referencia.iloc[0]
    fig.add_vline(x=ref["mediana_receita_usd"], line={"color": TEXTO_SEC, "dash": "dot"})
    fig.add_hline(y=ref["margem_global_pct"], line={"color": CIANO, "dash": "dot"})
    # as duas linhas de referência entram na legenda: rótulo sobre o gráfico cobria as bolhas
    for nome, cor in (
        (f"Mediana da receita ({usd_curto(ref['mediana_receita_usd'])})", TEXTO_SEC),
        (f"Margem global ({pct(ref['margem_global_pct'])})", CIANO),
    ):
        fig.add_trace(
            go.Scatter(x=[None], y=[None], mode="lines", name=nome, line={"color": cor, "dash": "dot"})
        )
    _base(fig, legenda=True)
    # eixo logarítmico: uma subcategoria de US$ 9,9 mi comprimiria as outras 31 no canto esquerdo
    marcas = _marcas_log(df["receita_usd"].min(), df["receita_usd"].max())
    fig.update_xaxes(type="log", tickvals=marcas, ticktext=[usd_eixo(m) for m in marcas], tickangle=0)
    fig.update_yaxes(ticksuffix="%", title_text="Margem", title_font_color=TEXTO_SEC)
    fig.update_xaxes(title_text="Receita (escala logarítmica)", title_font_color=TEXTO_SEC)
    return fig


def grafico_06(df):
    """Top 5 Marcas: colunas verticais, maior à esquerda."""
    df = df.sort_values("receita_usd", ascending=False)
    fig = go.Figure(
        go.Bar(
            x=df["marca"],
            y=df["receita_usd"],
            marker_color=PRINCIPAL,
            text=[f"{usd_curto(r)}<br>{pct(p)}" for r, p in zip(df["receita_usd"], df["participacao_pct"])],
            textposition="outside",
            cliponaxis=False,
            customdata=[[usd(r), pct(p), numero(i)] for r, p, i in zip(df["receita_usd"], df["participacao_pct"], df["itens"])],
            hovertemplate="<b>%{x}</b><br>Receita: %{customdata[0]}<br>Participação: %{customdata[1]}"
            "<br>Itens: %{customdata[2]}<extra></extra>",
        )
    )
    _base(fig)
    _eixo_usd(fig, "y", df["receita_usd"].max())
    fig.update_yaxes(range=[0, df["receita_usd"].max() * 1.25])
    return fig


def _marcas_barra(maximo):
    passo = _passo(maximo, alvo=3)
    return [passo * i for i in range(int(maximo // passo) + 1)]


def grafico_07(df, altura=300):
    """Receita por País: mapa coroplético (escala do fundo ao roxo)."""
    fig = go.Figure(
        go.Choropleth(
            locations=df["pais"],
            locationmode="country names",
            z=df["receita_usd"],
            colorscale=[[0, "#2B3560"], [1, PRINCIPAL]],
            showscale=True,
            colorbar={
                "orientation": "h", "thickness": 8, "len": 0.7, "x": 0.5, "y": -0.02, "yanchor": "top",
                "tickfont": {"color": TEXTO_EIXO, "size": 10}, "outlinewidth": 0,
                "tickvals": _marcas_barra(df["receita_usd"].max()),
                "ticktext": [usd_eixo(v) for v in _marcas_barra(df["receita_usd"].max())],
            },
            marker_line_color=FUNDO,
            customdata=[[usd(r), pct(p), numero(c)] for r, p, c in zip(df["receita_usd"], df["participacao_pct"], df["clientes"])],
            text=df["pais"],
            hovertemplate="<b>%{text}</b><br>Receita: %{customdata[0]}<br>Participação: %{customdata[1]}"
            "<br>Clientes: %{customdata[2]}<extra></extra>",
        )
    )
    fig.update_geos(
        bgcolor="rgba(0,0,0,0)", landcolor="#1D2747", showcountries=True, countrycolor=FUNDO,
        showocean=False, showlakes=False, showframe=False, coastlinecolor=FUNDO,
        projection_type="natural earth", fitbounds="locations",
    )
    _base(fig, altura=altura)
    fig.update_layout(margin={"l": 0, "r": 0, "t": 0, "b": 30})
    return fig


def tabela_07(df):
    """Ranking de países (texto já formatado), maior receita primeiro."""
    df = df.sort_values("receita_usd", ascending=False)
    return pd.DataFrame(
        {
            "País": df["pais"].to_list(),
            "Receita": [usd_curto(v) for v in df["receita_usd"]],
            "%": [pct(v) for v in df["participacao_pct"]],
            "Clientes": [numero(v) for v in df["clientes"]],
        }
    )


def grafico_08_total(df):
    """Online × Loja física no total geral (linhas ano = 'Total'): rosca."""
    total = df[df["ano"] == "Total"].sort_values("canal")
    fig = go.Figure(
        go.Pie(
            labels=total["canal"],
            values=total["receita_usd"],
            hole=0.62,
            marker={"colors": [CORES_CANAL.get(c, LILAS) for c in total["canal"]], "line": {"color": CARTAO, "width": 2}},
            text=[f"{pct(p)}<br>{usd_curto(r)}" for p, r in zip(total["participacao_pct"], total["receita_usd"])],
            textinfo="text",
            textposition="outside",
            insidetextorientation="horizontal",
            sort=False,
            customdata=[[usd(r), pct(p)] for r, p in zip(total["receita_usd"], total["participacao_pct"])],
            hovertemplate="<b>%{label}</b><br>Receita: %{customdata[0]}<br>Participação: %{customdata[1]}<extra></extra>",
        )
    )
    _base(fig, altura=300, legenda=True)
    fig.update_layout(margin={"l": 40, "r": 40, "t": 34, "b": 20})
    return fig


def grafico_08_evolucao(df):
    """Participação de cada canal por ano (colunas empilhadas 100%)."""
    anos = df[df["ano"] != "Total"].sort_values(["ano", "canal"])
    fig = go.Figure()
    for canal in sorted(anos["canal"].unique()):
        parte = anos[anos["canal"] == canal]
        fig.add_trace(
            go.Bar(
                x=parte["ano"],
                y=parte["receita_usd"],
                name=canal,
                marker_color=CORES_CANAL.get(canal, LILAS),
                text=[pct(p) for p in parte["participacao_pct"]],
                textposition="inside",
                customdata=[[usd(r), pct(p)] for r, p in zip(parte["receita_usd"], parte["participacao_pct"])],
                hovertemplate=f"<b>{canal} · %{{x}}</b><br>Receita: %{{customdata[0]}}"
                "<br>Participação: %{customdata[1]}<extra></extra>",
            )
        )
    fig.update_layout(barmode="stack", barnorm="percent")
    _base(fig, altura=300, legenda=True)
    fig.update_yaxes(ticksuffix="%")
    fig.update_xaxes(type="category")  # anos em texto: sem isso viram eixo numérico e perdem colunas
    return fig


def grafico_09(df, tendencia, altura=340):
    """Desempenho das Lojas: dispersão área × receita com reta de tendência (mart 13)."""
    detalhe = [
        [int(c), p, e, numero(m), usd(r), usd(rm)]
        for c, p, e, m, r, rm in zip(
            df["chave_loja"], df["pais"], df["estado"], df["metros_quadrados"], df["receita_usd"], df["receita_por_m2"]
        )
    ]
    fig = go.Figure(
        go.Scatter(
            x=df["metros_quadrados"],
            y=df["receita_usd"],
            mode="markers",
            marker={"size": 9, "color": "rgba(145,73,245,0.7)", "line": {"color": LILAS, "width": 1}},
            customdata=detalhe,
            hovertemplate="<b>Loja %{customdata[0]}</b> · %{customdata[1]}, %{customdata[2]}"
            "<br>Área: %{customdata[3]} m²<br>Receita: %{customdata[4]}"
            "<br>Receita por m²: %{customdata[5]}<extra></extra>",
            name="Lojas",
        )
    )
    t = tendencia.iloc[0]
    x0, x1 = df["metros_quadrados"].min(), df["metros_quadrados"].max()
    fig.add_trace(
        go.Scatter(
            x=[x0, x1],
            y=[t["intercepto"] + t["inclinacao"] * x0, t["intercepto"] + t["inclinacao"] * x1],
            mode="lines",
            line={"color": CIANO, "width": 2, "dash": "dash"},
            name=f"Tendência (R² {numero(t['r2'], 2)})",
            hoverinfo="skip",
        )
    )
    _base(fig, altura=altura, legenda=True)
    _eixo_usd(fig, "y", df["receita_usd"].max())
    fig.update_xaxes(title_text="Área da loja (m²)", title_font_color=TEXTO_SEC)
    fig.update_yaxes(title_text="Receita", title_font_color=TEXTO_SEC)
    return fig


def lista_lojas(df, tipo):
    """Top 10 (tipo='top') ou Bottom 10 (tipo='bottom') por receita ÷ m²."""
    coluna = "ranking_top" if tipo == "top" else "ranking_bottom"
    parte = df[df[coluna] <= 10].sort_values(coluna)
    return pd.DataFrame(
        {
            "#": [int(v) for v in parte[coluna]],
            "Loja": [f"{p} · {e}" for p, e in zip(parte["pais"], parte["estado"])],
            "US$/m²": [numero(v, 2) for v in parte["receita_por_m2"]],
        }
    )


def grafico_10(df, metrica="Clientes distintos", altura=320):
    """Perfil de Clientes: pirâmide por faixa etária; masculino à esquerda."""
    coluna = METRICAS_PIRAMIDE[metrica]
    formatar = {"clientes": numero, "receita_usd": usd_curto, "ticket_medio_usd": usd}[coluna]
    faixas = sorted(df["faixa_etaria"].unique())
    fig = go.Figure()
    for genero in ("Male", "Female"):
        parte = df[df["genero"] == genero].set_index("faixa_etaria").reindex(faixas)
        valores = parte[coluna]
        fig.add_trace(
            go.Bar(
                y=faixas,
                x=-valores if genero == "Male" else valores,  # só desenho: Masculino cresce à esquerda
                orientation="h",
                name=GENERO_ROTULO[genero],
                marker_color=GENERO_COR[genero],
                text=[formatar(v) for v in valores],
                textposition="outside",
                cliponaxis=False,
                customdata=[
                    [formatar(v), numero(c), usd(r), numero(p)]
                    for v, c, r, p in zip(valores, parte["clientes"], parte["receita_usd"], parte["pedidos"])
                ],
                hovertemplate=f"<b>{GENERO_ROTULO[genero]} · %{{y}}</b><br>{metrica}: %{{customdata[0]}}"
                "<br>Clientes: %{customdata[1]}<br>Receita: %{customdata[2]}"
                "<br>Pedidos: %{customdata[3]}<extra></extra>",
            )
        )
    maximo = df[coluna].max()
    passo = _passo(maximo, alvo=3)
    marcas = [passo * i for i in range(int(maximo // passo) + 1)]
    ticks = [-m for m in reversed(marcas[1:])] + marcas
    formatar_eixo = {"clientes": numero, "receita_usd": usd_eixo, "ticket_medio_usd": lambda v: usd(v, 0)}[coluna]
    fig.update_layout(barmode="overlay", bargap=0.25)
    _base(fig, altura=altura, legenda=True)
    fig.update_traces(textfont={"size": 10})
    fig.update_xaxes(
        tickvals=ticks,
        ticktext=[formatar_eixo(abs(t)) for t in ticks],
        tickangle=0,
        range=[-maximo * 1.6, maximo * 1.6],  # folga para o rótulo de fora não cobrir a faixa etária
    )
    return fig
