"""Etapa 5 (decisão, sem rede): features de cada par (questão, conceito do tesauro).

As classes são os 89 conceitos de nível 1 do tesauro (gêmeos e "(Parte N)" unidos ao tema-base). Publicar no
nó-base de um conceito conta como certo quando o gabarito é esse tema ou um subtema dele, e é a convenção que a
folha-verdade mostrou (nó antigo/original em 21 de 22 casos). Tudo vem do tesauro e dos embeddings já gravados:

- emb_doc:   maior similaridade entre a questão e o documento de um nó do conceito (tema ou subtema);
- emb_ex:    maior similaridade com os exemplos de questão do conceito (tesauro enriquecido);
- emb_ex3:   média das 3 maiores similaridades com esses exemplos;
- lex_cur:   peso da evidência lexical curada (termos + leis citadas; s04, como na etapa 1);
- lex_llm:   termos e leis propostos por modelo (LLM revisado e Jev da etapa 1) encontrados no texto;
- origem:    similaridade entre o assunto de origem e o documento do conceito;
- origem_eq: o crosswalk do assunto de origem aponta este conceito;
- disc:      a disciplina de origem é a do conceito;
- lixeira:   o tema-base é genérico (lixeira);
- z_doc, z_ex: emb_doc e emb_ex padronizados entre os candidatos da mesma questão (posição relativa);
- emb_tit:   similaridade só com o título do tema (sem o tesauro), usada apenas na ablação.
A similaridade com as questões da folha-verdade (kNN) é calculada na etapa 6, dentro de cada dobra.
Saída: data/interim/features.npz
"""

import numpy as np

import thesaurus
from common import INTERIM, ROOT, read_jsonl
from s02_taxonomy import norm
from s04_evidencias import DISC

FEATURES = ["emb_doc", "emb_ex", "emb_ex3", "lex_cur", "lex_llm", "origem", "origem_eq", "disc", "lixeira",
            "z_doc", "z_ex", "emb_tit"]


def carregar_embeddings():
    e = np.load(ROOT / "artefatos" / "embeddings.npz")
    return {k: e[k] for k in e.files}


def lex_modelo(texto, nos, tes):
    """Termos (LLM revisado e Jev) e leis propostas por LLM que aparecem no texto da questão."""
    alvo, peso = f" {norm(texto)} ", 0.0
    cits = thesaurus.citacoes(texto)
    for no in nos:
        d = tes["nos"][no]
        for t in (d.get("altLabel_llm") or []) + (d.get("altLabel_jev") or []):
            k = norm(t)
            if len(k) >= 4 and f" {k} " in alvo:
                peso += 1.0 if " " in k else 0.5
        for r in d.get("refs_llm") or []:
            dip, fx = thesaurus.diploma_canonico(r["diploma"]), thesaurus.faixas(r.get("artigos"))
            if any(c == dip and (a is None or any(x <= a <= y for x, y in fx)) for c, a in cits) and fx:
                peso += 2.0
    return peso


def main():
    tes, emb = thesaurus.tesauro(), carregar_embeddings()
    conceitos = thesaurus.conceitos_n1()
    chaves = [c["key"] for c in conceitos]
    nos_de = {c["key"]: [n for n, k in tes["no_para_conceito"].items() if k == c["key"]] for c in conceitos}
    qs = read_jsonl(INTERIM / "questoes_limpas.jsonl")
    ev = {r["id"]: r for r in read_jsonl(INTERIM / "evidencias.jsonl")}

    pos_q = {q: i for i, q in enumerate(emb["questoes_ids"])}
    pos_t = {t: i for i, t in enumerate(emb["temas_ids"])}
    pos_o = {o: i for i, o in enumerate(emb["origens_ids"])}
    Q, T, E, O, TT = (emb[k].astype(np.float32) for k in ("questoes", "temas", "exemplos", "origens", "temas_titulo"))
    ex_conc = np.array([tes["no_para_conceito"].get(t) for t in emb["exemplos_tema"]])

    X = np.zeros((len(qs), len(chaves), len(FEATURES)), dtype=np.float32)
    for i, q in enumerate(qs):
        v = Q[pos_q[q["id"]]]
        s_doc, s_ex, s_tit = T @ v, E @ v, TT @ v
        o = O[pos_o[q["assunto_origem"]]] if q["assunto_origem"] in pos_o else None
        disc = DISC.get(q["disciplina_origem"])
        for j, c in enumerate(conceitos):
            idx = [pos_t[n] for n in nos_de[c["key"]] if n in pos_t]
            ex = np.sort(s_ex[ex_conc == c["key"]])[::-1]
            X[i, j, 0] = s_doc[idx].max() if idx else 0
            X[i, j, 1] = ex[0] if len(ex) else 0
            X[i, j, 2] = ex[:3].mean() if len(ex) else 0
            X[i, j, 3] = ev[q["id"]]["pesos_L"].get(c["key"], 0.0)
            X[i, j, 4] = lex_modelo(q["texto"], nos_de[c["key"]], tes)
            X[i, j, 5] = (T[idx] @ o).max() if o is not None and idx else 0
            X[i, j, 6] = float(ev[q["id"]]["O"] == c["key"])
            X[i, j, 7] = float(disc == c["disciplina"])
            X[i, j, 8] = float(tes["nos"][c["base"]]["lixeira"])
            X[i, j, 11] = s_tit[idx].max() if idx else 0
        for f, z in ((0, 9), (1, 10)):
            col = X[i, :, f]
            X[i, :, z] = (col - col.mean()) / (col.std() + 1e-6)
    np.savez_compressed(INTERIM / "features.npz", X=X, ids=np.array([q["id"] for q in qs]), chaves=np.array(chaves),
                        bases=np.array([c["base"] for c in conceitos]), nomes=np.array(FEATURES))
    print(f"features: {X.shape[0]} questões × {X.shape[1]} conceitos × {X.shape[2]} | "
          f"questões com algum termo do modelo: {(X[:, :, 4].max(1) > 0).sum()}")


if __name__ == "__main__":
    main()
