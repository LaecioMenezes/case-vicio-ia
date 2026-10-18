"""Etapa 3b: o Jev ajuda a preencher o dicionário de temas (tesauro).

O Jev não escreve texto, mas preencher um tesauro é, em boa parte, decidir onde cada coisa entra.
Três tarefas, todas com regras fixas de aceite e com a origem de cada item registrada:

1. Termos de entrada vindos das próprias questões ("garantia literária" da biblioteconomia: o termo
   entra porque aparece nos documentos). O código colhe expressões de 2 a 4 palavras que se repetem em
   pelo menos duas questões; o Jev decide a qual dos 89 conceitos cada uma pertence, ou se é genérica.
   Só entra o que ele decide igual nas duas ordens, com certeza ≥ 0,85, e que ele julga específico.
   Esses termos vão para os critérios do próprio Jev (s05) e para a fila de aprovação do professor.
   Eles NÃO entram na testemunha lexical (s04): se entrassem, o Jev estaria conferindo a si mesmo e a
   precisão prevista sairia inflada.
2. Cruzamento do assunto de origem: o Jev escolhe o conceito dos assuntos que não casaram nem pelo
   título nem pela curadoria. Ele vê só o nome do assunto, não a questão.
3. Auditoria: para cada termo curado, o Jev diz se o termo indica mesmo aquele tema. Os duvidosos vão
   para a planilha do professor; nada muda sozinho.

Saídas: data/interim/tesauro.json (enriquecido), out/termos_propostos_jev.csv, out/tesauro_auditoria.csv
"""
import csv
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

import thesaurus
from clients import USAGE, jev
from common import INTERIM, OUT, read_jsonl, write_json
from s02_taxonomy import norm
from s05_jev import choice, duas_ordens, media

GENERICO = "Termo genérico"
SEM = "Sem correspondência"
P_MIN, ESPECIFICO_MIN, N_MAX, DF_MAX = 0.85, 0.7, 250, 25
STOP = set("a b c d e i ii iii iv v vi vii viii ix x o as os é de da do das dos em no na nos nas por pelo pela para "
           "com que se um uma uns umas ao aos à às ou sua seu suas seus ser foi são não mais como já há sobre entre "
           "quando qual quais este esta esse essa isso isto ele ela eles elas lhe tem pode podem deve deverá será art "
           "lei nº n f inciso parágrafo caput apenas caso nesse nessa neste nesta assim também anos dias meses".split())
# expressões de enunciado e nomes genéricos de órgãos e códigos: o Jev as daria como genéricas, então nem perguntamos
FRASES_GENERICAS = ("assinale", "alternativa", "correto afirmar", "incorreto afirmar", "julgue", "de acordo com",
                    "nos termos", "com base", "a respeito", "acerca", "no que se refere", "em relação", "considerando",
                    "item a seguir", "situação hipotética", "hipotética", "assertiva", "afirmativa", "segundo o",
                    "conforme o", "enunciado", "opção", "corretas", "incorretas", "tribunal", "supremo", "superior",
                    "constituição", "código", "processual penal", "direito penal", "penal brasileiro", "crimes contra",
                    "crime contra", "crime de", "tenha sido", "diz respeito", "acordo com", "previsto no", "artigo",
                    "jurisprudência", "defensoria", "delegacia", "seguida", "responderá", "condenado por", "item",
                    "correta", "qualquer")
TOKEN = re.compile(r"[a-záàâãéêíóôõúüç]+(?:-[a-záàâãéêíóôõúüç]+)*")
INSTR_TERMO = ("Which syllabus topic does this Portuguese legal term typically indicate when it appears in Brazilian "
               "law exam questions? The example sentences only show how the term is used. Choose '" + GENERICO + "' "
               "if the term is common to many topics or does not point to one specific topic.")
NOUL_ESPECIFICO = {"type": "noul",
                   "instructions": "Does this term point to one specific legal topic, rather than being a common "
                                   "expression used across many topics?",
                   "criteria": {"true": "The term names a specific crime, institute, procedural act or doctrine.",
                                "false": "The term is a generic expression (e.g. 'ministério público', 'prazo de', "
                                         "'pena de')."}}
INSTR_ORIGEM = ("Which syllabus topic corresponds to this subject name, taken from the website where the question "
                "came from? Choose '" + SEM + "' if the name is a whole discipline, covers several topics, or has no "
                "match in the list.")


def trecho(texto, termo, raio=70):
    i = texto.lower().find(termo)
    return re.sub(r"\s+", " ", texto[max(0, i - raio): i + len(termo) + raio]).strip()


def candidatos(qs, conhecidos):
    """Expressões de 2 a 4 palavras que se repetem em 2 a 25 questões e ainda não estão no tesauro."""
    df, exemplos = Counter(), defaultdict(list)
    for q in qs:
        toks = TOKEN.findall(q["texto"].lower())
        vistos = set()
        for n in (2, 3, 4):
            for i in range(len(toks) - n + 1):
                g = toks[i:i + n]
                if g[0] not in STOP and g[-1] not in STOP:
                    vistos.add(" ".join(g))
        for t in vistos:
            df[t] += 1
            if len(exemplos[t]) < 3:
                exemplos[t].append(trecho(q["texto"], t))
    cands = [t for t, n in df.items() if 2 <= n <= DF_MAX and norm(t) not in conhecidos
             and len(norm(t).split()) >= 2 and not any(f in t for f in FRASES_GENERICAS)]
    cands.sort(key=lambda t: (-df[t], -len(t)))
    escolhidos = []
    for t in cands:                                        # fica a forma mais longa entre as de mesma frequência
        if not any(t in e and df[e] == df[t] for e in escolhidos):
            escolhidos.append(t)
        if len(escolhidos) >= N_MAX:
            break
    return escolhidos, df, exemplos


