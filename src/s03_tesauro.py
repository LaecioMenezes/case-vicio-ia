"""Etapa 3: monta o tesauro (vocabulário controlado) a partir da curadoria e da árvore. Sem API.

Por que um tesauro: as descrições do temas.csv são inúteis ("Subtema de X. N questões no source.")
e o Jev lê os critérios ao pé da letra. A biblioteconomia resolve isso com notas de escopo, termos de
entrada (como o assunto aparece no texto), dispositivos de lei e relações entre termos.

Fontes:
- tesauro/tesauro_curado.txt: a curadoria (uma linha por tema: dispositivos, termos de entrada, nota
  de escopo). É a fonte de verdade, editável pelo professor;
- tesauro/crosswalk_origem.txt: o cruzamento do vocabulário do site de origem com a árvore;
- a árvore (s02): hierarquia (TG/TE), gêmeos, "(Parte N)", nós novos, temas genéricos.

O script organiza tudo em código:
1. famílias de nós que disputam a mesma questão: gêmeos (mesmo título em dois ramos), "(Parte N)"
   (fatias irmãs do tema-base), novo × antigo, homógrafos (Ação Penal no CP e no CPP) e sobreposições
   (o mesmo assunto em duas disciplinas com títulos diferentes);
2. herança: gêmeos e fatias sem linha própria herdam a linha do tema-base;
3. o esquema de conceitos de nível 1 que o Jev vê: gêmeos e fatias unidos ao tema-base, porque duas
   opções idênticas só dividiriam a probabilidade (a convenção vira regra explícita na política);
4. o cruzamento do assunto_origem com a árvore;
5. controle de qualidade.

Saídas: data/interim/tesauro.json e out/tesauro_revisao.csv (a planilha para o professor revisar).
"""
import csv
import re
from collections import defaultdict

from common import INTERIM, OUT, ROOT, Tree, read_jsonl, write_json
from s02_taxonomy import norm

CURADO = ROOT / "tesauro" / "tesauro_curado.txt"
CROSS = ROOT / "tesauro" / "crosswalk_origem.txt"
DIPLOMA = re.compile(r"^(Lei(?: Complementar)? [\d.]+/\d{4}|Decreto-Lei [\d.]+/\d{4}|CPP|CP|CF|LEP|LCP|ECA)\s*(.*)$")

# Mesmo assunto em disciplinas diferentes, com títulos diferentes (os de título igual saem do s02).
SOBREPOSICOES = [
    ("4700", "5555"),   # interceptação telefônica: lei especial × meio de prova
    ("4701", "5539"),   # juizado especial criminal × procedimento sumaríssimo
    ("4705", "5557"),   # organizações criminosas × colaboração premiada
    ("4705", "5559"),   # organizações criminosas × infiltração de agentes
    ("4705", "5558"),   # organizações criminosas × ação controlada
    ("4703", "5566"),   # execução penal × agravo em execução
    ("4704", "5131"),   # Maria da Penha × violência psicológica contra a mulher (CP 147-B)
    ("4690", "5124"),   # racismo × injúria (injúria racial)
    ("4709", "5108"),   # ECA × corrupção de menores
]


def ler_curadoria():
    out = {}
    for linha in CURADO.read_text(encoding="utf-8").splitlines():
        if not linha.strip() or linha.lstrip().startswith("#"):
            continue
        partes = [p.strip() for p in linha.split("|")] + ["", "", ""]
        tid, refs, termos, nota = partes[:4]
        dispositivos = []
        for r in filter(None, (x.strip() for x in refs.split(";"))):
            m = DIPLOMA.match(r)
            dispositivos.append({"diploma": m.group(1), "artigos": m.group(2)} if m else {"diploma": r, "artigos": ""})
        out[tid] = {"refs_legais": dispositivos, "nota_en": nota,
                    "altLabel": [t.strip() for t in termos.split(";") if t.strip()]}
    return out


def familias(tree):
    fams = []
    grupos = defaultdict(list)
    for n in tree.nodes.values():
        if n["grupo_dup"]:
            grupos[n["grupo_dup"]].append(n)
    for membros in grupos.values():
        novos = [m for m in membros if m["novo"]]
        antigos = [m for m in membros if not m["novo"]]
        if novos and all(not m["children"] for m in membros):
            tipo = "gemeos"
        elif novos:
            tipo = "novo_x_antigo"
        else:
            tipo = "homografo"
        base = antigos[0]["id"] if antigos and tipo != "homografo" else None
        fams.append({"tipo": tipo, "nos": sorted(m["id"] for m in membros), "base": base})
    partes = defaultdict(list)
    for n in tree.nodes.values():
        if n["parte_de"]:
            partes[n["parte_de"]].append(n["id"])
    for base, ps in partes.items():
        fams.append({"tipo": "parte", "nos": sorted([base] + ps), "base": base})
    for a, b in SOBREPOSICOES:
        fams.append({"tipo": "sobreposicao", "nos": sorted([a, b]), "base": None})
    for k, f in enumerate(fams, 1):
        f["id"] = f"F{k:02d}"
    return fams


