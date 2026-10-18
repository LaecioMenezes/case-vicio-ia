"""Tesauro (vocabulário controlado, à moda da biblioteconomia): leitura e usos.

Cada tema da árvore vira um descritor com (nomes no espírito do SKOS / ISO 25964):
- prefLabel, broader/narrower (TG/TE), related (TR);
- altLabel: termos de entrada (sinônimos, siglas, expressões típicas de prova);
- refs_legais: dispositivos de lei que ancoram o tema (ex.: CP arts. 312–313);
- nota_en: nota de escopo, só onde o título não basta (temas genéricos, gêmeos, partes, homógrafos);
- familias: grupos de nós que disputam a mesma questão (gêmeos, "(Parte N)", sobreposições).

Este módulo faz duas coisas com ele:
1. casamento lexical: acha na questão os termos de entrada e as citações de lei (grátis, explicável);
2. critérios das Choices do Jev (um objeto por opção, como a doc da TypeSafe recomenda).
"""
import re
from functools import lru_cache

from common import INTERIM, read_json
from s02_taxonomy import norm

# ---------------------------------------------------------------- citações de lei
LEI = re.compile(r"(?<!decreto-)(?<!decreto )\blei\s*(?:complementar\s*|federal\s*)?"
                 r"(?:n\s*[º°o.]*\s*\.?\s*)?(\d{1,2}\.?\d{3})", re.I)
DL = re.compile(r"\bdecreto[\s-]*lei\s*(?:n\s*[º°o.]*\s*\.?\s*)?(\d{1,2}\.?\d{3})", re.I)
ART = re.compile(r"\bart(?:igo)?s?\.?\s*(\d{1,4})", re.I)
CODIGOS = [("CPP", re.compile(r"\bCPP\b|c[óo]digo de processo penal", re.I)),
           ("LEP", re.compile(r"\bLEP\b|lei de execu[çc][ãa]o penal", re.I)),
           ("CP", re.compile(r"\bCP\b|c[óo]digo penal", re.I)),
           ("CF", re.compile(r"\bCF\b|constitui[çc][ãa]o federal", re.I))]
# leis que têm nome de código
ALIAS = {"L7210": "LEP", "DL2848": "CP", "DL3689": "CPP", "DL3688": "LCP"}


def diploma_canonico(s):
    """'Lei 11.343/2006' -> 'L11343'; 'Decreto-Lei 3.688/41' -> 'LCP'; 'CP' -> 'CP'."""
    s = (s or "").strip()
    m = DL.search(s)
    if m:
        k = "DL" + m.group(1).replace(".", "")
        return ALIAS.get(k, k)
    m = LEI.search(s)
    if m:
        k = "L" + m.group(1).replace(".", "")
        return ALIAS.get(k, k)
    for nome, rx in CODIGOS:
        if rx.search(s):
            return nome
    up = s.upper()
    return up if up in {"CP", "CPP", "CF", "LEP", "LCP", "ECA"} else None


def faixas(artigos):
    """'312-313; 316' -> [(312, 313), (316, 316)]. Letras (149-A) ficam com o número."""
    out = []
    s = re.sub(r"(\d+)-[A-Z]\b", r"\1", artigos or "")
    for a, b in re.findall(r"(\d+)\s*(?:a|-|–|até)\s*(\d+)", s):
        out.append((int(a), int(b)))
    s = re.sub(r"(\d+)\s*(?:a|-|–|até)\s*(\d+)", " ", s)
    out += [(int(n), int(n)) for n in re.findall(r"\d+", s)]
    return out


def citacoes(texto):
    """Citações de lei/artigo no texto da questão: {('L11343', None), ('CP', 312), ...}."""
    refs = set()
    for m in DL.finditer(texto):
        refs.add((ALIAS.get("DL" + m.group(1).replace(".", ""), "DL" + m.group(1).replace(".", "")), None))
    for m in LEI.finditer(texto):
        refs.add((ALIAS.get("L" + m.group(1).replace(".", ""), "L" + m.group(1).replace(".", "")), None))
    for m in ART.finditer(texto):
        # o diploma do artigo é a menção mais próxima depois dele ("art. 41 do CPP e da Lei X")
        janela = texto[m.end():m.end() + 70]
        mencoes = [(lm.start(), diploma_canonico(lm.group(0))) for rx in (DL, LEI) for lm in rx.finditer(janela)]
        mencoes += [(cm.start(), nome) for nome, rx in CODIGOS for cm in rx.finditer(janela)]
        mencoes = [(pos, dip) for pos, dip in mencoes if pos < 40 and dip]
        if mencoes:
            refs.add((min(mencoes)[1], int(m.group(1))))
    return refs


