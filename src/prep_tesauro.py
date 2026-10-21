"""Preparação (LLM permitido): o GPT-6 Luna PROPÕE enriquecimento para cada ficha do tesauro; o código revisa; o
que passa vira dado versionado em tesauro/tesauro_enriquecido.jsonl, com a origem de cada campo.

Para cada nó ativo de nível 1 ou 2 (os nós novos sem descrição herdam a ficha do tema-base e ficam de fora), o LLM
recebe o caminho, a ficha curada, o pai, os irmãos e os filhos, e propõe: escopo, o que não cobre (os irmãos),
termos típicos de prova, leis/artigos e 6 exemplos curtos e originais de questão sobre o tema. Nenhuma questão de
questoes.jsonl é mostrada ao LLM nem rotulada por ele.

Revisão automática (o que não passa é descartado e contado):
- leis: só ficam as que a regex do tesauro reconhece (thesaurus.diploma_canonico);
- termos: minúsculas, 2+ caracteres, sem repetir os curados;
- exemplos: descartados se 30%+ dos 8-gramas aparecem em alguma questão real (anti-vazamento) ou se repetem outro
  exemplo do mesmo tema.
Saídas: tesauro/tesauro_enriquecido.jsonl e out/revisao_tesauro.csv (amostra para revisão humana).
Uso: python src/prep_tesauro.py   (precisa de OPENROUTER_API_KEY; ~US$ 0,25; respostas em cache/llm)
"""
import csv
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

import thesaurus
from clients import USAGE, llm_json
from common import INTERIM, OUT, ROOT, Tree, read_jsonl, sha
from s02_taxonomy import norm

MODELO = "openai/gpt-6-luna"
SAIDA = ROOT / "tesauro" / "tesauro_enriquecido.jsonl"

SYSTEM = """Você ajuda a construir um tesauro jurídico (vocabulário controlado, ISO 25964) que organiza questões de \
concursos de Direito Penal, Processo Penal, Legislação Penal Especial e Criminologia por tema. Para o tema indicado, \
proponha em português:
- escopo: 1 ou 2 frases dizendo exatamente o que o tema cobre;
- nao_cobre: 1 frase dizendo o que NÃO entra aqui e vai para os temas irmãos (cite-os pelo nome);
- termos: 6 a 12 expressões curtas típicas de enunciados de prova sobre o tema (minúsculas, sem artigos soltos);
- leis: os dispositivos que ancoram o tema, só se tiver certeza. diploma no formato "CP", "CPP", "LEP", "CF" ou \
"Lei 11.343/2006"; artigos como "33-47" ou "312; 316". Lista vazia se o tema for doutrinário;
- exemplos: 6 enunciados curtos e ORIGINAIS de questões de concurso que cobram especificamente este tema e não os \
irmãos: 3 do tipo certo_errado (a assertiva a julgar) e 3 do tipo multipla (o comando e a alternativa correta). \
Nada de copiar questões reais conhecidas."""

SCHEMA = {"type": "object", "additionalProperties": False,
          "required": ["escopo", "nao_cobre", "termos", "leis", "exemplos"],
          "properties": {
              "escopo": {"type": "string"},
              "nao_cobre": {"type": "string"},
              "termos": {"type": "array", "items": {"type": "string"}},
              "leis": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                  "required": ["diploma", "artigos"],
                                                  "properties": {"diploma": {"type": "string"},
                                                                 "artigos": {"type": "string"}}}},
              "exemplos": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                      "required": ["tipo", "texto"],
                                                      "properties": {"tipo": {"type": "string",
                                                                              "enum": ["certo_errado", "multipla"]},
                                                                     "texto": {"type": "string"}}}}}}


