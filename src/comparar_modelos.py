"""Experimento: qual modelo de revisor tem o melhor custo-benefício? (não faz parte do pipeline)

Para cada modelo que revisou as 359 questões (data/interim/revisores/*.jsonl, gerados pelo s05d), mede com a
mesma régua independente (o assunto de origem, corrigido pela taxa de acerto dele, estimada no s06):
- custo real por questão e por 50 mil questões (o volume semanal do case);
- acerto sozinho, acerto quando concorda com o Jev e quando discorda;
- o efeito na decisão: quantas questões passam a ser publicáveis com a mesma precisão prevista (≥ 96%).

Saída: out/comparacao_modelos.csv
"""
import csv
from pathlib import Path

import numpy as np

from common import INTERIM, OUT, read_json, read_jsonl
from s05_jev import NENHUM
from s06_triangulacao import acc_por_concordancia, estimar, igual, votos
from s07_politica import carregar, resumo, rodar

DOLAR = 5.20          # R$ por US$, fim de setembro de 2026
SEMANA = 50_000


def main():
    dados = carregar()
    base = read_json(INTERIM / "triangulacao.json")
    aO, k = base["aO"], base["kappa"]
    jev = {q: j["n1"]["top"][0] for q, j in dados["jev"].items()}
    O = {q: e["O"] for q, e in dados["ev"].items()}
    props, _ = rodar({**dados, "rev": None}, "conservador")
    so_jev = resumo(props)

    def acerto(votos_):
        pares = [(v, O[q]) for q, v in votos_.items() if v and v != NENHUM and O[q] and O[q] != "FORA"]
        if not pares:
            return None, 0
        r = np.mean([igual(v, o) for v, o in pares])
        return float(np.clip(acc_por_concordancia(r, aO, k), 0, 1)), len(pares)

    linhas = [{"modelo": "só Jev (sem revisor)", "custo_q": 0, "acerto": acerto(jev)[0], "concorda": "",
               "acerto_concorda": "", "acerto_discorda": "", "publicadas": so_jev["publicar"],
               "precisao_prevista": so_jev["precisao_esperada"]}]
    for arq in sorted((INTERIM / "revisores").glob("*.jsonl")):
        rev = {r["id"]: r for r in read_jsonl(arq)}
        R = {q: r["tema"] for q, r in rev.items()}
        custo_q = float(np.mean([r.get("custo") or 0 for r in rev.values()]))
        concorda = {q for q in R if R[q] == jev[q]}
        params = estimar(votos(dados["jev"], dados["ev"], None, rev), k)
        props, _ = rodar({**dados, "rev": rev, "params": {**dados["params"], **{x: params[x] for x in
                                                         ("faixas_por_grupo", "acc_revisor_discorda")}}}, "conservador")
        r = resumo(props)
        linhas.append({"modelo": arq.stem.replace("__", "/"), "custo_q": custo_q, "acerto": acerto(R)[0],
                       "concorda": len(concorda) / len(R),
                       "acerto_concorda": acerto({q: R[q] for q in concorda})[0],
                       "acerto_discorda": acerto({q: R[q] for q in R if q not in concorda})[0],
                       "publicadas": r["publicar"], "precisao_prevista": r["precisao_esperada"]})

    with open(OUT / "comparacao_modelos.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]) + ["custo_semana_usd", "custo_semana_brl"])
        w.writeheader()
        for l in linhas:
            w.writerow({**l, "custo_semana_usd": round(l["custo_q"] * SEMANA, 2),
                        "custo_semana_brl": round(l["custo_q"] * SEMANA * DOLAR, 2)})
    print(f"{'modelo':34s} {'US$/questão':>11s} {'R$/semana':>10s} {'acerto':>7s} {'concorda c/ Jev':>15s} "
          f"{'acerto se concorda':>18s} {'acerto se discorda':>18s} {'publicadas':>10s} {'prec.prev.':>10s}")
    fmt = lambda x: f"{x:.0%}" if isinstance(x, float) else (x or "—")
    for l in linhas:
        print(f"{l['modelo']:34s} {l['custo_q']:>11.5f} {l['custo_q'] * SEMANA * DOLAR:>10.0f} {fmt(l['acerto']):>7s} "
              f"{fmt(l['concorda']):>15s} {fmt(l['acerto_concorda']):>18s} {fmt(l['acerto_discorda']):>18s} "
              f"{l['publicadas']:>10d} {l['precisao_prevista']:>10.1%}")


if __name__ == "__main__":
    main()
