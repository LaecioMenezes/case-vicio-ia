"""Etapa 6: quanto o Jev acerta, sem gabarito, por triangulação entre testemunhas independentes.

Três "testemunhas" dizem o conceito (tema N1) de cada questão:
- J: o Jev (s05);
- L: a evidência lexical do tesauro: lei/artigo citado e termos de entrada (s04);
- O: o assunto que o site de origem deu à questão, cruzado com a árvore (s04).
Nenhuma é gabarito, e elas erram por motivos diferentes. Se os erros são independentes, a frequência
com que cada par concorda revela a taxa de acerto de cada uma (Dawid & Skene, 1979; o "método das três
testemunhas"): concordar por acaso no MESMO conceito errado é raro (κ = chance de dois erros caírem no
mesmo conceito; o padrão é 0,10, conservador para 89 conceitos com erros concentrados em vizinhos).

  P(J=L) = aJ·aL + (1−aJ)(1−aL)·κ,   P(J=O) = aJ·aO + ...,   P(L=O) = aL·aO + ...  ->  aJ, aL, aO

Com aL e aO conhecidos, a mesma conta mede o Jev por faixa de probabilidade (calibração), e cada
testemunha que concorda ou discorda numa questão atualiza a confiança daquela questão (Bayes).

Saída: data/interim/triangulacao.json
"""
import math

import numpy as np

from common import INTERIM, config, read_jsonl, write_json
from s05_jev import NENHUM

FAIXAS = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 0.95), (0.95, 1.01)]


def igual(a, b):
    return a == b or {a, b} == {NENHUM, "FORA"}


def votos(jevs, evs, finais=None, revisor=None):
    """Uma linha por questão: J (conceito ou NENHUM), p, estabilidade, L e O. Se houver a segunda rodada
    (finalistas, s05c), ela é a decisão final do Jev e é ela que se mede."""
    out = []
    for qid, j in jevs.items():
        e = evs[qid]
        if finais and qid in finais:
            f = finais[qid]
            out.append({"id": qid, "J": f["top"], "p": f["p"][f["top"]], "cons": f["estavel"], "L": e["L"], "O": e["O"]})
        else:
            out.append({"id": qid, "J": j["n1"]["top"][0], "p": j["n1"]["p"][j["n1"]["top"][0]],
                        "cons": j["n1"]["consistente"], "L": e["L"], "O": e["O"]})
        r = (revisor or {}).get(qid)
        out[-1]["R"] = r["tema"] if r else None
        out[-1]["R_conf"] = r["confianca"] if r else None
    return out


def carregar_revisor():
    """Revisor LLM (s05d), se existir e estiver ligado em config revisor_llm.usar."""
    cfg = config().get("revisor_llm", {})
    caminho = INTERIM / "revisores" / (cfg.get("modelo", "").replace("/", "__").replace(":", "_") + ".jsonl")
    if not caminho.exists() or not cfg.get("usar"):
        return None
    return {r["id"]: r for r in read_jsonl(caminho)}


def carregar_finais(para_decidir=True):
    """Segunda rodada (s05c). Só vira a decisão se config politica.segunda_rodada = true; senão entra
    apenas na comparação (foi testada e não melhorou o resultado)."""
    caminho = INTERIM / "jev_final.jsonl"
    if not caminho.exists() or (para_decidir and not config()["politica"].get("segunda_rodada")):
        return None
    return {r["id"]: r for r in read_jsonl(caminho)}


def taxas(pJL, pJO, pLO, kappa):
    """Resolve as três equações de concordância (ponto fixo a partir da solução com κ=0)."""
    aJ = aL = aO = 0.7
    for _ in range(200):
        qJL = max(pJL - (1 - aJ) * (1 - aL) * kappa, 1e-6)
        qJO = max(pJO - (1 - aJ) * (1 - aO) * kappa, 1e-6)
        qLO = max(pLO - (1 - aL) * (1 - aO) * kappa, 1e-6)
        aJ = min(0.999, math.sqrt(qJL * qJO / qLO))
        aL = min(0.999, math.sqrt(qJL * qLO / qJO))
        aO = min(0.999, math.sqrt(qJO * qLO / qJL))
    return aJ, aL, aO


