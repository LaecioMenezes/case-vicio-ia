"""Folha-verdade (100 questões rotuladas pela equipe) e a régua de acerto do case.

Regra do LEIA-ME: publicar no tema central, num extra ou num nó do mesmo ramo de um deles (pai ou filho) conta como
certo; publicar uma questão que a equipe marcou como fora da taxonomia é erro.

Rodar este arquivo mede o baseline sem modelo nenhum (testemunha lexical do tesauro e assunto de origem) na folha.
"""
from common import RAW, INTERIM, Tree, read_csv, read_jsonl


def carregar_folha():
    """{id: {"central": tema_id|None, "extras": [tema_id], "fora": bool}}"""
    out = {}
    for r in read_csv(RAW / "folha_verdade.csv"):
        out[r["id"]] = {"central": r["tema_central_id"] or None,
                        "extras": [x for x in r["extras_ids"].split(";") if x],
                        "fora": r["fora_da_taxonomia"] == "1"}
    return out


def acerta(tree, publicado, linha):
    """True se publicar `publicado` nessa questão conta como certo pela regra do case."""
    if linha["fora"] or not publicado:
        return False
    alvos = [g for g in [linha["central"], *linha["extras"]] if g and str(g) in tree.nodes]
    return any(tree.acerto(publicado, g) for g in alvos)


def medir(tree, folha, previstos):
    """previstos: {id: tema_id ou None (não publica)}. Devolve publicadas, certas e precisão."""
    pub = {q: p for q, p in previstos.items() if q in folha and p}
    certas = sum(acerta(tree, p, folha[q]) for q, p in pub.items())
    return {"publicadas": len(pub), "certas": certas, "precisao": certas / len(pub) if pub else 0.0,
            "cobertura": len(pub) / len(folha)}


def _testes(tree):
    folha = carregar_folha()
    q12 = folha["Q0012"]                                  # central 5562 (Apelação), extras 4701; 5569
    assert acerta(tree, "5562", q12)                      # o próprio central
    assert acerta(tree, "5560", q12)                      # pai do central (Recursos em Espécies)
    assert acerta(tree, "4701", q12)                      # um extra
    assert not acerta(tree, "5561", q12)                  # subtema irmão do central: erro
    assert not acerta(tree, "5560", folha["Q0002"])       # fora da taxonomia: publicar é erro


def main():
    import thesaurus
    tree = Tree()
    _testes(tree)
    folha = carregar_folha()
    ev = {r["id"]: r for r in read_jsonl(INTERIM / "evidencias.jsonl")}
    base = lambda k: thesaurus.no_base(k) if k and k != "FORA" else None
    for nome, prev in (("tesauro (lexical)", {q: base(ev[q]["L"]) for q in folha}),
                       ("assunto de origem", {q: base(ev[q]["O"]) for q in folha}),
                       ("tesauro, senão origem", {q: base(ev[q]["L"] or ev[q]["O"]) for q in folha})):
        m = medir(tree, folha, prev)
        print(f"baseline {nome:24s}: publica {m['publicadas']:3d} de 100 | certas {m['certas']:3d} | "
              f"precisão {m['precisao']:.1%}")
    print("testes da régua: ok")


if __name__ == "__main__":
    main()
