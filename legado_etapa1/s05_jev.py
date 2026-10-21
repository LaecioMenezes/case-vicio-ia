"""Etapa 5: decisão tipada com o Jev sobre os conceitos do tesauro. É o modelo que decide; o revisor (s05d) só
confirma ou contesta.

Por questão, duas requisições (as perguntas de uma mesma requisição rodam em paralelo no Jev):
A) Choice N1 entre os 89 conceitos de nível 1 (gêmeos e "(Parte N)" unidos ao tema-base), cada opção
   com o critério-objeto do tesauro {area, scope, legal_basis, typical_terms}; feita em duas ordens
   (normal e invertida), porque o Jev 1.13 tende a escolher a primeira opção. Junto: Noul "é matéria
   penal?" e Noul "as alternativas misturam temas?".
B) Noul de verificação do conceito vencedor (a mesma decisão perguntada de outro jeito: "esta questão
   cobra mesmo o tema X?"); Choice N2 entre os subtemas dos 2 conceitos mais prováveis, com a opção
   "tema em geral", em duas ordens; e, para cada tema genérico (lixeira) envolvido, uma Noul "a questão
   é mesmo sobre o conceito geral, e não sobre um instituto específico?".

O state é só a questão (enunciado + alternativas), sem nenhum metadado de origem, que pode estar
errado. "Nenhum destes temas" fica sempre por último, para o viés de primeira opção não inflar o "fora".

Saída: data/interim/jev.jsonl
"""
import argparse
from concurrent.futures import ThreadPoolExecutor

import thesaurus
from clients import USAGE, jev
from common import INTERIM, read_jsonl, write_jsonl

NENHUM = "Nenhum destes temas"
GERAL = "Tema em geral"
INSTR_N1 = ("Which syllabus topic is this Brazilian law exam question mainly testing? Choose the topic of the "
            "legal point the candidate must know to answer, not topics that only appear in the story. "
            "Topic names and terms are in Portuguese.")
INSTR_N2 = ("Which subtopic of '{t}' is this Brazilian law exam question mainly testing? Choose the subtopic of "
            "the legal point the candidate must know to answer. Choose '" + GERAL + "' if the question is about "
            "the topic in general or about an aspect that no listed subtopic covers.")
CRIT_NENHUM = {"scope": "The question is not about Brazilian criminal law, criminal procedure, special criminal "
                        "statutes or criminology (e.g. tax, civil or constitutional law), or its subject is not in this list."}
NOUL_PENAL = {"type": "noul",
              "instructions": "Does this exam question test Brazilian criminal law, criminal procedure, special criminal "
                              "legislation or criminology?",
              "criteria": {"true": "The legal point asked is criminal: crimes, penalties, criminal procedure, criminal "
                                   "statutes or criminology.",
                           "false": "The legal point asked belongs to another field, such as tax, civil, administrative "
                                    "or constitutional law."}}
NOUL_MISTA = {"type": "noul",
              "instructions": "Do the answer options of this question test two or more different syllabus topics, "
                              "without one common subject?",
              "criteria": {"true": "Different options are about unrelated topics (e.g. one about prescription, another "
                                   "about jurisdiction).",
                           "false": "The question and its options revolve around one subject."}}


def choice(instr, criteria):
    return {"type": "choice", "instructions": instr, "criteria": criteria}


def duas_ordens(opcoes, ultima):
    """Critérios na ordem normal e invertida; a opção `ultima` fica sempre no fim."""
    itens = list(opcoes.items())
    return dict(itens + [ultima]), dict(itens[::-1] + [ultima])


def media(ra, rb):
    pa, pb = ra["probabilities"], rb["probabilities"]
    return {k: (pa.get(k, 0) + pb.get(k, 0)) / 2 for k in pa}, ra["choice"] == rb["choice"]


