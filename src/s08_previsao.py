"""Etapa 8 (sem rede): previsao.txt para as questões fora da folha-verdade.

- Precisão prevista: média das confianças calibradas das publicadas (fora da folha).
- Intervalo: bootstrap que reamostra as questões da folha (pela questão, não pela repetição), reajusta o
  calibrador, refaz a escolha do limiar e sorteia o resultado de cada publicada (Bernoulli da confiança). Assim o
  intervalo junta a incerteza da calibração (só 100 rótulos) e o acaso das questões publicadas.
- Conferência direta: a precisão medida na validação cruzada da folha, com o mesmo calibrador e o mesmo limiar.
- Cobertura: exata nas 559; o intervalo binomial cobre o caso de a avaliação usar só parte delas.
"""
import numpy as np

import s07_decisao as s07
from common import INTERIM, ROOT, config, read_json

REAMOSTRAS = 500


def main():
    pol = config()["politica"]
    props, tau = s07.decidir()
    aval = [p for p in props if not p["na_folha"]]
    pub = [p for p in aval if p["decisao"] == "publicar"]
    cobertura = len(pub) / len(aval)
    prev = float(np.mean([p["conf"] for p in pub])) if pub else 0.0

    oof = read_json(INTERIM / "oof.json")["oof"]
    X = np.array([o["p"] for o in oof])
    y = np.array([o["certo"] for o in oof])
    cal, _ = s07.calibrador()
    conf_oof = cal.predict(X)
    sel = conf_oof >= tau
    medida = float(y[sel].mean()) if sel.any() else float("nan")

    r = np.load(INTERIM / "ranking.npz")
    ordem = np.argsort(-r["p"], axis=1)
    p1 = r["p"][np.arange(len(ordem)), ordem[:, 0]]
    Xall = p1
    elegivel = np.array([p["decisao"] != "fora" and not p["na_folha"] for p in props])

    rng = np.random.default_rng(2026)
    ids = np.array([o["id"] for o in oof])
    unicos = np.unique(ids)
    precisoes = []
    for _ in range(REAMOSTRAS):
        amostra = rng.choice(unicos, len(unicos), replace=True)
        idx = np.concatenate([np.where(ids == u)[0] for u in amostra])
        if len(set(y[idx])) < 2:
            continue
        c = s07.ajustar(X[idx], y[idx]).predict(Xall)
        t = s07.escolher_tau(list(c[elegivel]), pol["alvo_precisao"], pol["piso_confianca"])
        escolhidas = c[elegivel & (c >= t)]
        if len(escolhidas):
            precisoes.append(rng.binomial(1, np.clip(escolhidas, 0, 1)).mean())
    p_lo, p_hi = np.percentile(precisoes, [5, 95]) if precisoes else (prev, prev)
    n_sub = 240
    delta = 1.645 * np.sqrt(cobertura * (1 - cobertura) / n_sub)

    texto = f"""precisao_prevista: {prev:.2f}
precisao_intervalo: {p_lo:.2f}-{p_hi:.2f}
cobertura_prevista: {cobertura:.2f}
cobertura_intervalo: {max(0, cobertura - delta):.2f}-{min(1, cobertura + delta):.2f}

Como cheguei nesses números (só as {len(aval)} questões fora da folha-verdade)

Cobertura. O sistema publica {len(pub)} das {len(aval)} ({cobertura:.1%}); {sum(p['decisao'] == 'revisar' for p in aval)} vão para
revisar com a sugestão de tema e {sum(p['decisao'] == 'fora' for p in aval)} ficam fora. Nas {len(aval)}, a cobertura é
exatamente essa; o intervalo (90%, binomial) cobre o caso de a avaliação usar só parte delas (~{n_sub}).

Precisão. A decisão não chama nenhum modelo: um ranqueador (regressão logística sobre features do tesauro, dos
embeddings guardados e dos 100 rótulos) escolhe o tema, e uma calibração isotônica transforma a probabilidade do 1º tema na chance de o tema
estar certo pela régua do case. O calibrador foi ajustado em previsões fora da dobra (validação cruzada 10 × 5 na
folha-verdade), ou seja, em questões que o modelo não tinha visto.
- Precisão esperada das publicadas: {prev:.1%} (média das confianças; no cabeçalho, duas casas, como pede o LEIA-ME).
  Publicamos o maior conjunto com média ≥ {pol['alvo_precisao']:.0%} (a régua do case) e piso de
  {pol['piso_confianca']:.2f} por questão; limiar {tau:.2f}.
- Conferência direta na folha: com o mesmo limiar, a validação cruzada publicaria {int(sel.sum())} de {len(sel)}
  previsões fora da dobra, com {medida:.1%} de acerto.
- Intervalo de 90%: {len(precisoes)} reamostras das 100 questões da folha, reajustando o calibrador e o limiar e
  sorteando o resultado de cada publicada: {p_lo:.1%}–{p_hi:.1%}. É largo porque a folha tem só 100 rótulos.

Riscos: a folha tem 8% de questões que a equipe considera fora da taxonomia mesmo parecendo classificáveis; se a
proporção nas avaliadas for maior, a precisão cai. As questões novas (Q0360 em diante) podem diferir das antigas,
e a folha só tem questões antigas.
"""
    (ROOT / "previsao.txt").write_text(texto, encoding="utf-8")
    print(texto)


if __name__ == "__main__":
    main()