def pedido(no, tree, tes):
    n, d = tree[no], tes["nos"][no]
    pai = tree[n["parent"]]["caminho"] if n["parent"] else ""
    irmaos = [tree[i]["titulo"] for i in tree.children(n["parent"]) if i != no and not tree[i]["novo"]]
    filhos = [tree[i]["titulo"] for i in n["children"]]
    refs = "; ".join(f"{r['diploma']} {r.get('artigos') or ''}".strip() for r in d.get("refs_legais") or [])
    return (f"TEMA: {n['caminho']} (nível {n['nivel']})\nPAI: {pai}\nIRMÃOS: {'; '.join(irmaos) or '-'}\n"
            f"FILHOS (subtemas): {'; '.join(filhos) or '-'}\nFICHA ATUAL: termos = {', '.join(d.get('altLabel') or []) or '-'}"
            f" | leis = {refs or '-'} | nota = {d.get('nota_en') or '-'}\n\nResponda em JSON.")


def shingles(texto, n=8):
    t = norm(texto).split()
    return {" ".join(t[i:i + n]) for i in range(len(t) - n + 1)}


def main():
    tree, tes = Tree(), thesaurus.tesauro()
    nos = [i for i, n in tree.nodes.items() if n["nivel"] in (1, 2) and not n["novo"]]
    reais = set()
    for q in read_jsonl(INTERIM / "questoes_limpas.jsonl"):
        reais |= shingles(q["texto"])
    prompt_sha = sha(SYSTEM + json.dumps(SCHEMA, sort_keys=True))[:12]

    def propor(no):
        out, _ = llm_json(MODELO, SYSTEM, pedido(no, tree, tes), SCHEMA, max_tokens=2000)
        return no, out

    with ThreadPoolExecutor(12) as ex:
        propostas = list(ex.map(propor, nos))

    descartes = {"leis": 0, "termos": 0, "exemplos_vazamento": 0, "exemplos_repetidos": 0}
    linhas = []
    for no, p in propostas:
        curados = {norm(t) for t in tes["nos"][no].get("altLabel") or []}
        termos = []
        for t in p["termos"]:
            k = norm(t)
            if len(k) < 2 or k in curados or k in {norm(x) for x in termos}:
                descartes["termos"] += 1
            else:
                termos.append(t.strip().lower())
        leis = []
        for lei in p["leis"]:
            if thesaurus.diploma_canonico(lei["diploma"]):
                leis.append(lei)
            else:
                descartes["leis"] += 1
        exemplos, vistos = [], set()
        for e in p["exemplos"]:
            sh = shingles(e["texto"])
            if sh and len(sh & reais) / len(sh) >= 0.3:
                descartes["exemplos_vazamento"] += 1
            elif norm(e["texto"]) in vistos:
                descartes["exemplos_repetidos"] += 1
            else:
                vistos.add(norm(e["texto"]))
                exemplos.append(e)
        linhas.append({"id": no, "caminho": tree[no]["caminho"],
                       "escopo": p["escopo"], "nao_cobre": p["nao_cobre"], "termos": termos, "leis": leis,
                       "exemplos": exemplos,
                       "origem": {"modelo": MODELO, "data": time.strftime("%Y-%m-%d"), "prompt_sha": prompt_sha,
                                  "revisao": "automática (leis pela regex, anti-vazamento de 8-gramas, duplicatas)"}})
    linhas.sort(key=lambda r: r["caminho"])
    with open(SAIDA, "w", encoding="utf-8") as f:
        for r in linhas:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OUT / "revisao_tesauro.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tema_id", "caminho", "escopo", "nao_cobre", "termos", "leis", "exemplo_1", "exemplo_2",
                    "aprovado_professor"])
        for r in linhas[::12]:                                # amostra de ~30 fichas para revisão humana
            w.writerow([r["id"], r["caminho"], r["escopo"], r["nao_cobre"], "; ".join(r["termos"]),
                        "; ".join(f"{x['diploma']} {x['artigos']}" for x in r["leis"]),
                        *(x["texto"] for x in (r["exemplos"] + [{"texto": ""}] * 2)[:2]), ""])
    n_ex = sum(len(r["exemplos"]) for r in linhas)
    print(f"{len(linhas)} fichas enriquecidas | termos novos {sum(len(r['termos']) for r in linhas)} | leis "
          f"{sum(len(r['leis']) for r in linhas)} | exemplos {n_ex} | descartes {descartes} | custo US$ "
          f"{USAGE.get('llm_usd', 0):.3f} (pago agora US$ {USAGE.get('llm_usd_novo', 0):.3f})")


if __name__ == "__main__":
    main()
