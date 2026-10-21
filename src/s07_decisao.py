"""Etapa 7 (decisão, sem rede): confiança calibrada, regras de "fora" e a política publicar / revisar / fora.

1. Confiança: regressão isotônica que transforma a probabilidade do 1º conceito (softmax do ranqueador) na
   chance de o tema estar certo pela régua do case, com teto de 0,98 (100 rótulos não autorizam certeza total).
   É ajustada nas previsões fora da dobra da folha-verdade (s06), então mede o sistema em questões que ele não viu.
   Testada e descartada: logística com margem e confiança absoluta (suavizava demais e nunca passava de 0,9).
2. Fora (só por regra forte, porque publicar uma questão fora é erro):
   - disciplina de origem militar: a árvore não tem tema de Direito Penal Militar;
   - a questão cita uma lei que não ancora nenhum tema (thesaurus.leis_sem_tema) e a confiança é baixa.
3. Publicar: o maior conjunto cuja confiança média (precisão esperada) fica ≥ 95%, a régua do case, sem folga, e
   nenhuma questão abaixo do piso de 0,85. Publica no nó-base do conceito (convenção da equipe: tema original).
4. O resto vai para revisar, com a sugestão de tema, a 2ª opção e o motivo.
Saídas: publicacao.csv (raiz) e out/decisoes_detalhadas.csv
"""
import csv

import numpy as np
from sklearn.isotonic import IsotonicRegression

import thesaurus
from common import INTERIM, OUT, ROOT, Tree, config, read_json, read_jsonl
from verdade import carregar_folha

PISO_FORA_LEI = 0.5


TETO = 0.98


def ajustar(p, certo):
    return IsotonicRegression(y_min=0.0, y_max=TETO, out_of_bounds="clip").fit(p, certo)


def calibrador():
    oof = read_json(INTERIM / "oof.json")["oof"]
    return ajustar([o["p"] for o in oof], [o["certo"] for o in oof]), oof


def escolher_tau(confs, alvo, piso):
    """Menor limiar (≥ piso) cuja confiança média dos selecionados fica ≥ alvo."""
    for tau in sorted({c for c in confs if c >= piso}):
        sel = [c for c in confs if c >= tau]
        if np.mean(sel) >= alvo:
            return float(tau)
    return 1.01


def decidir(alvo=None, piso=None):
    pol = config()["politica"]
    alvo, piso = alvo or pol["alvo_precisao"], piso or pol["piso_confianca"]
    tree, folha = Tree(), carregar_folha()
    r = np.load(INTERIM / "ranking.npz")
    qs = {q["id"]: q for q in read_jsonl(INTERIM / "questoes_limpas.jsonl")}
    chaves, bases = list(r["chaves"]), list(r["bases"])
    cal, _ = calibrador()
    ordem = np.argsort(-r["p"], axis=1)
    p1 = r["p"][np.arange(len(ordem)), ordem[:, 0]]
    p2 = r["p"][np.arange(len(ordem)), ordem[:, 1]]
    conf = cal.predict(p1)

    props = []
    for i, qid in enumerate(r["ids"]):
        q, top, seg = qs[qid], int(ordem[i, 0]), int(ordem[i, 1])
        prop = {"id": qid, "central": bases[top], "conceito": chaves[top], "conf": float(conf[i]),
                "p_top": float(p1[i]), "segundo": chaves[seg], "p_segundo": float(p2[i]), "decisao": None,
                "extras": [bases[j] for j in ordem[i, 1:3] if r["p"][i, j] >= 0.25], "na_folha": qid in folha}
        leis = thesaurus.leis_sem_tema(q["texto"])
        if "militar" in (q["disciplina_origem"] or "").lower():
            prop.update(decisao="fora", central="", extras=[], motivo=f"Direito Penal Militar ({q['disciplina_origem']}): "
                        "a árvore não tem tema militar; sugestão: criar o ramo")
        elif leis and conf[i] < PISO_FORA_LEI:
            prop.update(decisao="fora", central="", extras=[], motivo=f"cita {', '.join(leis)}, que não tem tema na "
                        "árvore, e nenhum tema tem confiança suficiente; sugestão: criar o tema")
        props.append(prop)

    candidatas = [p["conf"] for p in props if not p["decisao"]]
    tau = escolher_tau(candidatas, alvo, piso)
    for p in props:
        if p["decisao"]:
            continue
        if p["conf"] >= tau:
            p.update(decisao="publicar", motivo="")
        else:
            p.update(decisao="revisar", motivo=f"confiança {p['conf']:.2f} abaixo do limiar {tau:.2f}; 2ª opção: "
                     f"{p['segundo']} ({p['p_segundo']:.0%})"[:180])
    return props, tau


def main():
    props, tau = decidir()
    tree = Tree()
    with open(ROOT / "publicacao.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "decisao", "tema_central_id", "extras_ids", "confianca", "motivo"])
        for p in sorted(props, key=lambda x: x["id"]):
            w.writerow([p["id"], p["decisao"], p["central"], ";".join(p["extras"]), f"{p['conf']:.2f}", p["motivo"]])
    campos = ["id", "decisao", "central", "conceito", "conf", "p_top", "segundo", "p_segundo", "extras", "na_folha",
              "motivo"]
    with open(OUT / "decisoes_detalhadas.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos + ["caminho"], extrasaction="ignore")
        w.writeheader()
        for p in sorted(props, key=lambda x: x["id"]):
            w.writerow({**p, "extras": ";".join(p["extras"]), "caminho": tree[p["central"]]["caminho"] if p["central"] else ""})
    aval = [p for p in props if not p["na_folha"]]
    pub = [p for p in aval if p["decisao"] == "publicar"]
    print(f"τ={tau:.3f} | fora da folha ({len(aval)}): publicar {len(pub)} ({len(pub) / len(aval):.1%}) | revisar "
          f"{sum(p['decisao'] == 'revisar' for p in aval)} | fora {sum(p['decisao'] == 'fora' for p in aval)} | "
          f"precisão esperada {np.mean([p['conf'] for p in pub]) if pub else 0:.1%}")


if __name__ == "__main__":
    main()