def conceitos(tree, fams):
    """Conceitos N1 do Jev. Gêmeos, novo×antigo e partes unidos ao tema-base."""
    une = {}
    for f in fams:
        if f["tipo"] in ("gemeos", "novo_x_antigo", "parte"):
            for no in f["nos"]:
                if tree[no]["nivel"] == 1 and no != f["base"]:
                    une[no] = f["base"]
    nivel1 = [n for n in tree.nodes.values() if n["nivel"] == 1 and n["id"] not in une]
    nivel1.sort(key=lambda n: (n["disciplina"], norm(n["titulo"])))
    contagem = defaultdict(int)
    for n in nivel1:
        contagem[norm(n["titulo"])] += 1
    out, no_para = [], {}
    for n in nivel1:
        nos = [n["id"]] + sorted(k for k, v in une.items() if v == n["id"])
        key = n["titulo"]
        if contagem[norm(n["titulo"])] > 1:                       # homógrafo: qualifica pela disciplina
            key = f"{n['titulo']} ({n['disciplina']})"
        outras = sorted({tree[k]["disciplina"] for k in nos} - {n["disciplina"]})
        if outras:                                                # gêmeo em outra disciplina
            key = f"{n['titulo']} ({' ou '.join([n['disciplina']] + outras)})"
        out.append({"key": key, "base": n["id"], "nos": nos, "disciplina": n["disciplina"]})
        for k in nos:
            no_para[k] = key
    for n in tree.nodes.values():                                 # subtemas -> conceito do tema N1
        if n["nivel"] == 2:
            no_para[n["id"]] = no_para[tree.n1(n["id"])]
    return out, no_para


def crosswalk(tree):
    """assunto_origem -> nós: primeiro a curadoria (prefixo), depois o título normalizado, parte a parte."""
    curado = []
    for linha in CROSS.read_text(encoding="utf-8").splitlines():
        if linha.strip() and not linha.lstrip().startswith("#"):
            prefixo, alvo = (p.strip() for p in linha.split("|"))
            curado.append((prefixo, alvo))
    por_titulo = defaultdict(list)
    for n in tree.nodes.values():
        if n["nivel"] > 0:
            por_titulo[norm(n["titulo"])].append(n["id"])
    cross = {}
    for q in read_jsonl(INTERIM / "questoes_limpas.jsonl"):
        a = q["assunto_origem"]
        if not a or a in cross:
            continue
        alvo = next((t for p, t in curado if a.startswith(p)), None)
        if alvo:
            cross[a] = [alvo]
        else:
            cross[a] = sorted({i for parte in a.split(",") for i in por_titulo.get(norm(parte), [])})
    return cross


def main():
    tree = Tree()
    cur = ler_curadoria()
    fams = familias(tree)
    por_no = defaultdict(list)
    for f in fams:
        for no in f["nos"]:
            por_no[no].append(f["id"])
    conc, no_para = conceitos(tree, fams)

    nos, herdados = {}, []
    for n in tree.nodes.values():
        c = cur.get(n["id"])
        herdado = None
        if c is None:                                             # gêmeo/fatia sem linha: herda do tema-base
            base = next((f["base"] for f in fams if n["id"] in f["nos"] and f["base"] and f["base"] != n["id"]), None)
            if base and base in cur:
                c = {**cur[base], "nota_en": f"Same subject as '{tree[base]['caminho']}' (topic duplicated in "
                                            f"another branch of the tree). " + cur[base]["nota_en"]}
                herdado = base
                herdados.append(n["id"])
        c = c or {"refs_legais": [], "nota_en": "", "altLabel": []}
        nos[n["id"]] = {
            "prefLabel": n["titulo"], "caminho": n["caminho"], "nivel": n["nivel"], "disciplina": n["disciplina"],
            "broader": n["parent"], "narrower": n["children"],
            "related": sorted({m for f in fams if n["id"] in f["nos"] for m in f["nos"]} - {n["id"]}),
            "familias": por_no.get(n["id"], []), "altLabel": c["altLabel"], "refs_legais": c["refs_legais"],
            "nota_en": c["nota_en"], "novo": n["novo"], "lixeira": n["generico"], "herdado_de": herdado,
        }

    cross = crosswalk(tree)
    sem_curadoria = [i for i, d in nos.items() if not d["altLabel"]]
    termo_conc = defaultdict(set)
    for i, d in nos.items():
        for t in d["altLabel"]:
            if no_para.get(i):
                termo_conc[norm(t)].add(no_para[i])
    repetidos = {t: sorted(v) for t, v in termo_conc.items() if len(v) > 1}

    write_json(INTERIM / "tesauro.json", {
        "nos": nos, "familias": fams, "conceitos_n1": conc, "no_para_conceito": no_para,
        "crosswalk_assunto": cross, "qc": {"sem_curadoria": sem_curadoria, "termos_em_varios_conceitos": repetidos}})
    with open(OUT / "tesauro_revisao.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tema_id", "caminho", "nivel", "novo", "lixeira", "familias", "dispositivos", "termos_entrada",
                    "nota_escopo", "herdado_de"])
        for i, d in nos.items():
            w.writerow([i, d["caminho"], d["nivel"], d["novo"], d["lixeira"], ";".join(d["familias"]),
                        "; ".join(f"{r['diploma']} {r['artigos']}".strip() for r in d["refs_legais"]),
                        "; ".join(d["altLabel"]), d["nota_en"], d["herdado_de"] or ""])

    tipos = defaultdict(int)
    for f in fams:
        tipos[f["tipo"]] += 1
    print(f"{len(nos)} descritores | {len(conc)} conceitos N1 para o Jev | famílias: {dict(tipos)}")
    print(f"herdados do tema-base: {len(herdados)} | sem curadoria: {sem_curadoria}")
    print(f"assunto_origem com correspondência: {sum(bool(v) for v in cross.values())}/{len(cross)} | "
          f"termos de entrada em mais de um conceito: {len(repetidos)}")


if __name__ == "__main__":
    main()
