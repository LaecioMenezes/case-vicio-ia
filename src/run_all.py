"""Roda o pipeline inteiro, da limpeza à previsão.

    python src/run_all.py                    usa o cache/ do repositório: nenhuma chamada ao Jev ou ao revisor é
                                             refeita (nenhuma chave é necessária) e o publicacao.csv sai idêntico
    python src/run_all.py --chave sk-or-...  roda sem o cache: chama o Jev e o revisor de novo para todas as
                                             questões (~2.400 chamadas, ~US$ 0,75, ~7 min)"""
import argparse
import importlib
import os
import sys
import time

ETAPAS = ["s01_preprocess", "s02_taxonomy", "s03_tesauro", "s03b_jev_tesauro", "s04_evidencias", "s05_jev", "s05b_jev_sem_tesauro", "s05c_jev_finalistas",
          "s05d_revisor_llm", "s06_triangulacao", "s07_politica", "s08_previsao", "validar"]

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Roda o pipeline inteiro e grava publicacao.csv e previsao.txt. "
                                             "Sem --chave, usa o cache/; com --chave, roda sem o cache.")
    ap.add_argument("--chave", metavar="SK-OR-...",
                    help="chave da OpenRouter: se for informada, o Jev e o revisor são chamados de novo para todas "
                         "as questões, sem reaproveitar o cache/")
    args = ap.parse_args()
    import clients
    from clients import USAGE
    if args.chave:
        os.environ["OPENROUTER_API_KEY"] = args.chave.strip()
        try:
            saldo = clients.credito_disponivel()
        except RuntimeError as e:
            sys.exit(f"--chave: {e}")
        if saldo is not None and saldo < clients.CUSTO_AO_VIVO:
            sys.exit(f"Crédito disponível na OpenRouter: US$ {saldo:.2f}. A rodada sem cache custa ~US$ "
                     f"{clients.CUSTO_AO_VIVO:.2f}; recarregue em https://openrouter.ai/settings/credits")
        pasta = clients.modo_ao_vivo()
        print(f"Chave informada: rodando sem o cache (~US$ {clients.CUSTO_AO_VIVO:.2f}, ~7 min; crédito disponível: "
              f"{'US$ %.2f' % saldo if saldo is not None else 'não consultado'}). Respostas novas em "
              f"{pasta.relative_to(clients.ROOT)}/", flush=True)
    inicio = time.time()
    for nome in ETAPAS:
        print(f"\n=== {nome} ===", flush=True)
        sys.argv = [nome]
        importlib.import_module(nome).main()
    print(f"\nTempo total: {time.time() - inicio:.0f}s | chamadas novas: {USAGE['calls']} | do cache: "
          f"{USAGE['cache_hits']} | tokens do Jev: {USAGE['jev_tokens']:,} | custo das respostas usadas: Jev US$ "
          f"{USAGE['jev_usd']:.3f} + revisor US$ {USAGE.get('llm_usd', 0):.3f} (pago nesta execução: US$ "
          f"{USAGE['jev_usd_novo'] + USAGE.get('llm_usd_novo', 0):.3f})")