def acc_por_concordancia(r, a_w, kappa):
    """Taxa de acerto do Jev num grupo, a partir da concordância r com uma testemunha de acerto a_w."""
    return (r - (1 - a_w) * kappa) / (a_w - (1 - a_w) * kappa)


def pava(valores, pesos):
    """Regressão isotônica (não decrescente) por pool-adjacent-violators."""
    blocos = [[v, w, 1] for v, w in zip(valores, pesos)]
    i = 0
    while i < len(blocos) - 1:
        if blocos[i][0] > blocos[i + 1][0]:
            v = (blocos[i][0] * blocos[i][1] + blocos[i + 1][0] * blocos[i + 1][1]) / (blocos[i][1] + blocos[i + 1][1])
            blocos[i:i + 2] = [[v, blocos[i][1] + blocos[i + 1][1], blocos[i][2] + blocos[i + 1][2]]]
            i = max(i - 1, 0)
        else:
            i += 1
    out = []
    for v, _, n in blocos:
        out += [v] * n
    return out


def estimar(linhas, kappa, rho_L=None, teto=None):
    """Taxas de acerto das três testemunhas e calibração do Jev por faixa. `teto` é a confiança máxima
    de uma questão: o erro que nenhuma testemunha enxerga (convenção da equipe, ruído no gabarito)."""
    tri = config()["triangulacao"]
    teto = tri["teto"] if teto is None else teto
    trio = [x for x in linhas if x["L"] and x["O"]]
    pJL = np.mean([igual(x["J"], x["L"]) for x in trio])
    pJO = np.mean([igual(x["J"], x["O"]) for x in trio])
    pLO = np.mean([igual(x["L"], x["O"]) for x in trio])
    aJ, aL, aO = taxas(pJL, pJO, pLO, kappa)

    faixas = []
    for lo, hi in FAIXAS:
        g = [x for x in linhas if x["cons"] and lo <= x["p"] < hi and x["J"] != NENHUM]
        est, peso = [], []
        for w, a in (("O", aO), ("L", aL)):
            gw = [x for x in g if x[w] and x[w] != "FORA"]
            if gw:
                r = np.mean([igual(x["J"], x[w]) for x in gw])
                est.append(acc_por_concordancia(r, a, kappa))
                peso.append(len(gw) * a ** 2)                  # testemunha mais confiável pesa mais
        acc = float(np.clip(np.average(est, weights=peso), 0.01, teto)) if est else None
        faixas.append({"lo": lo, "hi": hi, "n": len(g), "acc": acc, "peso": float(sum(peso))})
    validas = [f for f in faixas if f["acc"] is not None]
    for f, v in zip(validas, pava([f["acc"] for f in validas], [max(f["peso"], 1e-6) for f in validas])):
        f["acc_iso"] = v
    out = {"kappa": kappa, "rho_L": tri["rho_L"] if rho_L is None else rho_L, "teto": teto,
           "n_trio": len(trio), "pJL": pJL, "pJO": pJO, "pLO": pLO, "aJ": aJ, "aL": aL, "aO": aO, "faixas": faixas}
    if any(x.get("R") for x in linhas):
        # O revisor LLM e o Jev erram juntos com frequência (leem o mesmo texto), então o voto dele NÃO entra como
        # testemunha independente: medimos direto, pela régua de fora, quanto acerta cada caso.
        out["faixas_por_grupo"] = {
            "concorda": _faixas(linhas, lambda x: x["R"] == x["J"], aO, aL, kappa, teto),
            "discorda": _faixas(linhas, lambda x: x["R"] != x["J"], aO, aL, kappa, teto, faixas_=[(0.0, 0.85), (0.85, 1.01)])}
        out["acc_revisor_discorda"] = {}
        for nivel in ("alta", "media"):
            g = [x for x in linhas if x["R"] and x["R"] != x["J"] and x["R_conf"] == nivel]
            out["acc_revisor_discorda"][nivel] = _acc_grupo(g, "R", aO, aL, kappa, teto)
    return out


