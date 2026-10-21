"""Etapa 7: política em código. Decide publicar, revisar ou fora para cada questão.

1. fora: o Jev diz que a questão não é matéria penal (Noul < 0,2) e, além disso, não acha tema na
   árvore ou o assunto de origem também diz que não é penal; ou a questão cita uma lei que não ancora
   nenhum tema da árvore e o revisor também não acha tema (ex.: Lei 9.029/95). Nesse segundo caso, a
   confiança do fora é 1 − P do tema mais provável do Jev.
2. tema proposto: o conceito N1 mais provável do Jev (média das duas ordens). Desce ao subtema só se o
   Jev tiver P(subtema) ≥ 0,9 nas duas ordens E o tesauro ou o assunto de origem apontarem o mesmo
   subtema; senão publica no tema, que a regra do case aceita (o aluno do tema vê os subtemas). Nunca
   na disciplina (raiz): a regra até contaria como certo, mas isso recriaria a lixeira.
3. confiança = P(conteúdo certo) × P(convenção):
   - P(conteúdo): a taxa de acerto do Jev na faixa de probabilidade dele, medida por triangulação
     (s06), atualizada pelo voto das testemunhas independentes daquela questão (tesauro e origem);
   - P(convenção): quando o assunto existe em mais de um lugar da árvore (gêmeos, "(Parte N)", novo ×
     antigo, homógrafos, sobreposições), a chance de a equipe ter usado o nó escolhido. Ninguém tira
     isso do texto da questão; os valores ficam em config/politica.json.
4. bloqueios que mandam para revisar: o Jev muda de resposta quando a ordem das opções muda; não
   confirma o próprio tema na pergunta de verificação; acha que as alternativas misturam temas; ou
   escolhe um tema genérico (lixeira) sem confirmar que a questão trata do conceito geral.
5. publica o maior conjunto cuja confiança média (= precisão esperada) fica ≥ o alvo, com piso por questão.

Saídas: publicacao.csv (raiz), out/decisoes_detalhadas.csv
"""
import argparse
import csv
import json
from collections import defaultdict

import thesaurus
from common import INTERIM, OUT, ROOT, Tree, config, read_json, read_jsonl
from s04_evidencias import DISC
from s05_jev import NENHUM
from s06_triangulacao import carregar_revisor, posterior, posterior_prior


def carregar():
    ler = lambda nome: {r["id"]: r for r in read_jsonl(INTERIM / nome)}
    fin = INTERIM / "jev_final.jsonl"
    return {"qs": ler("questoes_limpas.jsonl"), "jev": ler("jev.jsonl"), "ev": ler("evidencias.jsonl"),
            "fin": ler("jev_final.jsonl") if fin.exists() and config()["politica"].get("segunda_rodada") else None,
            "rev": carregar_revisor(),
            "params": read_json(INTERIM / "triangulacao.json")}


