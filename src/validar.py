"""Validador dos entregáveis (formato do LEIA-ME) e testes do casamento lexical do tesauro."""
import csv
import re
import sys

import thesaurus
from common import INTERIM, ROOT, Tree, read_jsonl


def main():
    tree, erros = Tree(), []
    rows = list(csv.DictReader(open(ROOT / "publicacao.csv", encoding="utf-8", newline="")))
    if list(rows[0].keys()) != ["id", "decisao", "tema_central_id", "extras_ids", "confianca", "motivo"]:
        erros.append(f"colunas erradas: {list(rows[0].keys())}")
    if (INTERIM / "questoes_limpas.jsonl").exists():
        ids = {q["id"] for q in read_jsonl(INTERIM / "questoes_limpas.jsonl")}
        if {r["id"] for r in rows} != ids or len(rows) != len(ids):
            erros.append(f"ids: {len(rows)} linhas, esperado uma por questão ({len(ids)})")
    for r in rows:
        d, t = r["decisao"], r["tema_central_id"]
        if d not in ("publicar", "revisar", "fora"):
            erros.append(f"{r['id']}: decisão inválida {d!r}")
        if d == "fora" and t:
            erros.append(f"{r['id']}: fora com tema")
        if d != "fora" and t not in tree.nodes:
            erros.append(f"{r['id']}: tema inexistente/inativo {t!r}")
        if d == "publicar" and t in tree.nodes and tree[t]["nivel"] == 0:
            erros.append(f"{r['id']}: publicado na raiz (disciplina)")
        if d in ("revisar", "fora") and not r["motivo"].strip():
            erros.append(f"{r['id']}: motivo vazio em {d}")
        for e in filter(None, r["extras_ids"].split(";")):
            if e not in tree.nodes:
                erros.append(f"{r['id']}: extra inválido {e!r}")
        if not 0 <= float(r["confianca"]) <= 1:
            erros.append(f"{r['id']}: confiança fora de [0,1]")
    linhas = (ROOT / "previsao.txt").read_text(encoding="utf-8").splitlines()
    padroes = [r"precisao_prevista: [01]\.\d\d$", r"precisao_intervalo: [01]\.\d\d-[01]\.\d\d$",
               r"cobertura_prevista: [01]\.\d\d$", r"cobertura_intervalo: [01]\.\d\d-[01]\.\d\d$"]
    for linha, p in zip(linhas[:4], padroes):
        if not re.match(p, linha):
            erros.append(f"previsao.txt: linha fora do formato: {linha!r}")
    # casamento lexical: citações viram os temas certos
    refs = thesaurus.citacoes("nos termos do art. 312 do Código Penal")
    if ("CP", 312) not in refs:
        erros.append(f"citação 'art. 312 do CP' não reconhecida: {refs}")
    ev = {e["no"] for e in thesaurus.evidencias("crime previsto no art. 312 do Código Penal (peculato)")}
    if "5089" not in ev:
        erros.append(f"'art. 312 do CP' não levou ao tema Peculato (5089): {sorted(ev)[:10]}")
    ev = {thesaurus.conceito_de(e["no"]) for e in thesaurus.evidencias("violência doméstica, Lei 11.340/2006")}
    if not any(k and "Maria da Penha" in k for k in ev):
        erros.append(f"'Lei 11.340/2006' não levou à família Maria da Penha: {ev}")
    cont = {d: sum(r["decisao"] == d for r in rows) for d in ("publicar", "revisar", "fora")}
    print(f"publicacao.csv: {len(rows)} linhas {cont} | previsao.txt: {linhas[:4]}")
    if erros:
        print("ERROS:\n- " + "\n- ".join(erros[:40]))
        sys.exit(1)
    print("OK: entregáveis no formato do LEIA-ME e testes do tesauro passando.")


if __name__ == "__main__":
    main()
