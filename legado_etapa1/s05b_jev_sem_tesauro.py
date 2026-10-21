"""Etapa 5b (experimento de controle): o Jev SEM o tesauro. Não entra na decisão.

Para medir se o tesauro faz diferença, o Jev classifica as mesmas questões vendo só a árvore crua, como
ela está na plataforma: os 109 temas de nível 1 pelo caminho (gêmeos e "(Parte N)" como opções
separadas), sem nota de escopo, sem leis e sem termos. Duas ordens, como no s05. O s06 compara a taxa
de acerto desta versão com a do Jev com tesauro, usando o assunto de origem como régua independente.

Saída: data/interim/jev_sem_tesauro.jsonl
"""
from concurrent.futures import ThreadPoolExecutor

from clients import USAGE, jev
from common import INTERIM, Tree, read_jsonl, write_jsonl
from s05_jev import INSTR_N1, NENHUM, choice, duas_ordens, media


def main():
    tree = Tree()
    nivel1 = sorted((n for n in tree.nodes.values() if n["nivel"] == 1), key=lambda n: n["caminho"])
    por_caminho = {n["caminho"]: n["id"] for n in nivel1}
    crit = {n["caminho"]: None for n in nivel1}                      # só o nome da opção, como na plataforma
    a, b = duas_ordens(crit, (NENHUM, None))
    qs = read_jsonl(INTERIM / "questoes_limpas.jsonl")

    def decidir(q):
        r = jev({"exam_question_pt": q["texto"]}, {"n1_a": choice(INSTR_N1, a), "n1_b": choice(INSTR_N1, b)})["answers"]
        p, cons = media(r["n1_a"], r["n1_b"])
        k = max(p, key=p.get)
        return {"id": q["id"], "no": por_caminho.get(k), "p": p[k], "consistente": cons}

    with ThreadPoolExecutor(8) as ex:
        rows = list(ex.map(decidir, qs))
    write_jsonl(INTERIM / "jev_sem_tesauro.jsonl", rows)
    print(f"{len(rows)} questões | consistente nas 2 ordens: {sum(r['consistente'] for r in rows)} | "
          f"Jev: {USAGE['jev_tokens']:,} tokens ~US$ {USAGE['jev_usd']:.3f}")


if __name__ == "__main__":
    main()
