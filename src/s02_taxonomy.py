"""Etapa 2: monta a árvore de temas ativa e marca os nós problemáticos.

Marcações (usadas pela política de decisão e pelo memo ao professor):
- generico:   título introdutório/geral ("Introdução", "Disposições Gerais", "Teoria Geral"...),
              candidato a "lixeira".
- parte_n:    nó "(Parte N)" sem subtemas e sem descrição, espelho de módulo de curso.
- grupo_dup:  nós com o mesmo assunto em ramos diferentes (ex.: Lei Maria da Penha em
              Penal e em Legislação Especial). Publicar no ramo "errado" conta como erro.
"""
import re
import unicodedata
from collections import defaultdict

from common import INTERIM, RAW, read_csv, write_json

GENERICO = re.compile(r"introdu|no[çc][õo]es gerais|disposi[çc][õo]es gerais|teoria geral|"
                      r"parte geral|regras gerais|^conceito", re.I)
PARTE_N = re.compile(r"\(parte\s*0?\d+\)", re.I)


TYPOS = {"estaturo": "estatuto", "crimonologicas": "criminologicas", "caracteristas": "caracteristicas",
         "comeptencia": "competencia", "testemunhavel": "testemunhavel"}


def norm(t):
    """Título comparável: sem acento, artigos, "(Parte N)", plural e erros de digitação."""
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    t = PARTE_N.sub("", t)
    t = re.sub(r"\(parte\s*0?\d+\)\s*-?", "", t)
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    words = [TYPOS.get(w, w) for w in t.split()]
    words = [w for w in words if w not in {"de", "do", "da", "dos", "das", "e", "a", "o", "em"}]
    words = [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words]
    return " ".join(words)


def main():
    rows = read_csv(RAW / "temas.csv")
    ativos = {r["tema_id"]: r for r in rows if r["status"] == "active"}
    inativos = [r["caminho"] for r in rows if r["status"] != "active"]

    nodes = {}
    for tid, r in ativos.items():
        desc = (r["descricao"] or "").strip()
        m = re.search(r"(\d+) questões", desc)
        nodes[tid] = {
            "id": tid,
            "parent": r["parent_id"] if r["parent_id"] in ativos else None,
            "nivel": int(r["nivel"]),
            "disciplina": r["disciplina"],
            "titulo": r["titulo"].strip(),
            "caminho": r["caminho"].strip(),
            "n_origem": int(m.group(1)) if m else None,
            # descrição de verdade (não o modelo "Subtema de X. N questões no source")
            "descricao": "" if m else desc,
            # nó criado depois das descrições: sem texto nenhum (IDs 6716–6738 neste recorte)
            "novo": not desc,
            "children": [],
            "generico": bool(GENERICO.search(r["titulo"])),
            "parte_n": bool(PARTE_N.search(r["titulo"])),
            "grupo_dup": None,
        }
    for n in nodes.values():
        if n["parent"]:
            nodes[n["parent"]]["children"].append(n["id"])

    # Duplicados: mesmo título normalizado (plural, artigos e erros de digitação tratados)
    # em nós que não são ancestral/descendente um do outro. "(Parte N)" fica de fora:
    # vira `parte_de`, apontando para o tema base irmão.
    def anc(i):
        out, p = set(), nodes[i]["parent"]
        while p:
            out.add(p)
            p = nodes[p]["parent"]
        return out

    grupos = defaultdict(set)
    for n in nodes.values():
        if n["nivel"] > 0 and not n["parte_n"]:
            grupos[norm(n["titulo"])].add(n["id"])
    for chave, membros in grupos.items():
        membros = {m for m in membros if not (anc(m) & membros)}
        if len(membros) > 1:
            gid = min(membros)
            for m in membros:
                nodes[m]["grupo_dup"] = gid

    for n in nodes.values():
        n["parte_de"] = None
        if n["parte_n"]:
            base = norm(n["titulo"])
            irmaos = [s for s in nodes.values() if s["parent"] == n["parent"]
                      and not s["parte_n"] and norm(s["titulo"]) == base]
            n["parte_de"] = irmaos[0]["id"] if irmaos else None

    write_json(INTERIM / "arvore.json", {"nodes": list(nodes.values()), "inativos": inativos})

    print(f"{len(nodes)} nós ativos ({len(inativos)} inativos descartados: {inativos})")
    dups = defaultdict(list)
    for n in nodes.values():
        if n["grupo_dup"]:
            dups[n["grupo_dup"]].append(n["caminho"])
    print(f"genéricos: {sum(n['generico'] for n in nodes.values())} | "
          f"(Parte N): {sum(n['parte_n'] for n in nodes.values())} | grupos de duplicados: {len(dups)}")
    for caminhos in dups.values():
        print("  DUP:", " || ".join(sorted(caminhos)))
    for n in nodes.values():
        if n["parte_n"]:
            print("  PARTE:", n["caminho"], "->", nodes[n["parte_de"]]["caminho"] if n["parte_de"] else "SEM BASE")
    print("maior número de filhos num nó:", max(len(n["children"]) for n in nodes.values()))


if __name__ == "__main__":
    main()
