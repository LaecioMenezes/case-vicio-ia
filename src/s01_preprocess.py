"""Etapa 1: limpa as questões e monta o texto que os modelos vão ler.

Decisões (registradas no README):
- O `comando` é descartado: em parte das questões ele foi gerado artificialmente
  ("Explique o que é...", "Complete a frase...") e não acrescenta informação.
- Questões Certo/Errado: as alternativas "Certo"/"Errado" são omitidas (só ruído).
- `assunto_origem` e `disciplina_origem` NÃO entram no texto; ficam como metadado
  separado, porque podem estar errados (LEIA-ME).
- Duplicata = mesmo enunciado E mesmas alternativas. Enunciados iguais com
  alternativas diferentes (ex.: "Assinale a alternativa correta.") são questões distintas.
"""
import html
import re

import pandas as pd

from common import INTERIM, RAW, sha

DISCIPLINAS_PENAIS = {"Processo Penal", "Direito Penal", "Penal", "Criminologia",
                      "Direito Penal - Legislação Especial", "Direito Processual Penal"}
STEM_GENERICO = re.compile(r"^(assinale|marque|analise|considerando|sobre|acerca|"
                           r"com rela[çc][ãa]o|a respeito|no que|no tocante|é correto|julgue)", re.I)


def clean(s):
    if not isinstance(s, str) or not s:
        return ""
    s = s.replace("\\n", "\n")                      # \n literal vindo do banco
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p>|</li>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace("\xa0", " ")
    s = re.sub(r"(?<=\w)-\n(?=\w)", "", s)          # hifenização de PDF: "qual-\nquer"
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{2,}", "\n", s)
    return s.strip()


def montar_texto(row):
    partes = [f"ENUNCIADO:\n{row.enunciado}"]
    if row.alternativas and row.tipo != "certo_errado":
        partes.append("ALTERNATIVAS:\n" + "\n".join(f"{k}) {v}" for k, v in row.alternativas.items()))
    return "\n".join(partes)


def main():
    df = pd.read_json(RAW / "questoes.jsonl", lines=True, dtype={"id": str})
    df["enunciado"] = df["enunciado_html"].map(clean)
    df["alternativas"] = df["alternativas"].map(lambda a: {k: clean(v) for k, v in (a or {}).items()})
    df["tipo"] = df["alternativas"].map(
        lambda a: "certo_errado" if set(a) == {"C", "E"} else f"multipla_{len(a)}")
    df["texto"] = df.apply(montar_texto, axis=1)
    df["enunciado_generico"] = df["enunciado"].map(
        lambda e: (len(e) < 90 and bool(STEM_GENERICO.match(e))) or len(e) < 40)
    for col in ("disciplina_origem", "assunto_origem"):
        df[col] = df[col].fillna("")
    df["disciplina_suspeita"] = ~df["disciplina_origem"].isin(DISCIPLINAS_PENAIS)
    df["hash_conteudo"] = df.apply(lambda r: sha(r.enunciado + "|" + "|".join(
        f"{k}:{v}" for k, v in sorted(r.alternativas.items()))), axis=1)
    df["duplicada"] = df.duplicated("hash_conteudo", keep=False)

    cols = ["id", "texto", "enunciado", "alternativas", "tipo", "enunciado_generico",
            "disciplina_origem", "assunto_origem", "disciplina_suspeita", "hash_conteudo", "duplicada"]
    df[cols].to_json(INTERIM / "questoes_limpas.jsonl", orient="records", lines=True, force_ascii=False)

    print(f"{len(df)} questões -> data/interim/questoes_limpas.jsonl")
    print("tipos:", df["tipo"].value_counts().to_dict())
    print("enunciado genérico (conteúdo nas alternativas):", int(df["enunciado_generico"].sum()))
    print("disciplina de origem suspeita:", int(df["disciplina_suspeita"].sum()))
    print("duplicatas reais (enunciado+alternativas):", int(df["duplicada"].sum()))


if __name__ == "__main__":
    main()
