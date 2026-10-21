"""Etapa 8: previsão de precisão e cobertura (previsao.txt), antes de conhecer o resultado.

Precisão: a confiança de cada questão publicada já é uma probabilidade calibrada de acerto (s06/s07),
então a precisão esperada é a média delas. Para o intervalo, um bootstrap refaz a triangulação em
reamostras das questões, sorteando também κ (a chance de dois erros coincidirem) numa faixa
plausível, e recalcula a confiança média das MESMAS publicadas.

Para comparar, o número que o Jev daria sozinho: a média das probabilidades dele nas publicadas.

Cobertura: o valor nas 359 é exato (é a nossa própria decisão); o intervalo cobre o caso de a
avaliação usar só um subconjunto das questões.
"""
import random

import numpy as np

from common import ROOT, config
from s06_triangulacao import estimar, votos
from s07_politica import carregar, propor, resumo, rodar

B = 1000


def main():
    cfg = config()
    conv, tri = cfg["convencao"], cfg["triangulacao"]
    dados = carregar()
    props, tau = rodar(dados, conv)
    pub = [p for p in props if p["decisao"] == "publicar"]
    ids_pub = {p["id"] for p in pub}
    r = resumo(props)
    cobertura = r["cobertura"]
    prev = r["precisao_esperada"]
    jev_bruto = float(np.mean([p["p_n1"] for p in pub])) if pub else 0.0

    linhas = votos(dados["jev"], dados["ev"], dados.get("fin"), dados.get("rev"))
    rng = random.Random(42)
    medias, aJs = [], []
    for _ in range(B):
        amostra = [rng.choice(linhas) for _ in linhas]
        kappa = rng.uniform(*tri["kappa_faixa"])           # chance de dois erros coincidirem
        rho = rng.uniform(*tri["rho_L_faixa"])             # quão independente o tesauro é do Jev
        teto = rng.uniform(*tri["teto_faixa"])             # erro que nenhuma testemunha enxerga
        try:
            params = estimar(amostra, kappa, rho, teto)
        except (ValueError, ZeroDivisionError):
            continue
        confs = {p["id"]: p["conf"] for p in propor(dados, conv, params) if p["id"] in ids_pub}
        if confs:
            medias.append(float(np.mean(list(confs.values()))))
            aJs.append(params["aJ"])
    p_lo, p_hi = np.percentile(medias, [5, 95]) if medias else (prev, prev)
    a_lo, a_hi = np.percentile(aJs, [5, 95]) if aJs else (0, 0)
    n_sub = 240                                   # caso a avaliação use ~2/3 das questões
    delta = 1.645 * np.sqrt(cobertura * (1 - cobertura) / n_sub)
    c_lo, c_hi = max(0.0, cobertura - delta), min(1.0, cobertura + delta)
    P = dados["params"]

    texto = f"""precisao_prevista: {prev:.2f}
precisao_intervalo: {p_lo:.2f}-{p_hi:.2f}
cobertura_prevista: {cobertura:.2f}
cobertura_intervalo: {c_lo:.2f}-{c_hi:.2f}

Como cheguei nesses números

Cobertura. Publicamos {r['publicar']} das {len(props)} questões ({cobertura:.1%}); {r['revisar']} ficam em "revisar" (em produção:
prática geral, reavaliadas automaticamente, sem esperar o professor) e {r['fora']} {'fica' if r['fora'] == 1 else 'ficam'} fora.
Se a avaliação usar as 359, a cobertura é exatamente essa; o intervalo (90%, binomial) cobre o caso de a
avaliação usar só um subconjunto (~{n_sub} questões).

Precisão. Não há gabarito. O Jev decide o tema e um LLM barato (GPT-6 Luna) faz a revisão automática. Para
medir sem gabarito, usamos duas testemunhas independentes: o tesauro (lei/artigo citado e termos de entrada
achados no texto) e o assunto que o site de origem deu à questão. Nenhuma das três é gabarito, mas elas erram por motivos
diferentes; a frequência com que cada par concorda revela a taxa de acerto de cada uma (método das três
testemunhas, Dawid & Skene, 1979). Nas {P['n_trio']} questões em que as duas testemunhas votam:

- concordância Jev × tesauro {P['pJL']:.0%}, Jev × origem {P['pJO']:.0%}, tesauro × origem {P['pLO']:.0%};
- taxa de acerto estimada: Jev {P['aJ']:.0%} (90%: {a_lo:.0%}–{a_hi:.0%}), tesauro {P['aL']:.0%}, assunto de origem {P['aO']:.0%}.

A mesma conta, feita por faixa de probabilidade do Jev, calibra a confiança dele, separadamente para quando
o revisor LLM concorda e quando discorda (os dois erram juntos com frequência, então o voto do revisor não é
somado como testemunha independente: medimos direto quanto acerta cada caso). Em cada questão, a testemunha
que concorda aumenta a confiança e a que discorda diminui (Bayes). Multiplicamos pela chance
de a convenção bater quando o tema existe em mais de um lugar da árvore. Publicamos o maior conjunto com
confiança média ≥ {cfg['politica']['alvo_precisao']:.0%} e piso de {cfg['politica']['piso_confianca']:.2f} por questão (limiar {tau:.2f}).

- Precisão esperada das publicadas: {prev:.1%} (média das confianças; no cabeçalho, arredondada a duas casas, como
  pede o LEIA-ME). A régua do case é 95%.
- Só pelas probabilidades do Jev, sem triangulação, seria {jev_bruto:.1%}.
- Intervalo de 90%: bootstrap de {len(medias)} reamostras das questões, refazendo a triangulação e
  sorteando as hipóteses do método: κ entre {tri['kappa_faixa'][0]:.2f} e {tri['kappa_faixa'][1]:.2f}, o peso do voto do tesauro
  (ρ entre {tri['rho_L_faixa'][0]:.1f} e {tri['rho_L_faixa'][1]:.1f}) e o teto de confiança por questão (entre {tri['teto_faixa'][0]:.0%} e {tri['teto_faixa'][1]:.0%}: o erro
  que nenhuma testemunha enxerga, como a convenção da equipe ou ruído no gabarito): {p_lo:.1%}–{p_hi:.1%}.

Riscos que podem nos tirar do intervalo: (1) as testemunhas não são totalmente independentes (o Jev e o
tesauro leem o mesmo texto; se uma citação de lei engana os dois, a concordância superestima o acerto);
(2) a equipe pode ter convenções diferentes das nossas nos temas duplicados e nas partes "(Parte N)" (por
isso essas questões foram para revisão; convenção usada: "{conv}"); (3) o gabarito da equipe pode diferir
do que um leitor atento do texto escolheria, por exemplo no uso de temas genéricos.
"""
    (ROOT / "previsao.txt").write_text(texto, encoding="utf-8")
    print(texto)
    print("Curva confiança × cobertura:")
    eleg = sorted((p["conf"] for p in props if p.get("decisao") != "fora" and not p["bloqueios"]), reverse=True)
    for t in (0.80, 0.85, 0.90, 0.93, 0.95, 0.97):
        sel = [c for c in eleg if c >= t]
        print(f"  limiar {t:.2f}: cobertura {len(sel) / len(props):.1%} | precisão esperada "
              f"{(np.mean(sel) if sel else float('nan')):.1%}")


if __name__ == "__main__":
    main()
