"""Roda o pipeline inteiro, da limpeza à previsão. Com o cache/ do repositório, nenhuma chamada ao
Jev ou ao revisor é refeita (e nenhuma chave é necessária): o publicacao.csv sai idêntico."""
import importlib
import sys
import time

ETAPAS = ["s01_preprocess", "s02_taxonomy", "s03_tesauro", "s03b_jev_tesauro", "s04_evidencias", "s05_jev", "s05b_jev_sem_tesauro", "s05c_jev_finalistas",
          "s05d_revisor_llm", "s06_triangulacao", "s07_politica", "s08_previsao", "validar"]

if __name__ == "__main__":
    from clients import USAGE
    inicio = time.time()
    for nome in ETAPAS:
        print(f"\n=== {nome} ===", flush=True)
        sys.argv = [nome]
        importlib.import_module(nome).main()
    print(f"\nTempo total: {time.time() - inicio:.0f}s | chamadas novas: {USAGE['calls']} | do cache: "
          f"{USAGE['cache_hits']} | tokens do Jev: {USAGE['jev_tokens']:,} | custo das respostas usadas: Jev US$ "
          f"{USAGE['jev_usd']:.3f} + revisor US$ {USAGE.get('llm_usd', 0):.3f} (pago nesta execução: US$ "
          f"{USAGE['jev_usd_novo'] + USAGE.get('llm_usd_novo', 0):.3f})")
