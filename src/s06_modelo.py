"""Etapa 6 (decisão, sem rede): ranqueador treinado na folha-verdade, medido com validação cruzada.

- Rótulo do par (questão, conceito): 1 se publicar no nó-base do conceito conta como certo pela régua do case
  (central, extra ou ramo deles; verdade.acerta). Questões fora da taxonomia só têm pares negativos.
- kNN: maior similaridade da questão com as questões rotuladas (só as da dobra de treino, nunca ela mesma) que têm
  o conceito entre os certos. É o que o sistema "aprende" diretamente dos 100 rótulos.
- Modelo: regressão logística nos pares (features padronizadas). A probabilidade de cada conceito é o softmax dos
  logits entre os 89; p_bin = sigmoide do maior logit (confiança absoluta, sinal de "nenhum tema serve").
- Validação cruzada: 10 dobras × 5 repetições, previsões fora da dobra (OOF) para calibrar a confiança e prever a
  precisão. O modelo final é treinado nas 100 questões e aplicado às 659.
Saídas: artefatos/modelo.joblib, data/interim/ranking.npz, data/interim/oof.json
"""
import json

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import KFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from common import INTERIM, ROOT, Tree, write_json
from s05_features import carregar_embeddings
from verdade import acerta, carregar_folha

REPETICOES, DOBRAS, SEMENTE = 5, 10, 2026


def dados():
    f = np.load(INTERIM / "features.npz")
    emb = carregar_embeddings()
    ids = list(f["ids"])
    pos = {q: i for i, q in enumerate(emb["questoes_ids"])}
    Q = emb["questoes"].astype(np.float32)[[pos[q] for q in ids]]
    tree, folha = Tree(), carregar_folha()
    rot = [ids.index(q) for q in sorted(folha)]
    Y = np.array([[acerta(tree, b, folha[ids[i]]) for b in f["bases"]] for i in rot], dtype=bool)
    fora = np.array([folha[ids[i]]["fora"] for i in rot])
    return f, ids, Q, rot, Y, fora


def knn(Q, consultas, treino, Y_treino, excluir=None):
    """(len(consultas), conceitos): maior cos com uma questão de treino que tem o conceito como certo."""
    S = Q[consultas] @ Q[treino].T
    if excluir is not None:                                   # a própria questão não conta
        S[np.asarray(consultas)[:, None] == np.asarray(treino)[None, :]] = -1
    out = np.zeros((len(consultas), Y_treino.shape[1]), dtype=np.float32)
    for c in range(Y_treino.shape[1]):
        tem = Y_treino[:, c]
        if tem.any():
            out[:, c] = np.clip(S[:, tem].max(1), 0, None)
    return out


def pares(X, K):
    return np.concatenate([X, K[:, :, None]], axis=2).reshape(-1, X.shape[2] + 1)


def treinar(X, K, Y, colunas):
    m = make_pipeline(StandardScaler(), LogisticRegression(C=0.2, max_iter=3000, class_weight="balanced"))
    m.fit(pares(X, K)[:, colunas], Y.reshape(-1))
    return m


def pontuar(m, X, K, colunas):
    z = m.decision_function(pares(X, K)[:, colunas]).reshape(X.shape[0], X.shape[1])
    p = np.exp(z - z.max(1, keepdims=True))
    p /= p.sum(1, keepdims=True)
    return z, p


def validar(f, Q, rot, Y, colunas):
    """Previsões fora da dobra: lista de dicts por (repetição, questão)."""
    X = f["X"]
    oof = []
    for r in range(REPETICOES):
        for tr, te in KFold(DOBRAS, shuffle=True, random_state=SEMENTE + r).split(rot):
            itr, ite = [rot[i] for i in tr], [rot[i] for i in te]
            m = treinar(X[itr], knn(Q, itr, itr, Y[tr], excluir=True), Y[tr], colunas)
            z, p = pontuar(m, X[ite], knn(Q, ite, itr, Y[tr]), colunas)
            for k, i in enumerate(te):
                top = int(p[k].argmax())
                seg = np.sort(p[k])[::-1]
                oof.append({"rep": r, "i": int(i), "top": top, "p": float(seg[0]), "margem": float(seg[0] - seg[1]),
                            "p_bin": float(1 / (1 + np.exp(-z[k, top]))), "certo": bool(Y[i, top])})
    return oof


