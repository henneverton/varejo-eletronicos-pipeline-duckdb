"""Ingestão da camada raw no DuckDB (spec 001).

Executar com:  uv run python ingestao.py

Traz os seis CSVs de RAW/ para o schema `raw` de data/projeto.duckdb,
exatamente como chegaram. Limpeza, tipagem e modelagem são da etapa 2.

Regras e por que existem
------------------------
1. Nomes: schema `raw`, tabelas em inglês e minúsculas, iguais aos arquivos.
   Motivo: é o vocabulário do Data_Dictionary e o que será digitado de
   memória nos JOINs; uma regra única evita lembrar exceções.
2. Proibições: nenhuma conversão de tipo, nenhuma linha descartada ou
   deduplicada, nenhum nome de coluna alterado, nenhum valor corrigido.
   Motivo: a fronteira entre "o dado que chegou" e "o dado que decidi"
   precisa existir, e é a passagem de raw para a etapa 2.
3. Reexecução: CREATE OR REPLACE TABLE, nunca acrescenta.
   Motivo: permite errar e rodar de novo sem medo.
4. Leitura: encoding declarado por arquivo, nunca adivinhado. Só célula
   vazia vira nulo (keep_default_na=False + na_values=[""]); NA, null e N/A
   continuam texto. Não usar na_filter=False: o vazio chegaria como ''.
   Motivo: a lista padrão do pandas alteraria valores reais sem avisar.
5. Tipagem: tudo texto (dtype=str). Motivo: "$6.62 ", códigos com zero à
   esquerda (0101) e datas M/D/AAAA seriam destruídos ou ambíguos na
   inferência; a conversão é decisão registrada da etapa 2.
6. Saída: uma linha por tabela, contagem lida do banco, milhar com ponto,
   linha de total, stdout em utf-8. Motivo: é o único instrumento de
   conferência da etapa e precisa refletir o que foi gravado.
7. Erro: antes de qualquer efeito no disco, verifica os seis arquivos;
   faltando algum, lista, informa a pasta e sai com código 1, sem criar
   data/ nem o banco. Motivo: ingerir parte em silêncio gera resultado
   errado que parece certo.
8. Caminhos: calculados a partir deste arquivo, nunca do diretório
   corrente; main() recebe os caminhos como parâmetros (testes usam
   pastas temporárias). Ordem: verificar -> criar data/ -> conectar ->
   carregar -> fechar. Importar o módulo não toca o disco. Motivo: rodar de
   outra pasta não pode criar um banco vazio no lugar errado, e o .duckdb
   aceita um único processo escrevendo.
"""

import sys
from pathlib import Path

import duckdb
import pandas as pd

RAIZ = Path(__file__).resolve().parent
PASTA_RAW = RAIZ / "RAW"
ARQUIVO_BANCO = RAIZ / "data" / "projeto.duckdb"

SCHEMA = "raw"

# (arquivo, tabela, encoding), na ordem em que a saída é impressa.
TABELAS = [
    ("Sales.csv", "sales", "utf-8"),
    ("Customers.csv", "customers", "windows-1252"),
    ("Products.csv", "products", "utf-8"),
    ("Stores.csv", "stores", "utf-8"),
    ("Exchange_Rates.csv", "exchange_rates", "utf-8"),
    ("Data_Dictionary.csv", "data_dictionary", "utf-8"),
]


def formatar_milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def arquivos_faltando(pasta_raw: Path) -> list[str]:
    return [arquivo for arquivo, _, _ in TABELAS if not (pasta_raw / arquivo).is_file()]


def carregar_tabela(
    con: duckdb.DuckDBPyConnection, pasta_raw: Path, arquivo: str, tabela: str, encoding: str
) -> int:
    df = pd.read_csv(
        pasta_raw / arquivo,
        encoding=encoding,
        dtype=str,
        keep_default_na=False,
        na_values=[""],
    )
    con.register("df_carga", df)
    try:
        con.execute(f"CREATE OR REPLACE TABLE {SCHEMA}.{tabela} AS SELECT * FROM df_carga")
    finally:
        # não deixa view temporária para trás
        con.unregister("df_carga")
    # fetchall (não fetchone): fetchone deixa o resultado aberto e a próxima
    # tabela falha com "unfinished result" no DuckDB 2.x
    return con.execute(f"SELECT count(*) FROM {SCHEMA}.{tabela}").fetchall()[0][0]


def main(pasta_raw: Path = PASTA_RAW, arquivo_banco: Path = ARQUIVO_BANCO) -> None:
    pasta_raw = Path(pasta_raw)
    arquivo_banco = Path(arquivo_banco)

    faltando = arquivos_faltando(pasta_raw)
    if faltando:
        print(f"Arquivos ausentes em {pasta_raw}:", file=sys.stderr)
        for arquivo in faltando:
            print(f"  - {arquivo}", file=sys.stderr)
        print("Nada foi ingerido.", file=sys.stderr)
        sys.exit(1)

    arquivo_banco.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(arquivo_banco))
    try:
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        total = 0
        for arquivo, tabela, encoding in TABELAS:
            n = carregar_tabela(con, pasta_raw, arquivo, tabela, encoding)
            total += n
            print(f"{SCHEMA}.{tabela}: {formatar_milhar(n)} linhas")
        print(f"Total: {formatar_milhar(total)} registros")
    finally:
        con.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