def propor(dados, convencao, params=None):
    """Proposta por questão, antes do limiar: tema central, confiança, bloqueios."""
    tree, tes, cfg = Tree(), thesaurus.tesauro(), config()
    pol, conv = cfg["politica"], cfg["convencoes"][convencao]
    params = params or dados["params"]
    por_key = {c["key"]: c for c in thesaurus.conceitos_n1()}
    fam_por_id = {f["id"]: f for f in tes["familias"]}
    out = []
    for qid, q in dados["qs"].items():
        j, e = dados["jev"][qid], dados["ev"][qid]
        f = (dados.get("fin") or {}).get(qid)
        if f:                                                 # decisão final = segunda rodada (finalistas)
            p1 = f["p"]
            top = sorted(p1, key=lambda k: -p1[k])
            estavel, verif = f["estavel"], f["verif"]
        else:
            p1, top = j["n1"]["p"], j["n1"]["top"]
            estavel, verif = j["n1"]["consistente"], j["verif"]
        k1 = next((t for t in top if t != NENHUM), None)
        prop = {"id": qid, "conceito": k1, "J": top[0], "p_n1": p1.get(top[0], 0.0), "consistente": estavel,
                "penal": j["penal"], "mista": j["mista"], "verif": verif, "L": e["L"], "O": e["O"],
                "bloqueios": [], "extras": [], "familia": "", "p_conv": 1.0, "nivel": "tema"}

        if j["penal"] < pol["fora_p_penal_max"] and (top[0] == NENHUM or e["O"] == "FORA"):
            prop.update(decisao="fora", central="", conf=round(max(1 - j["penal"], p1.get(NENHUM, 0.0)), 3),
                        motivo=f"o Jev indica que a questão não é de matéria penal (P={j['penal']:.2f}) e nenhum tema "
                               f"da árvore serve" + ("; o assunto de origem confirma" if e["O"] == "FORA" else ""))
            out.append(prop)
            continue
        r = (dados.get("rev") or {}).get(qid)
        leis = thesaurus.leis_sem_tema(q["texto"]) if pol.get("fora_lei_sem_tema") else []
        if leis and r and r["tema"] == NENHUM:
            prop.update(decisao="fora", central="", conf=round(1 - p1.get(k1, 0.0), 3),
                        motivo=f"cita {', '.join(leis)}, que não tem tema na árvore, e o revisor também não achou "
                               f"tema; sugestão: criar o tema")
            out.append(prop)
            continue

        base = por_key[k1]["base"]
        central, s = base, None
        n2 = j["n2"].get(k1)
        fator_sub = 1.0
        if n2:
            filhos = {k: v for k, v in n2["p"].items() if k != "__geral__"}
            s = max(filhos, key=filhos.get)
            apoio = s in e["nos_L"] or s in e["nos_O"]
            lixo_s = tes["nos"][s]["lixeira"] and j["geral_ok"].get(s, 0) < pol["lixeira_geral_ok_min"]
            if filhos[s] >= pol["subtema_p_min"] and n2["consistente"] and apoio and not lixo_s:
                central, prop["nivel"] = s, "subtema"
                fator_sub = filhos[s] + n2["p"].get("__geral__", 0)
        grupo = None
        if r:
            grupo = "concorda" if r["tema"] == k1 else "discorda"
            prop["revisor"], prop["revisor_conf"] = r["tema"], r["confianca"]
            prop["revisor_justificativa"] = r.get("justificativa")
        conf_conteudo = posterior(params, p1.get(k1, 0.0), k1, e["L"], e["O"], grupo) * fator_sub
        # O revisor discorda do Jev: a sugestão dele compete; fica a de maior confiança calibrada
        if r and grupo == "discorda" and r["tema"] != NENHUM and r["tema"] in por_key:
            prior_r = (params.get("acc_revisor_discorda") or {}).get(r["confianca"])
            if prior_r:
                conf_r = posterior_prior(params, prior_r, r["tema"], e["L"], e["O"])
                if conf_r > conf_conteudo:
                    k1, base, s = r["tema"], por_key[r["tema"]]["base"], None
                    central, conf_conteudo = base, conf_r
                    prop["nivel"], prop["conceito"], prop["trocado_pelo_revisor"] = "tema", k1, True

        # convenção: o assunto cai numa família de nós concorrentes?
        disc_q = DISC.get(q["disciplina_origem"])
        olhar = {central, base} | ({s} if s else set())
        for fid in sorted({fid for no in olhar for fid in tes["nos"][no]["familias"]}):
            f = fam_por_id[fid]
            if f["tipo"] in ("gemeos", "parte", "novo_x_antigo"):
                p = conv[f["tipo"]]
            else:
                ok = disc_q == tree[central]["disciplina"]
                p = conv[f"{f['tipo']}_disciplina_{'ok' if ok else 'diverge'}"]
            if p < prop["p_conv"]:
                prop["p_conv"], prop["familia"] = p, f"{f['tipo']}:" + "|".join(f["nos"])
            if f["tipo"] in ("gemeos", "novo_x_antigo"):
                prop["extras"] += [n for n in f["nos"] if n != central and tree[n]["nivel"] == tree[central]["nivel"]]

        if top[0] == NENHUM:
            prop["bloqueios"].append("o Jev não achou tema adequado na árvore (sugestão: o 2º mais provável)")
        trocado = prop.get("trocado_pelo_revisor")
        if trocado and prop.get("revisor_conf") != "alta":
            prop["bloqueios"].append("o revisor trocou o tema, mas sem confiança alta")
        if not estavel and not trocado:
            prop["bloqueios"].append("o Jev muda de tema quando a ordem das opções muda")
        if verif is not None and verif < pol["verif_min"] and not trocado:
            prop["bloqueios"].append(f"o Jev não confirmou o tema na pergunta de verificação (P={verif:.2f})")
        if j["mista"] >= pol["mista_noul_min"]:
            prop["bloqueios"].append("as alternativas parecem cobrar temas diferentes (questão mista)")
        if tes["nos"][central]["lixeira"] and j["geral_ok"].get(central, 0) < pol["lixeira_geral_ok_min"]:
            prop["bloqueios"].append("tema genérico (lixeira) sem confirmação de que a questão trata do conceito geral")
        prop["extras"] = list(dict.fromkeys(x for x in prop["extras"] if x and x != central))
        prop.update(central=central, conf_conteudo=conf_conteudo, conf=round(conf_conteudo * prop["p_conv"], 3))
        out.append(prop)
    return out


def escolher_tau(confs, alvo, piso):
    """Menor limiar (≥ piso) cuja confiança média dos selecionados (= precisão esperada) fica ≥ alvo."""
    for tau in sorted({c for c in confs if c >= piso}):
        sel = [c for c in confs if c >= tau]
        if sum(sel) / len(sel) >= alvo:
            return tau
    return 1.01


