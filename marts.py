"""Camada marts no DuckDB (spec 003).

Executar com:  uv run python marts.py

Lê os arquivos de sql/marts/ e grava o schema `marts` de data/projeto.duckdb:
uma tabela por arquivo, para os gráficos do dashboard. Toda a regra de negócio
mora nos arquivos .sql; este script só os executa (encanamento).

Regras e por que existem
------------------------
1. Escopo: lê de `refined`, escreve em `marts`, nunca escreve em `raw` nem em
   `refined`. O schema `marts` é apagado e recriado a cada execução (DROP SCHEMA
   IF EXISTS marts CASCADE). Motivo: um mart cujo arquivo foi apagado ou
   renomeado não pode continuar existindo no banco.
2. Um arquivo, uma tabela: todos os sql/marts/*.sql em ordem alfabética (o
   prefixo NN_ dá a ordem); nome da tabela = nome do arquivo sem `NN_` e sem
   `.sql` (01_receita_anual.sql -> marts.receita_anual). Motivo: o nome digitado
   nas consultas do dashboard é o mesmo que se vê na pasta, e adicionar um
   gráfico é criar um arquivo, sem tocar no Python.
3. Execução: CREATE TABLE marts.<nome> AS <conteúdo do arquivo>. O Python tira
   só os espaços e um `;` do final e nada mais; não divide o texto por `;`
   (quatro arquivos têm `;` dentro de comentário) e lê em UTF-8 declarado
   (os arquivos têm acento e travessão; o padrão do Windows é cp1252). CREATE
   simples, e não OR REPLACE: o schema acabou de ser recriado, então colisão de
   nome seria erro, não substituição.
4. Nenhuma regra de negócio aqui: sem cálculo, filtro, join, renomeação ou
   conversão de tipo. Motivo: regra no Python escapa da revisão das specs;
   no .sql ela aparece onde o analista vai olhar.
5. Atomicidade: DROP SCHEMA, CREATE SCHEMA e as criações das tabelas ficam numa
   só transação. Qualquer falha faz ROLLBACK e `marts` volta a ser o da última
   execução que deu certo. Para no primeiro erro; os arquivos seguintes não
   rodam. Motivo: um schema pela metade quebra o dashboard sem avisar.
6. Erros antes de executar qualquer SQL, todos com sys.exit(1) e sem criar
   arquivo, pasta ou schema: pasta sem .sql; arquivo fora do padrão NN_nome.sql;
   dois arquivos com o mesmo nome de tabela (o segundo sobrescreveria o primeiro
   em silêncio); banco inexistente (abrir criaria um banco vazio que parece
   válido); tabela de `refined` faltando.
7. Durante a execução: SQL que falha mostra o nome do arquivo e a mensagem do
   DuckDB; mart com zero linhas é erro. Motivo: mart vazio é quase sempre um
   JOIN que não casou, e um dashboard vazio parece um negócio parado.
8. Saída: uma linha por mart com a contagem lida do banco (milhar com ponto) e
   uma linha final com o número de marts e o total. Nenhuma contagem é fixada
   no código: elas decorrem dos dados; a referência de comparação é a tabela
   da seção 1 de specs/003-marts.md.
9. Caminhos calculados a partir deste arquivo, nunca do diretório corrente;
   sem efeito colateral ao importar; quem abre a conexão a fecha.
"""

import re
import sys
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parent
ARQUIVO_BANCO = RAIZ / "data" / "projeto.duckdb"
PASTA_SQL = RAIZ / "sql" / "marts"

ORIGEM = "refined"
DESTINO = "marts"
TABELAS_REFINED = [
    "vendas",
    "clientes",
    "produtos",
    "lojas",
    "taxas_cambio",
    "dicionario_dados",
]
PADRAO_ARQUIVO = re.compile(r"^\d{2}_([a-z0-9_]+)\.sql$")


class ErroMarts(Exception):
    """Falha de verificação ou execução: a transação deve ser desfeita."""


def formatar_milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def falhar(*linhas: str) -> None:
    for linha in linhas:
        print(linha, file=sys.stderr)
    sys.exit(1)