def resumo_criterio(c):
    partes = [c.get("scope", ""), f"Legal basis: {c['legal_basis']}." if c.get("legal_basis") else "",
              f"Typical terms: {', '.join(c['typical_terms'])}." if c.get("typical_terms") else ""]
    return " ".join(p for p in partes if p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=0, help="só as primeiras N questões (teste)")
    args = ap.parse_args()

    tes = thesaurus.tesauro()
    conceitos = thesaurus.conceitos_n1()
    por_key = {c["key"]: c for c in conceitos}
    crit_n1 = {c["key"]: thesaurus.criterio(c["base"], com_area=True) for c in conceitos}
    n1_a, n1_b = duas_ordens(crit_n1, (NENHUM, CRIT_NENHUM))
    qs = {q["id"]: q for q in read_jsonl(INTERIM / "questoes_limpas.jsonl")}
    ids = list(qs)[:args.n] if args.n else list(qs)

    def geral_noul(no):
        d = tes["nos"][no]
        return {"type": "noul",
                "instructions": f"Is this question specifically about the general topic '{d['prefLabel']}', rather "
                                f"than about a specific crime, institute or procedure?",
                "criteria": {"true": "The legal point asked is the general concept itself. " + d.get("nota_en", ""),
                             "false": "The legal point asked is a specific crime, institute or procedural act."}}

    def decidir(qid):
        state = {"exam_question_pt": qs[qid]["texto"]}
        ra = jev(state, {"n1_a": choice(INSTR_N1, n1_a), "n1_b": choice(INSTR_N1, n1_b),
                         "penal": NOUL_PENAL, "mista": NOUL_MISTA})["answers"]
        p1, consistente = media(ra["n1_a"], ra["n1_b"])
        top = sorted(p1, key=lambda k: -p1[k])
        out = {"id": qid, "n1": {"p": p1, "top": top[:3], "consistente": consistente,
                                 "conf": [ra["n1_a"]["confidence"], ra["n1_b"]["confidence"]]},
               "penal": ra["penal"]["noul"], "mista": ra["mista"]["noul"], "verif": None, "n2": {}, "geral_ok": {}}

        candidatos = [t for t in top if t != NENHUM][:2]
        perguntas, mapas = {}, {}
        if candidatos:
            k1 = candidatos[0]
            perguntas["verif"] = {"type": "noul",
                                  "instructions": f"Is this exam question mainly testing the topic '{k1}'?",
                                  "criteria": {"true": "The legal point the candidate must know belongs to this topic. "
                                                       + resumo_criterio(crit_n1[k1]),
                                               "false": "The legal point asked belongs to another topic; this topic "
                                                        "only appears in the story or not at all."}}
        for k, key in enumerate(candidatos):
            base = por_key[key]["base"]
            filhos = tes["nos"][base]["narrower"]
            for no in [n for n in [base] + filhos if tes["nos"][n]["lixeira"]]:
                perguntas[f"geral_{no}"] = geral_noul(no)
            if filhos:
                nomes = {}
                for f in filhos:                              # chave = título (único entre irmãos)
                    nome = tes["nos"][f]["prefLabel"]
                    nomes[nome if nome not in nomes else f"{nome} [{f}]"] = f
                crit = {nome: thesaurus.criterio(f) for nome, f in nomes.items()}
                ger = (GERAL, {"scope": f"The question is about '{tes['nos'][base]['prefLabel']}' in general, or about "
                                        f"an aspect not covered by the listed subtopics."})
                a, b = duas_ordens(crit, ger)
                instr = INSTR_N2.format(t=tes["nos"][base]["prefLabel"])
                perguntas[f"n2_{k}_a"], perguntas[f"n2_{k}_b"] = choice(instr, a), choice(instr, b)
                mapas[k] = (key, {**nomes, GERAL: "__geral__"})
        if perguntas:
            rb = jev(state, perguntas)["answers"]
            out["verif"] = rb["verif"]["noul"] if "verif" in rb else None
            for k, (key, nomes) in mapas.items():
                p2, cons2 = media(rb[f"n2_{k}_a"], rb[f"n2_{k}_b"])
                out["n2"][key] = {"p": {nomes[n]: v for n, v in p2.items()}, "consistente": cons2}
            out["geral_ok"] = {nome[6:]: r["noul"] for nome, r in rb.items() if nome.startswith("geral_")}
        return out

    with ThreadPoolExecutor(8) as ex:
        rows = list(ex.map(decidir, ids))
    write_jsonl(INTERIM / ("jev_teste.jsonl" if args.n else "jev.jsonl"), rows)
    cons = sum(r["n1"]["consistente"] for r in rows)
    print(f"{len(rows)} questões | N1 consistente nas 2 ordens: {cons}/{len(rows)} | "
          f"'nenhum' no topo: {sum(r['n1']['top'][0] == NENHUM for r in rows)} | "
          f"Jev: {USAGE['jev_tokens']:,} tokens ~US$ {USAGE['jev_usd']:.3f} ({USAGE['calls']} chamadas novas, "
          f"{USAGE['cache_hits']} do cache)")
    if args.n:
        for r in rows:
            p = r["n1"]["p"]
            print(r["id"], [(k, round(p[k], 2)) for k in r["n1"]["top"]], "| penal", round(r["penal"], 2),
                  "| mista", round(r["mista"], 2), "| verif", r["verif"] and round(r["verif"], 2),
                  "| consistente", r["n1"]["consistente"])


if __name__ == "__main__":
    main()