def decidir(props, tau):
    tes = thesaurus.tesauro()
    for p in props:
        if p.get("decisao") == "fora":
            continue
        if not p["bloqueios"] and p["conf"] >= tau:
            p["decisao"], p["motivo"] = "publicar", ""
            continue
        p["decisao"] = "revisar"
        if p["bloqueios"]:
            p["motivo"] = "; ".join(p["bloqueios"])
        elif p["p_conv"] < 1 and p["conf_conteudo"] >= tau:
            tipo, nos = p["familia"].split(":")
            p["motivo"] = ("tema em mais de um lugar da árvore (" +
                           " | ".join(tes["nos"][n]["prefLabel"] for n in nos.split("|")) + "); falta a convenção da equipe")
        else:
            p["motivo"] = f"confiança {p['conf']:.2f} abaixo do limiar {tau:.2f}"
            if p["O"] and p["O"] != p["conceito"] and p["O"] != "FORA":
                p["motivo"] += f"; o assunto de origem aponta outro tema ({p['O']})"
            if p["L"] and p["L"] != p["conceito"]:
                p["motivo"] += f"; o tesauro aponta outro tema ({p['L']})"
    for p in props:                                           # o LEIA-ME pede motivo curto
        if len(p.get("motivo", "")) > 180:
            p["motivo"] = p["motivo"][:177].rsplit(" ", 1)[0] + "..."
    return props


def rodar(dados, convencao, params=None):
    pol = config()["politica"]
    props = propor(dados, convencao, params)
    elegiveis = [p["conf"] for p in props if p.get("decisao") != "fora" and not p["bloqueios"]]
    tau = escolher_tau(elegiveis, pol["alvo_precisao"], pol["piso_confianca"])
    return decidir(props, tau), tau


def resumo(props):
    pub = [p for p in props if p["decisao"] == "publicar"]
    return {"publicar": len(pub), "revisar": sum(p["decisao"] == "revisar" for p in props),
            "fora": sum(p["decisao"] == "fora" for p in props), "cobertura": len(pub) / len(props),
            "precisao_esperada": sum(p["conf"] for p in pub) / len(pub) if pub else 0.0,
            "em_familia": sum(p["p_conv"] < 1 for p in pub), "subtema": sum(p["nivel"] == "subtema" for p in pub)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--convencao", default=config()["convencao"])
    args = ap.parse_args()
    tes, dados = thesaurus.tesauro(), carregar()

    cenarios = {}
    for conv in config()["convencoes"]:                       # cenários para o ponto de decisão
        props, tau = rodar(dados, conv)
        r = resumo(props)
        cenarios[conv] = {**r, "tau": tau}
        print(f"[{conv}] τ={tau:.3f} | publicar {r['publicar']} ({r['cobertura']:.1%}) | revisar {r['revisar']} | "
              f"fora {r['fora']} | precisão esperada {r['precisao_esperada']:.1%} | em família {r['em_familia']} | "
              f"no subtema {r['subtema']}")

    (OUT / "cenarios.json").write_text(json.dumps(cenarios, ensure_ascii=False, indent=1), encoding="utf-8")
    props, tau = rodar(dados, args.convencao)
    with open(ROOT / "publicacao.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "decisao", "tema_central_id", "extras_ids", "confianca", "motivo"])
        for p in sorted(props, key=lambda x: x["id"]):
            w.writerow([p["id"], p["decisao"], p["central"], ";".join(p["extras"]), f"{p['conf']:.2f}", p["motivo"]])
    campos = ["id", "decisao", "central", "caminho", "nivel", "extras", "conf", "conf_conteudo", "p_conv", "familia",
              "conceito", "J", "p_n1", "consistente", "verif", "L", "O", "revisor", "revisor_conf",
              "revisor_justificativa", "trocado_pelo_revisor", "penal", "mista", "motivo"]
    with open(OUT / "decisoes_detalhadas.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        for p in sorted(props, key=lambda x: x["id"]):
            w.writerow({**p, "extras": ";".join(p["extras"]),
                        "caminho": tes["nos"][p["central"]]["caminho"] if p["central"] else ""})
    # onde o Jev hesita entre dois temas: candidatos a uma nota "não confundir com" no tesauro
    pares = defaultdict(list)
    for qid, j in dados["jev"].items():
        p = j["n1"]["p"]
        top = [k for k in sorted(p, key=lambda k: -p[k]) if k != NENHUM][:2]
        if len(top) == 2 and p[top[1]] >= 0.1 and p[top[0]] - p[top[1]] < 0.3:
            pares[tuple(sorted(top))].append(qid)
    with open(OUT / "fronteiras_sugeridas.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tema_a", "tema_b", "n_questoes_em_duvida", "exemplos"])
        for (a, b), ids in sorted(pares.items(), key=lambda x: -len(x[1])):
            w.writerow([a, b, len(ids), " ".join(ids[:5])])
    r = resumo(props)
    print(f"pares de temas em que o Jev hesita (fronteiras a escrever no tesauro): {len(pares)}")
    print(f"convenção usada: {args.convencao} | τ={tau:.3f} | publicar {r['publicar']} | revisar {r['revisar']} | "
          f"fora {r['fora']} | cobertura {r['cobertura']:.1%} | precisão esperada {r['precisao_esperada']:.1%}")


if __name__ == "__main__":
    main()