def main():
    tes = thesaurus.tesauro()
    conceitos = thesaurus.conceitos_n1()
    por_key = {c["key"]: c for c in conceitos}
    crit = {c["key"]: thesaurus.criterio(c["base"], com_area=True) for c in conceitos}
    qs = read_jsonl(INTERIM / "questoes_limpas.jsonl")

    # 1. termos de entrada vindos das questões
    conhecidos = {norm(t) for d in tes["nos"].values() for t in d["altLabel"] + [d["prefLabel"]]}
    termos, df, exemplos = candidatos(qs, conhecidos)
    ta, tb = duas_ordens(crit, (GENERICO, {"scope": "The term is common to many topics, or does not point to one topic."}))

    def classificar(t):
        r = jev({"term_pt": t, "example_sentences_pt": exemplos[t]},
                {"a": choice(INSTR_TERMO, ta), "b": choice(INSTR_TERMO, tb), "especifico": NOUL_ESPECIFICO})["answers"]
        p, cons = media(r["a"], r["b"])
        k = max(p, key=p.get)
        aceito = cons and k != GENERICO and p[k] >= P_MIN and r["especifico"]["noul"] >= ESPECIFICO_MIN
        return {"termo": t, "conceito": k, "p": round(p[k], 3), "consistente": cons,
                "especifico": round(r["especifico"]["noul"], 3), "questoes": df[t], "aceito": aceito}

    with ThreadPoolExecutor(8) as ex:
        propostas = list(ex.map(classificar, termos))
    for nos in tes["nos"].values():
        nos["altLabel_jev"] = []
    for pr in propostas:
        if pr["aceito"]:
            tes["nos"][por_key[pr["conceito"]]["base"]]["altLabel_jev"].append(pr["termo"])

    # 2. cruzamento do assunto de origem que ficou sem correspondência
    sem_par = [a for a, v in tes["crosswalk_assunto"].items() if not v]
    oa, ob = duas_ordens(crit, (SEM, {"scope": "Whole discipline, several topics, or no match in the list."}))
    cross_jev = {}

    def mapear(a):
        r = jev({"source_subject_pt": a}, {"a": choice(INSTR_ORIGEM, oa), "b": choice(INSTR_ORIGEM, ob)})["answers"]
        p, cons = media(r["a"], r["b"])
        k = max(p, key=p.get)
        return a, k, p[k], cons

    with ThreadPoolExecutor(8) as ex:
        for a, k, p, cons in ex.map(mapear, sem_par):
            ok = cons and k != SEM and p >= P_MIN
            cross_jev[a] = {"conceito": k, "p": round(p, 3), "aceito": ok}
            if ok:
                tes["crosswalk_assunto"][a] = [por_key[k]["base"]]
    tes["crosswalk_jev"] = cross_jev

    # 3. auditoria dos termos curados (uma requisição por tema, uma pergunta por termo)
    def auditar(item):
        no, d = item
        perguntas = {f"t{i}": {"type": "noul",
                               "instructions": f"In Brazilian law exam questions, does the term '{t}' typically "
                                               f"indicate the topic '{d['prefLabel']}' ({d['caminho']})?"}
                     for i, t in enumerate(d["altLabel"])}
        r = jev({"topic_pt": d["caminho"], "scope": d.get("nota_en", "")}, perguntas)["answers"]
        return [(no, d["caminho"], t, r[f"t{i}"]["noul"]) for i, t in enumerate(d["altLabel"])]

    alvos = [(no, d) for no, d in tes["nos"].items() if d["altLabel"] and not d.get("herdado_de")]
    with ThreadPoolExecutor(8) as ex:
        auditoria = [linha for lote in ex.map(auditar, alvos) for linha in lote]

    write_json(INTERIM / "tesauro.json", tes)
    thesaurus.tesauro.cache_clear()
    thesaurus._indice_lexical.cache_clear()
    with open(OUT / "termos_propostos_jev.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["termo", "conceito_proposto", "certeza", "consistente_2_ordens", "especifico", "n_questoes",
                    "aceito", "aprovado_professor"])
        for pr in sorted(propostas, key=lambda x: (not x["aceito"], -x["questoes"])):
            w.writerow([pr["termo"], pr["conceito"], pr["p"], pr["consistente"], pr["especifico"], pr["questoes"],
                        pr["aceito"], ""])
    with open(OUT / "tesauro_auditoria.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tema_id", "caminho", "termo", "p_indica_o_tema", "sinal"])
        for no, cam, t, p in sorted(auditoria, key=lambda x: x[3]):
            w.writerow([no, cam, t, round(p, 3), "duvidoso" if p < 0.5 else "ok"])

    aceitos = sum(p["aceito"] for p in propostas)
    print(f"termos candidatos colhidos das questões: {len(termos)} | aceitos pelo Jev: {aceitos} "
          f"(vão para os critérios do Jev e para aprovação; não votam como testemunha)")
    print(f"assuntos de origem sem correspondência: {len(sem_par)} | mapeados pelo Jev: "
          f"{sum(v['aceito'] for v in cross_jev.values())}")
    print(f"auditoria: {len(auditoria)} termos curados conferidos | duvidosos: {sum(p < 0.5 for *_, p in auditoria)}")
    print(f"Jev: {USAGE['jev_tokens']:,} tokens ~US$ {USAGE['jev_usd']:.3f} ({USAGE['calls']} chamadas novas)")


if __name__ == "__main__":
    main()
