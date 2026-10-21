"""Preparação (antes da decisão; LLM e embeddings permitidos): refaz os artefatos versionados.

    python src/preparar.py                    usa o cache (cache/llm, cache/emb): sem custo se nada mudou
    python src/preparar.py --chave sk-or-...  roda sem o cache: o Luna propõe o tesauro de novo e os embeddings são
                                              refeitos (~US$ 0,30, ~10 min). O resultado pode variar um pouco.

Etapas: limpeza e árvore (s01, s02), tesauro curado (s03), proposta do Luna revisada (prep_tesauro), tesauro com o
enriquecimento (s03 de novo) e embeddings (prep_embeddings). Depois, rode src/run_all.py.
"""
import argparse
import importlib
import os
import sys
import time

ETAPAS = ["s01_preprocess", "s02_taxonomy", "s03_tesauro", "prep_tesauro", "s03_tesauro", "prep_embeddings"]

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--chave", metavar="SK-OR-...", help="chave da OpenRouter: se informada, roda sem o cache")
    args = ap.parse_args()
    import clients
    if args.chave:
        os.environ["OPENROUTER_API_KEY"] = args.chave.strip()
        try:
            saldo = clients.credito_disponivel()
        except RuntimeError as e:
            sys.exit(f"--chave: {e}")
        if saldo is not None and saldo < 0.4:
            sys.exit(f"Crédito disponível na OpenRouter: US$ {saldo:.2f}; a preparação sem cache custa ~US$ 0,30.")
        print(f"Chave informada: preparando sem o cache; respostas novas em {clients.modo_ao_vivo().relative_to(clients.ROOT)}/")
    inicio = time.time()
    for nome in ETAPAS:
        print(f"\n=== {nome} ===", flush=True)
        sys.argv = [nome]
        importlib.import_module(nome).main()
        if nome == "s03_tesauro":                             # o tesauro mudou: limpa o que o thesaurus guardou
            import thesaurus
            for f in (thesaurus.tesauro, thesaurus._indice_lexical, thesaurus._diplomas_com_tema, thesaurus.leis_sem_tema):
                f.cache_clear()
    print(f"\nPreparação: {time.time() - inicio:.0f}s | custo pago agora: US$ "
          f"{clients.USAGE.get('llm_usd_novo', 0) + clients.USAGE.get('emb_usd', 0):.3f}")
