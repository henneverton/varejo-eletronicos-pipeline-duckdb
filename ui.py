"""Interface web do DuckDB (UI oficial da extensão `ui`).

Executar com:  uv run python ui.py
Depois abra http://localhost:4213 no navegador. Encerre com Ctrl+C.

Abre data/projeto.duckdb somente leitura e sobe o servidor da UI do DuckDB.
Não importa o ingestao.py: o único elo entre os dois é o arquivo do banco.

Regras e por que existem
------------------------
1. Banco inexistente: sai com código 1 e manda rodar ingestao.py, sem criar
   um banco vazio. Motivo: conectar a um caminho novo criaria um arquivo
   vazio que parece um banco válido.
2. Somente leitura (ATTACH ... READ_ONLY em uma sessão :memory:). Motivo: a
   camada raw é "o dado que chegou" e não deve ser alterada por engano pelo
   editor SQL; o catálogo memory precisa existir para a UI funcionar.
3. Caminho calculado a partir deste arquivo, nunca do diretório corrente.
4. A primeira execução baixa a extensão `ui` (precisa de internet); depois
   fica em cache.
"""

import sys
import time
import webbrowser
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parent
ARQUIVO_BANCO = RAIZ / "data" / "projeto.duckdb"
URL = "http://localhost:4213"


def main(arquivo_banco: Path = ARQUIVO_BANCO) -> None:
    arquivo_banco = Path(arquivo_banco)
    if not arquivo_banco.is_file():
        print(f"Banco não encontrado: {arquivo_banco}", file=sys.stderr)
        print("Rode primeiro: uv run python ingestao.py", file=sys.stderr)
        sys.exit(1)

    # :memory: + ATTACH (em vez de abrir o arquivo direto): a UI assume o
    # catálogo `memory` e falha com "No catalog + schema named memory.main"
    # quando ele não existe.
    con = duckdb.connect(":memory:")
    try:
        con.execute(f"ATTACH '{arquivo_banco}' AS projeto (READ_ONLY)")
        con.execute("USE projeto")
        con.execute("INSTALL ui")
        con.execute("LOAD ui")
        con.execute("CALL start_ui_server()")
        print(f"DuckDB UI em {URL} (somente leitura). Ctrl+C para encerrar.")
        webbrowser.open(URL)
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nEncerrando.")
    finally:
        try:
            con.execute("CALL stop_ui_server()")
        except duckdb.Error:
            pass
        con.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
