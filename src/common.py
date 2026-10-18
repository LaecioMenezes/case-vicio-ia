"""Caminhos, leitura de arquivos e utilidades da árvore de temas."""
import csv
import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
CACHE = ROOT / "cache"
OUT = ROOT / "out"
for _d in (INTERIM, CACHE, OUT):
    _d.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT / ".env")


def env(name, default=None):
    return os.environ.get(name, default) or default


def config():
    """Limiares, triangulação e convenções (config/politica.json)."""
    return read_json(ROOT / "config" / "politica.json")


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def sha(obj):
    s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class Tree:
    """Árvore de temas ativa (gerada por s02_taxonomy.py)."""

    def __init__(self, path=INTERIM / "arvore.json"):
        self.nodes = {n["id"]: n for n in read_json(path)["nodes"]}

    def __getitem__(self, i):
        return self.nodes[str(i)]

    def children(self, i):
        return self.nodes[str(i)]["children"]

    def ancestors(self, i):
        """Ids do pai até a raiz (sem incluir o próprio nó)."""
        out, p = [], self.nodes[str(i)]["parent"]
        while p:
            out.append(p)
            p = self.nodes[p]["parent"]
        return out

    def roots(self):
        return [n["id"] for n in self.nodes.values() if not n["parent"]]

    def same_branch(self, a, b):
        """Mesmo ramo em qualquer profundidade (inclui avô/neto)."""
        a, b = str(a), str(b)
        return a == b or a in self.ancestors(b) or b in self.ancestors(a)

    def acerto(self, publicado, gabarito):
        """Regra exata do case: certo se for o próprio nó do gabarito, o pai ou um filho dele."""
        p, g = str(publicado), str(gabarito)
        return p == g or self.nodes[g]["parent"] == p or self.nodes[p]["parent"] == g

    def n1(self, i):
        """Tema de nível 1 que contém o nó (o próprio, se já for nível 1; None para disciplina)."""
        n = self.nodes[str(i)]
        while n["nivel"] > 1:
            n = self.nodes[n["parent"]]
        return n["id"] if n["nivel"] == 1 else None

    def lca(self, ids):
        """Ancestral comum mais profundo de um conjunto de nós."""
        ids = [str(i) for i in ids]
        paths = [[i] + self.ancestors(i) for i in ids]
        common = set(paths[0]).intersection(*map(set, paths[1:]))
        for n in paths[0]:  # do mais profundo para a raiz
            if n in common:
                return n
        return None
