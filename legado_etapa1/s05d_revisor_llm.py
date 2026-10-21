"""Etapa 5d: revisor automático, um LLM barato no lugar da revisão do professor (config revisor_llm.modelo:
OpenAI GPT-6 Luna, pelo OpenRouter, escolhido pelo custo-benefício em src/comparar_modelos.py).

O LLM revisa as 359 questões (não só as não publicadas): assim a mesma triangulação mede a taxa de acerto
dele contra uma régua independente (o assunto de origem).

O LLM vê a questão e a lista inteira dos 89 temas do tesauro (não só os finalistas do Jev, para não ser
puxado por ele) e escolhe um tema, ou "Nenhum destes temas", com nível de confiança e justificativa curta.
No s06/s07 ele confirma ou contesta o Jev, e a justificativa vai junto com a sugestão de tema.

Uso: python src/s05d_revisor_llm.py [--modelo anthropic/claude-haiku-5.5]
Saída: data/interim/revisores/<modelo>.jsonl (o revisor usado na decisão é o de config revisor_llm.modelo)
"""
import argparse
from concurrent.futures import ThreadPoolExecutor

import thesaurus
from clients import USAGE, llm_json
from common import INTERIM, config, env, read_jsonl, write_jsonl
from s05_jev import NENHUM

REVISORES = INTERIM / "revisores"


def arquivo_revisor(modelo):
    return REVISORES / (modelo.replace("/", "__").replace(":", "_") + ".jsonl")

SYSTEM = """Você é professor de Direito Penal, Processo Penal, Legislação Penal Especial e Criminologia e revisa a \
classificação de questões de concurso por tema numa plataforma de estudos. Regras:
1. Escolha o tema do ponto de direito que a questão cobra (o que o candidato precisa saber para acertar), não temas \
que só aparecem como cenário da história.
2. Em "assinale a correta", olhe as alternativas para achar o assunto comum.
3. Temas genéricos ou introdutórios só servem se a questão for sobre o conceito geral em si.
4. Se nenhum tema da lista serve (ou a questão nem é de matéria penal), responda "Nenhum destes temas".
5. confianca: "alta" se não há dúvida razoável; "media" se há um tema vizinho plausível; "baixa" se está em dúvida.

TEMAS (chave exata | área | dispositivos | termos típicos | escopo):
"""


def lista_temas():
    linhas = []
    for c in thesaurus.conceitos_n1():
        d = thesaurus.tesauro()["nos"][c["base"]]
        refs = "; ".join(f"{r['diploma']} {r['artigos']}".strip() for r in d.get("refs_legais") or [])
        termos = ", ".join((d.get("altLabel") or [])[:6])
        nota = (d.get("nota_en") or "")[:180]
        linhas.append(f"- {c['key']} | {d['disciplina']} | {refs or '-'} | {termos or '-'}" + (f" | {nota}" if nota else ""))
    return "\n".join(linhas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", default=config().get("revisor_llm", {}).get("modelo") or env("LLM_REVISOR", "openai/gpt-6-luna"))
    MODELO = ap.parse_args().modelo
    keys = [c["key"] for c in thesaurus.conceitos_n1()] + [NENHUM]
    system = SYSTEM + lista_temas()
    schema = {"type": "object", "additionalProperties": False, "required": ["tema", "confianca", "justificativa"],
              "properties": {"tema": {"type": "string", "enum": keys},
                             "confianca": {"type": "string", "enum": ["alta", "media", "baixa"]},
                             "justificativa": {"type": "string", "description": "no máximo 25 palavras"}}}
    qs = read_jsonl(INTERIM / "questoes_limpas.jsonl")

    def revisar(q):
        out, usage = llm_json(MODELO, system, f"QUESTÃO:\n{q['texto']}\n\nResponda em JSON.", schema)
        return {"id": q["id"], **out, "custo": usage.get("cost", 0), "tokens_in": usage.get("prompt_tokens"),
                "tokens_out": usage.get("completion_tokens")}

    with ThreadPoolExecutor(12) as ex:
        rows = list(ex.map(revisar, qs))
    REVISORES.mkdir(parents=True, exist_ok=True)
    write_jsonl(arquivo_revisor(MODELO), rows)
    conf = {k: sum(r["confianca"] == k for r in rows) for k in ("alta", "media", "baixa")}
    print(f"{MODELO}: {len(rows)} questões revisadas | confiança {conf} | 'nenhum': "
          f"{sum(r['tema'] == NENHUM for r in rows)} | custo total US$ {sum(r['custo'] or 0 for r in rows):.4f} "
          f"(pago agora: US$ {USAGE.get('llm_usd_novo', 0):.4f}) | tokens médios: entrada "
          f"{sum(r['tokens_in'] or 0 for r in rows) / len(rows):,.0f}, saída {sum(r['tokens_out'] or 0 for r in rows) / len(rows):,.0f}")


if __name__ == "__main__":
    main()
