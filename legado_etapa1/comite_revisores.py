"""Experimento: comitê de revisores LLM (não faz parte do pipeline).

Gera um "revisor" sintético que só vota quando os modelos do comitê concordam entre si; se discordam,
responde "Nenhum destes temas" (abstenção). O custo é a soma dos custos. O arquivo vai para
data/interim/revisores/, e o comparar_modelos.py o avalia como qualquer outro revisor.

Uso: python src/comite_revisores.py openai/gpt-6-luna anthropic/claude-haiku-5.5
"""
import sys

from common import INTERIM, read_jsonl, write_jsonl
from s05_jev import NENHUM


def main():
    modelos = sys.argv[1:]
    dir_ = INTERIM / "revisores"
    runs = [{r["id"]: r for r in read_jsonl(dir_ / (m.replace("/", "__") + ".jsonl"))} for m in modelos]
    rows = []
    for qid in runs[0]:
        votos = [run[qid] for run in runs]
        unanime = len({v["tema"] for v in votos}) == 1
        rows.append({"id": qid, "tema": votos[0]["tema"] if unanime else NENHUM,
                     "confianca": "alta" if unanime and all(v["confianca"] == "alta" for v in votos)
                     else ("media" if unanime else "baixa"),
                     "justificativa": "comitê: " + (" | ".join(v["tema"] for v in votos)),
                     "custo": sum(v.get("custo") or 0 for v in votos)})
    nome = "comite__" + "+".join(m.split("/")[-1] for m in modelos)
    write_jsonl(dir_ / f"{nome}.jsonl", rows)
    print(f"{nome}: unânimes em {sum(r['tema'] != NENHUM for r in rows)} de {len(rows)}")


if __name__ == "__main__":
    main()