def listar_marts(pasta_sql: Path) -> list[tuple[Path, str]]:
    """Devolve (arquivo, nome da tabela) em ordem alfabética, ou encerra com erro."""
    arquivos = sorted(pasta_sql.glob("*.sql")) if pasta_sql.is_dir() else []
    if not arquivos:
        falhar(f"Nenhum arquivo .sql em {pasta_sql}")

    fora_do_padrao = [a.name for a in arquivos if not PADRAO_ARQUIVO.match(a.name)]
    if fora_do_padrao:
        falhar(
            f"Arquivos fora do padrão NN_nome.sql em {pasta_sql}: {', '.join(fora_do_padrao)}"
        )

    por_nome: dict[str, list[str]] = {}
    for a in arquivos:
        nome = PADRAO_ARQUIVO.match(a.name).group(1)
        por_nome.setdefault(nome, []).append(a.name)
    duplicados = {n: fs for n, fs in por_nome.items() if len(fs) > 1}
    if duplicados:
        falhar(
            *(
                f"Arquivos que dão a mesma tabela marts.{n}: {', '.join(fs)}"
                for n, fs in duplicados.items()
            )
        )

    return [(a, PADRAO_ARQUIVO.match(a.name).group(1)) for a in arquivos]


def contar(con: duckdb.DuckDBPyConnection, tabela_completa: str) -> int:
    # fetchall (não fetchone): fetchone deixa o resultado aberto no DuckDB 2.x
    return con.execute(f"SELECT count(*) FROM {tabela_completa}").fetchall()[0][0]


def tabelas_refined_faltando(con: duckdb.DuckDBPyConnection) -> list[str]:
    existentes = {
        linha[0]
        for linha in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
            [ORIGEM],
        ).fetchall()
    }
    return [f"{ORIGEM}.{t}" for t in TABELAS_REFINED if t not in existentes]


def ler_select(arquivo: Path) -> str:
    sql = arquivo.read_text(encoding="utf-8").strip()
    if sql.endswith(";"):
        sql = sql[:-1].rstrip()
    return sql


def criar_marts(con: duckdb.DuckDBPyConnection, marts: list[tuple[Path, str]]) -> None:
    con.execute(f"DROP SCHEMA IF EXISTS {DESTINO} CASCADE")
    con.execute(f"CREATE SCHEMA {DESTINO}")
    for arquivo, nome in marts:
        try:
            con.execute(f"CREATE TABLE {DESTINO}.{nome} AS\n{ler_select(arquivo)}")
        except duckdb.Error as e:
            raise ErroMarts(f"Falha em {arquivo.name}: {e}") from e
        if contar(con, f"{DESTINO}.{nome}") == 0:
            raise ErroMarts(f"{DESTINO}.{nome} ({arquivo.name}) voltou com zero linhas")


def conferir_tabelas(con: duckdb.DuckDBPyConnection, marts: list[tuple[Path, str]]) -> None:
    existentes = {
        linha[0]
        for linha in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
            [DESTINO],
        ).fetchall()
    }
    esperadas = {nome for _, nome in marts}
    if existentes != esperadas:
        raise ErroMarts(
            f"Tabelas em {DESTINO} não batem com os arquivos. "
            f"Faltando: {sorted(esperadas - existentes)}. Sobrando: {sorted(existentes - esperadas)}"
        )


def main(arquivo_banco: Path = ARQUIVO_BANCO, pasta_sql: Path = PASTA_SQL) -> None:
    arquivo_banco = Path(arquivo_banco)
    pasta_sql = Path(pasta_sql)

    marts = listar_marts(pasta_sql)

    if not arquivo_banco.is_file():
        falhar(
            f"Banco não encontrado: {arquivo_banco}",
            "Rode primeiro: uv run python ingestao.py e uv run python refined.py",
        )

    try:
        con = duckdb.connect(str(arquivo_banco))
    except duckdb.Error as e:
        falhar(f"Não foi possível abrir {arquivo_banco} (outro processo com o arquivo aberto?):", str(e))

    try:
        faltando = tabelas_refined_faltando(con)
        if faltando:
            falhar(
                f"Tabelas ausentes em {arquivo_banco}: {', '.join(faltando)}",
                "Rode primeiro: uv run python refined.py",
            )

        con.begin()
        try:
            criar_marts(con, marts)
            conferir_tabelas(con, marts)
            con.commit()
        except ErroMarts as e:
            con.rollback()
            falhar(str(e), f"Nada foi alterado em {DESTINO} (ROLLBACK).")
        except duckdb.Error as e:
            con.rollback()
            falhar(f"Erro do DuckDB: {e}", f"Nada foi alterado em {DESTINO} (ROLLBACK).")

        largura = max(len(f"{DESTINO}.{nome}") for _, nome in marts)
        total = 0
        for _, nome in marts:
            n = contar(con, f"{DESTINO}.{nome}")
            total += n
            print(f"✓ {(DESTINO + '.' + nome).ljust(largura)}  {formatar_milhar(n):>7} linhas")
        print(f"{len(marts)} marts, {formatar_milhar(total)} linhas")
    finally:
        con.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