# ---------------------------------------------------------------- tesauro
@lru_cache(maxsize=1)
def tesauro():
    return read_json(INTERIM / "tesauro.json")


@lru_cache(maxsize=1)
def _indice_lexical():
    """Termos de entrada normalizados -> nós; e refs legais por diploma."""
    t = tesauro()
    termos, refs = {}, {}
    for no, d in t["nos"].items():
        cand = list(d.get("altLabel") or [])
        if not d.get("lixeira") and len(norm(d["prefLabel"]).split()) >= 2:
            cand.append(d["prefLabel"])
        for termo in cand:
            k = norm(termo)
            if len(k) >= 4:
                termos.setdefault(k, set()).add(no)
        for r in d.get("refs_legais") or []:
            dip = diploma_canonico(r.get("diploma"))
            fx = faixas(r.get("artigos"))
            if dip and (fx or dip not in {"CP", "CPP", "CF"}):   # "o CP inteiro" não ajuda
                refs.setdefault(dip, []).append((no, fx))
    return termos, refs


def evidencias(texto):
    """Casamento lexical: [{'no', 'tipo': 'ref'|'termo', 'termo'}]. Usa só o que pessoas escreveram no
    tesauro (termos curados e dispositivos legais), nunca os termos propostos pelo Jev: assim a
    testemunha lexical continua independente do Jev."""
    termos, refs = _indice_lexical()
    ev = []
    for dip, art in citacoes(texto):
        for no, fx in refs.get(dip, []):
            if not fx or (art is not None and any(a <= art <= b for a, b in fx)):
                ev.append({"no": no, "tipo": "ref", "termo": f"{dip}:{art}" if art else dip})
    alvo = f" {norm(texto)} "
    para = tesauro()["no_para_conceito"]
    for k, nos in termos.items():
        if f" {k} " in alvo:
            n_conc = len({para.get(no, no) for no in nos})       # termo ambíguo entre conceitos vale menos
            for no in nos:
                ev.append({"no": no, "tipo": "termo", "termo": k, "n_conceitos": n_conc})
    return ev


@lru_cache(maxsize=1)
def _diplomas_com_tema():
    return {diploma_canonico(r.get("diploma")) for d in tesauro()["nos"].values() for r in d.get("refs_legais") or []}


@lru_cache(maxsize=None)
def leis_sem_tema(texto):
    """Leis citadas na questão que não ancoram nenhum tema da árvore: ['Lei 9.029'] (candidatas a "fora")."""
    out = []
    for dip in sorted({dip for dip, _ in citacoes(texto)} - _diplomas_com_tema()):
        m = re.fullmatch(r"(DL|L)(\d+)", dip or "")
        if m:
            out.append(("Decreto-Lei " if m.group(1) == "DL" else "Lei ") + f"{int(m.group(2)):,}".replace(",", "."))
    return out


def _dispositivos(d):
    return "; ".join(f"{r['diploma']} arts. {r['artigos']}" if r["artigos"] else r["diploma"]
                     for r in d.get("refs_legais") or [])


def criterio(no, com_area=False):
    """Critério-objeto de uma opção da Choice do Jev, montado só a partir do tesauro: a nota de escopo
    (em inglês, a língua mais forte do Jev), os dispositivos legais e os termos de entrada em português
    (é assim que aparecem nas questões). Campos vazios ficam de fora."""
    d = tesauro()["nos"][no]
    c = {"area": d["disciplina"]} if com_area else {}
    if d.get("nota_en"):
        c["scope"] = d["nota_en"]
    if d.get("refs_legais"):
        c["legal_basis"] = _dispositivos(d)
    termos = (d.get("altLabel") or []) + (d.get("altLabel_jev") or [])   # curados primeiro, depois os do Jev
    if termos:
        c["typical_terms"] = termos[:12]
    return c


def conceitos_n1():
    """Conceitos de nível 1 para o Jev: gêmeos e "(Parte N)" já vêm unidos ao tema-base."""
    return tesauro()["conceitos_n1"]


def conceito_de(no):
    """Chave do conceito N1 que contém o nó (via o tema de nível 1 do nó)."""
    return tesauro()["no_para_conceito"].get(str(no))


def no_base(key):
    """Nó-base (o tema antigo, com os subtemas) de um conceito N1."""
    return next(c["base"] for c in conceitos_n1() if c["key"] == key)
