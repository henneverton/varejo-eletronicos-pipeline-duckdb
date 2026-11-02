"""Página do dashboard de vendas (spec 004).

Executar com:  uv run streamlit run app.py   (encerrar com Ctrl+C)

Lê as 13 tabelas do schema `marts` de data/projeto.duckdb por meio de painel.py
e desenha 4 KPIs e 10 gráficos. Nenhum cálculo aqui (nem em painel.py): número
novo na tela exige um .sql novo em sql/marts/ e uma nova execução de marts.py.

Regras e por que existem
------------------------
1. Só `marts` é lido, em conexão somente leitura aberta e fechada em
   painel.ler(). Motivo: marts.py precisa conseguir gravar com a página de pé.
2. Leitura com st.cache_data; o botão "Recarregar dados" limpa o cache. Motivo:
   depois de rodar marts.py de novo, a página mostra o dado novo sem reiniciar.
3. Banco ausente ou qualquer das 13 tabelas faltando: st.error dizendo quais e
   o comando para gerar, e st.stop(); sem traceback e sem criar banco. Motivo:
   dashboard em branco parece negócio parado.
4. Layout wide, de cima para baixo: cabeçalho, 4 KPIs, linha 01·02·03, linha
   04·05·06 e linha 07·08·09·10. Os KPIs vêm de marts.kpis, sem variação (não há
   filtro de período). Motivo: a ordem conta a história Evolução → Rentabilidade
   → Produtos → Geografia → Canais → Eficiência → Clientes.
5. Em 07 e 09 a lista/ranking fica abaixo da figura, não ao lado. Motivo: com
   quatro cartões na mesma linha, a largura não comporta duas colunas em cada.
"""

import streamlit as st

import painel

st.set_page_config(page_title="Dashboard de Vendas", layout="wide")

