"""Etapa 5c: segunda rodada do Jev, só entre os finalistas. Mais Jev, menos professor.

O professor é escasso, então hesitação do Jev não deve virar fila de revisão logo de cara. Antes disso,
uma segunda rodada: o Jev escolhe entre os 5 conceitos mais prováveis da primeira rodada, com as fichas
completas do tesauro, em 4 ordens (rodízio), e confirma o escolhido com uma pergunta de verificação.
Com 5 opções em vez de 89, o viés de posição e a leitura ao pé da letra pesam menos; com 4 ordens, só
passa o que ele responde sempre igual.

Os candidatos vêm só da primeira rodada do próprio Jev, nunca do tesauro nem do assunto de origem, para
a triangulação continuar medindo com testemunhas independentes.

Saída: data/interim/jev_final.jsonl
"""
from concurrent.futures import ThreadPoolExecutor

import thesaurus
from clients import USAGE, jev
from common import INTERIM, read_jsonl, write_jsonl
from s05_jev import CRIT_NENHUM, INSTR_N1, NENHUM, choice, resumo_criterio

N_FINALISTAS, N_ORDENS = 5, 4


def main():
    por_key = {c["key"]: c for c in thesaurus.conceitos_n1()}
    qs = {q["id"]: q for q in read_jsonl(INTERIM / "questoes_limpas.jsonl")}
    r1 = {r["id"]: r for r in read_jsonl(INTERIM / "jev.jsonl")}

    def decidir(qid):
        p = r1[qid]["n1"]["p"]
        cands = [k for k in sorted(p, key=lambda k: -p[k]) if k != NENHUM][:N_FINALISTAS]
        crit = {k: thesaurus.criterio(por_key[k]["base"], com_area=True) for k in cands}
        perguntas = {}
        for o in range(N_ORDENS):                                   # rodízio; "nenhum" sempre por último
            ordem = cands[o:] + cands[:o]
            perguntas[f"o{o}"] = choice(INSTR_N1, {**{k: crit[k] for k in ordem}, NENHUM: CRIT_NENHUM})
        for i, k in enumerate(cands):
            perguntas[f"v{i}"] = {"type": "noul", "instructions": f"Is this exam question mainly testing the topic '{k}'?",
                                  "criteria": {"true": "The legal point the candidate must know belongs to this topic. "
                                                       + resumo_criterio(crit[k]),
                                               "false": "The legal point asked belongs to another topic; this topic "
                                                        "only appears in the story or not at all."}}
        r = jev({"exam_question_pt": qs[qid]["texto"]}, perguntas)["answers"]
        chaves = cands + [NENHUM]
        p2 = {k: sum(r[f"o{o}"]["probabilities"].get(k, 0) for o in range(N_ORDENS)) / N_ORDENS for k in chaves}
        vencedor = max(p2, key=p2.get)
        estavel = all(r[f"o{o}"]["choice"] == vencedor for o in range(N_ORDENS))
        verif = r[f"v{cands.index(vencedor)}"]["noul"] if vencedor in cands else None
        return {"id": qid, "finalistas": cands, "p": p2, "top": vencedor, "estavel": estavel, "verif": verif,
                "mudou": vencedor != r1[qid]["n1"]["top"][0]}

    with ThreadPoolExecutor(8) as ex:
        rows = list(ex.map(decidir, list(qs)))
    write_jsonl(INTERIM / "jev_final.jsonl", rows)
    print(f"{len(rows)} questões | estáveis nas 4 ordens: {sum(r['estavel'] for r in rows)} | "
          f"mudaram de tema em relação à 1ª rodada: {sum(r['mudou'] for r in rows)} | "
          f"Jev: {USAGE['jev_tokens']:,} tokens ~US$ {USAGE['jev_usd']:.3f} (pago agora: US$ {USAGE['jev_usd_novo']:.3f})")


if __name__ == "__main__":
    main()