def resumo(oof, fora):
    certo = np.array([o["certo"] for o in oof])
    p = np.array([o["p"] for o in oof])
    ordem = np.argsort(-p)
    curva = {f"top{int(c * 100)}%": float(certo[ordem[:max(1, int(len(p) * c))]].mean()) for c in (0.2, 0.4, 0.6, 0.8, 1.0)}
    return {"acerto_top1": float(certo.mean()),
            "acerto_top1_sem_fora": float(np.mean([o["certo"] for o in oof if not fora[o["i"]]])), **curva}


def main():
    f, ids, Q, rot, Y, fora = dados()
    nomes = list(f["nomes"]) + ["knn"]
    # escolhido na validação cruzada (grade de C, pesos e conjuntos de features; ver relatório): o embedding da ficha
    # do tesauro e dos exemplos do tesauro. Léxico explícito, origem, disciplina e kNN não melhoraram (sobreajuste).
    principais = ["emb_doc", "z_doc", "emb_ex", "emb_ex3", "z_ex"]
    todas = [nomes.index(n) for n in principais]
    ablacoes = {"sem tesauro (só título do tema)": ["emb_tit"],
                "só embedding do tema (tesauro)": ["emb_doc", "z_doc"],
                "embedding + exemplos do tesauro": ["emb_doc", "z_doc", "emb_ex", "emb_ex3", "z_ex"],
                "+ léxico do tesauro": ["emb_doc", "z_doc", "emb_ex", "emb_ex3", "z_ex", "lex_cur", "lex_llm"],
                "+ origem e disciplina": ["emb_doc", "z_doc", "emb_ex", "emb_ex3", "z_ex", "lex_cur", "lex_llm",
                                          "origem", "origem_eq", "disc", "lixeira"],
                "+ kNN nos rótulos (tudo)": [n for n in nomes if n != "emb_tit"]}
    relato = {}
    for nome, cols in ablacoes.items():
        r = resumo(validar(f, Q, rot, Y, [nomes.index(c) for c in cols]), fora)
        relato[nome] = r
        print(f"{nome:34s} acerto top-1 {r['acerto_top1']:.1%} (sem fora {r['acerto_top1_sem_fora']:.1%}) | "
              f"20% mais confiantes {r['top20%']:.0%} | 40% {r['top40%']:.0%} | 60% {r['top60%']:.0%}")
    oof = validar(f, Q, rot, Y, todas)
    for o in oof:
        o["id"], o["fora"] = ids[rot[o["i"]]], bool(fora[o["i"]])
    final = treinar(f["X"][rot], knn(Q, rot, rot, Y, excluir=True), Y, todas)
    todos = list(range(len(ids)))
    z, p = pontuar(final, f["X"], knn(Q, todos, rot, Y, excluir=True), todas)
    (ROOT / "artefatos").mkdir(exist_ok=True)
    joblib.dump({"modelo": final, "features": principais}, ROOT / "artefatos" / "modelo.joblib")
    np.savez_compressed(INTERIM / "ranking.npz", ids=np.array(ids), z=z, p=p, chaves=f["chaves"], bases=f["bases"])
    write_json(INTERIM / "oof.json", {"oof": oof, "ablacoes": relato, "pesos": dict(zip(
        principais, map(float, final[-1].coef_[0])))})
    print("pesos do modelo final:", {k: round(v, 2) for k, v in zip(principais, final[-1].coef_[0])})


if __name__ == "__main__":
    main()