CSS = f"""
<style>
.stApp {{ background: {painel.FUNDO}; }}
.block-container {{ padding-top: 1.6rem; max-width: 100%; }}
[data-testid="stVerticalBlockBorderWrapper"] {{
    background: {painel.CARTAO}; border: 1px solid #2A3560 !important;
    border-radius: 12px; box-shadow: 0 4px 18px rgba(0,0,0,.25);
}}
[data-testid="stMetric"] {{
    background: {painel.CARTAO}; border: 1px solid #2A3560; border-radius: 12px;
    padding: 14px 18px; box-shadow: 0 0 18px rgba(145,73,245,.18);
}}
[data-testid="stMetricValue"] {{ color: {painel.LILAS}; }}
.titulo-cartao {{ font-weight: 600; font-size: 1.02rem; color: {painel.TEXTO}; margin: 0; }}
.pergunta-cartao {{ font-size: .82rem; color: {painel.TEXTO_SEC}; margin: 0 0 .4rem 0; }}
.nota-cartao {{ font-size: .75rem; color: {painel.TEXTO_SEC}; margin-top: .4rem; }}
h1 {{ margin-bottom: 0; }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

CONFIG_GRAFICO = {"displayModeBar": False}


def plotar(fig, chave):
    st.plotly_chart(fig, width="stretch", config=CONFIG_GRAFICO, key=chave)


def cabecalho_cartao(titulo, pergunta):
    st.markdown(
        f'<p class="titulo-cartao">{titulo}</p><p class="pergunta-cartao">{pergunta}</p>',
        unsafe_allow_html=True,
    )


def nota(texto):
    st.markdown(f'<p class="nota-cartao">{texto}</p>', unsafe_allow_html=True)


# --- Verificação (D8) ------------------------------------------------------
faltando = painel.tabelas_faltando()
if faltando:
    if not painel.ARQUIVO_BANCO.is_file():
        st.error(
            f"Banco não encontrado: {painel.ARQUIVO_BANCO}. "
            "Rode, nesta ordem: `uv run python ingestao.py`, `uv run python refined.py` "
            "e `uv run python marts.py`."
        )
    else:
        st.error(
            "Faltam tabelas no schema marts: "
            + ", ".join(f"marts.{n}" for n in faltando)
            + ". Rode `uv run python marts.py` (se faltar o schema refined, rode antes "
            "`uv run python refined.py`)."
        )
    st.stop()


@st.cache_data
def carregar():
    return painel.ler()


dados = carregar()

# --- Linha 1: cabeçalho ----------------------------------------------------
topo_titulo, topo_botao = st.columns([6, 1], vertical_alignment="center")
with topo_titulo:
    st.title("Dashboard de Vendas")
    st.caption("Análise de Receita, Margem, Canais, Lojas e Clientes.")
with topo_botao:
    if st.button("Recarregar dados", width="stretch"):
        st.cache_data.clear()
        st.rerun()

# --- Linha 2: KPIs ---------------------------------------------------------
kpi = dados["kpis"].iloc[0]
k1, k2, k3, k4 = st.columns(4)
k1.metric(
    "◉ Receita Total",
    painel.usd_curto(kpi["receita_usd"]),
    help="Quantidade × preço de tabela em US$, período inteiro.",
)
k2.metric(
    "◐ Margem Média",
    painel.pct(kpi["margem_pct"]),
    help="Ponderada: lucro total ÷ receita total (nunca média de margens).",
)
k3.metric(
    "▦ Total de Itens",
    painel.numero(kpi["itens"]),
    help="Soma das quantidades vendidas.",
)
k4.metric(
    "◍ Clientes",
    painel.numero(kpi["clientes"]),
    help="Clientes distintos que compraram (os cadastrados sem compra não entram).",
)

# --- Linha 3: 01 · 02 · 03 -------------------------------------------------
c1, c2, c3 = st.columns(3)
with c1, st.container(border=True):
    cabecalho_cartao("01 — Receita Anual", "Como a receita evoluiu e qual foi o melhor ano?")
    plotar(painel.grafico_01(dados["receita_anual"]), "g01")
with c2, st.container(border=True):
    cabecalho_cartao("02 — Receita Mensal e Sazonalidade", "Em quais meses se fatura mais e menos?")
    plotar(painel.grafico_02(dados["receita_mensal_sazonalidade"]), "g02")
with c3, st.container(border=True):
    cabecalho_cartao("03 — Receita por Categoria", "Quais categorias concentram a receita?")
    plotar(painel.grafico_03(dados["receita_por_categoria"]), "g03")

# --- Linha 4: 04 · 05 · 06 -------------------------------------------------
c4, c5, c6 = st.columns(3)
with c4, st.container(border=True):
    cabecalho_cartao("04 — Margem por Categoria", "Quais categorias são mais e menos rentáveis?")
    ordem = painel.ordem_categorias(dados["receita_por_categoria"])
    plotar(painel.grafico_04(dados["margem_por_categoria"], ordem), "g04")
with c5, st.container(border=True):
    cabecalho_cartao(
        "05 — Receita × Margem por Subcategoria",
        "Quais subcategorias vendem muito com pouca margem e quais são nichos rentáveis?",
    )
    plotar(
        painel.grafico_05(dados["receita_x_margem_subcategoria"], dados["referencia_subcategorias"]),
        "g05",
    )
with c6, st.container(border=True):
    cabecalho_cartao("06 — Top 5 Marcas", "Quais marcas concentram as vendas?")
    plotar(painel.grafico_06(dados["top5_marcas"]), "g06")

# --- Linha 5: 07 · 08 · 09 · 10 --------------------------------------------
c7, c8, c9, c10 = st.columns([1.15, 1, 1.25, 1])
with c7, st.container(border=True):
    cabecalho_cartao("07 — Receita por País", "Em quais países está concentrada a receita?")
    plotar(painel.grafico_07(dados["receita_por_pais"]), "g07")
    nota("Se o mapa não carregar (ele busca o mapa-base na internet), use o ranking.")
    st.dataframe(painel.tabela_07(dados["receita_por_pais"]), hide_index=True, width="stretch")
with c8, st.container(border=True):
    cabecalho_cartao("08 — Online × Lojas Físicas", "Qual a participação de cada canal e como evolui?")
    aba_total, aba_evolucao = st.tabs(["Total", "Evolução"])
    with aba_total:
        plotar(painel.grafico_08_total(dados["online_x_lojas_fisicas"]), "g08t")
    with aba_evolucao:
        plotar(painel.grafico_08_evolucao(dados["online_x_lojas_fisicas"]), "g08e")
with c9, st.container(border=True):
    cabecalho_cartao("09 — Desempenho das Lojas", "Lojas maiores vendem mais? Quais são as mais produtivas por m²?")
    plotar(painel.grafico_09(dados["desempenho_das_lojas"], dados["tendencia_lojas"]), "g09")
    esquerda, direita = st.columns(2)
    with esquerda:
        st.markdown("**Top 10** · US$ por m²")
        st.dataframe(painel.lista_lojas(dados["desempenho_das_lojas"], "top"), hide_index=True, width="stretch")
    with direita:
        st.markdown("**Bottom 10** · US$ por m²")
        st.dataframe(painel.lista_lojas(dados["desempenho_das_lojas"], "bottom"), hide_index=True, width="stretch")
    nota("Lojas abertas depois de 2016 têm menos tempo de venda e são penalizadas na receita por m².")
with c10, st.container(border=True):
    cabecalho_cartao("10 — Perfil de Clientes", "Qual a faixa etária e o gênero de quem compra?")
    metrica = st.radio(
        "Métrica", list(painel.METRICAS_PIRAMIDE), horizontal=True, label_visibility="collapsed", key="metrica10"
    )
    plotar(painel.grafico_10(dados["perfil_de_clientes"], metrica), "g10")

st.caption(
    "Receita = quantidade × preço de tabela em US$ (cadastro atual, sem histórico de preços). "
    "Dados de 01/01/2016 a 20/02/2021; 2021 é parcial."
)