def _acc_grupo(g, quem, aO, aL, kappa, teto):
    """Acerto de quem (J ou R) num grupo de questões, medido pela concordância com O e L."""
    est, peso = [], []
    for w, a in (("O", aO), ("L", aL)):
        gw = [x for x in g if x[w] and x[w] != "FORA" and x[quem] != NENHUM]
        if gw:
            r = np.mean([igual(x[quem], x[w]) for x in gw])
            est.append(acc_por_concordancia(r, a, kappa))
            peso.append(len(gw) * a ** 2)
    return float(np.clip(np.average(est, weights=peso), 0.01, teto)) if est else None


def _faixas(linhas, filtro, aO, aL, kappa, teto, faixas_=None):
    out = []
    for lo, hi in faixas_ or FAIXAS:
        g = [x for x in linhas if filtro(x) and x["cons"] and lo <= x["p"] < hi and x["J"] != NENHUM]
        out.append({"lo": lo, "hi": hi, "n": len(g), "acc": _acc_grupo(g, "J", aO, aL, kappa, teto),
                    "peso": float(len(g))})
    validas = [f for f in out if f["acc"] is not None]
    for f, v in zip(validas, pava([f["acc"] for f in validas], [max(f["peso"], 1e-6) for f in validas])):
        f["acc_iso"] = v
    return out


def acc_jev(params, p, grupo=None):
    """Taxa de acerto calibrada do Jev para uma probabilidade p (faixa correspondente); com revisor LLM,
    as faixas são as do grupo (revisor concorda ou discorda do Jev)."""
    faixas = (params.get("faixas_por_grupo") or {}).get(grupo) or params["faixas"]
    for f in faixas:
        if f["lo"] <= p < f["hi"] and f.get("acc_iso") is not None:
            return f["acc_iso"]
    validas = [f for f in faixas if f.get("acc_iso") is not None] or \
              [f for f in params["faixas"] if f.get("acc_iso") is not None]
    return min(validas, key=lambda f: abs((f["lo"] + f["hi"]) / 2 - p))["acc_iso"]


def posterior_prior(params, prior, J, L, O):
    """Atualiza uma taxa de acerto a priori com os votos do tesauro (amortecido) e do assunto de origem."""
    odds = prior / max(1 - prior, 1e-6)
    k = params["kappa"]
    for w, a, rho in ((L, params["aL"], params["rho_L"]), (O, params["aO"], 1.0)):
        if not w:
            continue
        if igual(J, w):
            odds *= (a / ((1 - a) * k)) ** rho
        else:
            odds *= ((1 - a) / (1 - (1 - a) * k)) ** rho
    return min(odds / (1 + odds), params["teto"])


def posterior(params, p, J, L, O, grupo=None):
    """Confiança de que o conceito do Jev está certo, dada a faixa dele e o voto das testemunhas.
    O voto do tesauro é amortecido (expoente ρ < 1): o Jev e o tesauro leem o mesmo texto, então não são
    totalmente independentes. O assunto de origem vem de fora do texto e conta inteiro. Há um teto."""
    prior = acc_jev(params, p, grupo)
    odds = prior / max(1 - prior, 1e-6)
    k = params["kappa"]
    for w, a, rho in ((L, params["aL"], params["rho_L"]), (O, params["aO"], 1.0)):
        if not w:
            continue
        if igual(J, w):
            odds *= (a / ((1 - a) * k)) ** rho
        else:
            odds *= ((1 - a) / (1 - (1 - a) * k)) ** rho
    return min(odds / (1 + odds), params["teto"])


