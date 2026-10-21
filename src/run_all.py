"""Decisão: regenera publicacao.csv e previsao.txt a partir dos anexos e dos artefatos versionados, SEM chamar
nenhum modelo. A rede fica bloqueada durante a execução: qualquer tentativa de conexão interrompe o processo.

    python src/run_all.py        (~1 min num notebook comum; nenhuma chave necessária)

Os artefatos que esta etapa lê (tesauro enriquecido e embeddings) são gerados por src/preparar.py.
"""
import importlib
import socket
import sys
import time

ETAPAS = ["s01_preprocess", "s02_taxonomy", "s03_tesauro", "s04_evidencias", "s05_features", "s06_modelo",
          "s07_decisao", "s08_previsao", "validar"]


def bloquear_rede():
    def recusa(*args, **kwargs):
        raise RuntimeError("rede bloqueada: a decisão não pode chamar nenhum modelo")
    socket.socket.connect = recusa
    socket.create_connection = recusa


if __name__ == "__main__":
    bloquear_rede()
    inicio = time.time()
    for nome in ETAPAS:
        print(f"\n=== {nome} ===", flush=True)
        sys.argv = [nome]
        importlib.import_module(nome).main()
    print(f"\nTempo total: {time.time() - inicio:.0f}s | sem rede e sem modelo de linguagem na decisão")
