"""Preparação: embeddings (qwen/qwen3-embedding-8b, pela OpenRouter) de tudo o que a decisão compara.

- questões (659): texto limpo, com a instrução de consulta que o Qwen3-Embedding recomenda;
- exemplos do tesauro (gerados pelo LLM e revisados): mesma instrução, porque também são questões;
- documento de cada tema: caminho + escopo + termos + leis, montado do tesauro (thesaurus.documento);
- assuntos de origem: o rótulo do site de origem, comparado aos documentos dos temas.

Saída versionada: artefatos/embeddings.npz (ids e matrizes em float16, normalizadas). A decisão só lê esse arquivo.
Custo: ~US$ 0,01 (US$ 0,01 por milhão de tokens). Cache local por texto em cache/emb (fora do git, grande demais).
Uso: python src/prep_embeddings.py   (precisa de OPENROUTER_API_KEY)
"""
import time

import numpy as np

import thesaurus
from clients import USAGE, embed
from common import INTERIM, ROOT, read_jsonl

MODELO = "qwen/qwen3-embedding-8b"
INSTRUCAO = ("Instruct: Given a Brazilian law exam question, retrieve the syllabus topic it tests\nQuery: ")
SAIDA = ROOT / "artefatos" / "embeddings.npz"


def matriz(textos):
    m = np.asarray(embed(MODELO, textos), dtype=np.float32)
    m /= np.linalg.norm(m, axis=1, keepdims=True)
    return m.astype(np.float16)


def main():
    qs = read_jsonl(INTERIM / "questoes_limpas.jsonl")
    tes = thesaurus.tesauro()
    temas = sorted(no for no, d in tes["nos"].items() if d["nivel"] in (1, 2))
    exemplos = [(no, i, e["texto"]) for no in temas for i, e in enumerate(tes["nos"][no].get("exemplos") or [])]
    origens = sorted({q["assunto_origem"] for q in qs if q["assunto_origem"]})
    inicio = time.time()
    dados = {
        "questoes_ids": np.array([q["id"] for q in qs]),
        "questoes": matriz([INSTRUCAO + q["texto"] for q in qs]),
        "temas_ids": np.array(temas),
        "temas": matriz([thesaurus.documento(no) for no in temas]),
        "temas_titulo": matriz([tes["nos"][no]["caminho"] for no in temas]),     # ablação: sem o tesauro
        "exemplos_tema": np.array([no for no, _, _ in exemplos]),
        "exemplos": matriz([INSTRUCAO + t for _, _, t in exemplos]),
        "origens_ids": np.array(origens),
        "origens": matriz(origens),
        "modelo": np.array(MODELO),
        "data": np.array(time.strftime("%Y-%m-%d")),
    }
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(SAIDA, **dados)
    print(f"embeddings: {len(qs)} questões, {len(temas)} temas, {len(exemplos)} exemplos, {len(origens)} origens | "
          f"dim {dados['questoes'].shape[1]} | {time.time() - inicio:.0f}s | chamadas {USAGE['calls']} | "
          f"custo US$ {USAGE.get('emb_usd', 0):.4f}")


if __name__ == "__main__":
    main()