def comparar(params, jevs, evs, finais=None):
    """O tesauro faz diferença? Taxa de acerto de cada abordagem medida pela mesma régua independente: a
    concordância com o assunto de origem (O), corrigida pela taxa de acerto de O. "Nenhum destes temas" não
    conta como voto (a mesma regra do comparar_modelos.py): mede o acerto quando a abordagem indica um tema."""
    import thesaurus
    from common import ROOT
    aO, k = params["aO"], params["kappa"]

    def medir(votos_):
        votos_ = {q: v for q, v in votos_.items() if v and v != NENHUM}
        pares = [(v, evs[q]["O"]) for q, v in votos_.items() if evs[q]["O"] and evs[q]["O"] != "FORA"]
        if not pares:
            return None
        r = float(np.mean([igual(v, o) for v, o in pares]))
        return {"vota_em": len(votos_), "n_regua": len(pares),
                "acerto": float(np.clip(acc_por_concordancia(r, aO, k), 0, 1))}

    out = {"tesauro_sozinho": medir({q: e["L"] for q, e in evs.items()}),
           "tesauro_sozinho_com_citacao_legal": medir({q: e["L"] if e.get("L_ref") else None for q, e in evs.items()}),
           "jev_com_tesauro": medir({q: j["n1"]["top"][0] for q, j in jevs.items()})}
    out["jev_com_tesauro"]["estavel"] = float(np.mean([j["n1"]["consistente"] for j in jevs.values()]))
    if finais:
        out["jev_final"] = medir({q: f["top"] for q, f in finais.items()})
        out["jev_final"]["estavel"] = float(np.mean([f["estavel"] for f in finais.values()]))
    rev_path = INTERIM / "revisores" / (config().get("revisor_llm", {}).get("modelo", "").replace("/", "__") + ".jsonl")
    if rev_path.exists():
        rev = {r["id"]: r for r in read_jsonl(rev_path)}
        out["revisor_llm"] = medir({q: r["tema"] for q, r in rev.items()})
        out["jev_e_revisor_concordam"] = medir({q: (j["n1"]["top"][0] if rev[q]["tema"] == j["n1"]["top"][0] else None)
                                                for q, j in jevs.items() if q in rev})
    caminho = INTERIM / "jev_sem_tesauro.jsonl"
    if caminho.exists():
        linhas = read_jsonl(caminho)
        sem = {r["id"]: thesaurus.conceito_de(r["no"]) if r["no"] else NENHUM for r in linhas}
        out["jev_sem_tesauro"] = medir(sem)
        out["jev_sem_tesauro"]["estavel"] = float(np.mean([r["consistente"] for r in linhas]))
    return out


def main():
    jevs = {r["id"]: r for r in read_jsonl(INTERIM / "jev.jsonl")}
    evs = {r["id"]: r for r in read_jsonl(INTERIM / "evidencias.jsonl")}
    kappa = config()["triangulacao"]["kappa"]
    finais = carregar_finais()
    params = estimar(votos(jevs, evs, finais, carregar_revisor()), kappa)
    params["comparacao"] = comparar(params, jevs, evs, carregar_finais(para_decidir=False))
    params["mede"] = "segunda rodada (finalistas)" if finais else "primeira rodada"
    write_json(INTERIM / "triangulacao.json", params)
    for nome, c in params["comparacao"].items():
        if c:
            print(f"  {nome}: vota em {c['vota_em']} questões | acerto estimado {c['acerto']:.1%} (régua: {c['n_regua']})")
    print(f"trio (L e O votam): {params['n_trio']} questões | concordância J=L {params['pJL']:.2f}, "
          f"J=O {params['pJO']:.2f}, L=O {params['pLO']:.2f} (κ={kappa})")
    print(f"taxa de acerto estimada: Jev {params['aJ']:.1%} | tesauro (lexical) {params['aL']:.1%} | "
          f"assunto de origem {params['aO']:.1%}")
    for f in params["faixas"]:
        print(f"  Jev com p em [{f['lo']:.2f}, {f['hi']:.2f}): n={f['n']:3d} | acerto estimado "
              f"{(f['acc'] or 0):.1%} | após isotônica {(f.get('acc_iso') or 0):.1%}")


if __name__ == "__main__":
    main()
