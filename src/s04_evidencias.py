"""Etapa 4: análise de assunto sem modelo: as duas testemunhas independentes do Jev.

Para cada questão, no nível dos conceitos N1 do tesauro:
- L (testemunha lexical): citações de lei/artigo e termos de entrada do tesauro achados no texto.
  Citação legal pesa 3; termo de várias palavras pesa 1; palavra solta pesa 0,5; termo que aparece
  em vários conceitos pesa menos. L só "vota" quando um conceito domina (peso ≥ 1,5 e o dobro do 2º).
- O (testemunha de origem): o `assunto_origem` cruzado com a árvore (tesauro/crosswalk_origem.txt).
  Quando o assunto cai em dois conceitos homógrafos (Ação Penal no CP e no CPP), desempata pela
  disciplina de origem; se continuar ambíguo, O não vota. "FORA" quando o assunto não é penal.

Nenhuma das duas é gabarito (o LEIA-ME avisa que o assunto de origem pode estar errado). Elas servem
para (a) medir o Jev sem gabarito, por triangulação (s06), e (b) reforçar ou contestar o Jev (s07).

Saída: data/interim/evidencias.jsonl
"""
from collections import defaultdict

import thesaurus
from common import INTERIM, Tree, read_jsonl, write_jsonl

DISC = {"Direito Penal": "Penal", "Penal": "Penal", "Processo Penal": "Processo Penal",
        "Direito Processual Penal": "Processo Penal", "Criminologia": "Criminologia",
        "Direito Penal - Legislação Especial": "Direito Penal - Legislação Especial"}


def testemunha_lexical(ev):
    peso = defaultdict(float)
    vistos = set()
    for e in ev:
        conc = thesaurus.conceito_de(e["no"])
        if not conc or (conc, e["termo"]) in vistos:            # cada termo conta uma vez por conceito
            continue
        vistos.add((conc, e["termo"]))
        if e["tipo"] == "ref":
            peso[conc] += 3
        else:
            peso[conc] += (1.0 if " " in e["termo"] else 0.5) / e["n_conceitos"]
    ordem = sorted(peso, key=lambda k: -peso[k])
    if ordem and peso[ordem[0]] >= 1.5 and (len(ordem) == 1 or peso[ordem[0]] >= 2 * peso[ordem[1]]):
        return ordem[0], dict(peso)
    return None, dict(peso)


def testemunha_origem(q, tes, tree):
    nos = tes["crosswalk_assunto"].get(q["assunto_origem"], [])
    if nos == ["FORA"]:
        return "FORA", nos
    concs = {thesaurus.conceito_de(n) for n in nos if thesaurus.conceito_de(n)}
    if len(concs) > 1:                                          # homógrafo: desempata pela disciplina
        disc = DISC.get(q["disciplina_origem"])
        concs = {c for c in concs if tree[thesaurus.no_base(c)]["disciplina"] == disc}
    return (concs.pop() if len(concs) == 1 else None), nos


def main():
    tree, tes = Tree(), thesaurus.tesauro()
    rows = []
    for q in read_jsonl(INTERIM / "questoes_limpas.jsonl"):
        ev = thesaurus.evidencias(q["texto"])
        L, pesos = testemunha_lexical(ev)
        O, o_nos = testemunha_origem(q, tes, tree)
        L_ref = bool(L) and any(e["tipo"] == "ref" and thesaurus.conceito_de(e["no"]) == L for e in ev)
        rows.append({"id": q["id"], "L": L, "L_ref": L_ref, "O": O, "pesos_L": pesos, "nos_O": o_nos,
                     "nos_L": sorted({e["no"] for e in ev}), "lex": ev})
    write_jsonl(INTERIM / "evidencias.jsonl", rows)
    n = len(rows)
    print(f"{n} questões | testemunha lexical vota em {sum(bool(r['L']) for r in rows)} | "
          f"testemunha de origem vota em {sum(bool(r['O']) for r in rows)} (FORA: {sum(r['O'] == 'FORA' for r in rows)}) | "
          f"as duas: {sum(bool(r['L']) and bool(r['O']) for r in rows)} | "
          f"concordam entre si: {sum(bool(r['L']) and r['L'] == r['O'] for r in rows)}")


if __name__ == "__main__":
    main()
