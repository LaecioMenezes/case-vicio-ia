# Case Vício IA: classificação de questões com um tesauro + o Jev

Classifica as 359 questões de Penal, Processo Penal, Legislação Penal Especial e Criminologia na árvore de 375 temas
ativos e decide, para cada uma, **publicar**, **revisar** ou **fora**. A régua: ≥95% de precisão nas publicadas e,
dentro dela, a maior cobertura possível, dependendo o mínimo do professor.

| Entregável | Arquivo |
|---|---|
| Decisão por questão | [`publicacao.csv`](publicacao.csv) |
| Previsão de precisão e cobertura | [`previsao.txt`](previsao.txt) |
| Relatório (raciocínio, diagnóstico, produção, memo ao professor) | [`relatorio.md`](relatorio.md) |
| Explicação visual para quem não é técnico | [`docs/como_resolvemos.pdf`](docs/como_resolvemos.pdf) |

**Resultado:**
- **Publicadas:** 121 das 359 (34%), com **95,6% de acerto previsto**, na faixa de 92% a 97% (no `previsao.txt`,
  0.96, porque o formato pede duas casas). A política publica o maior conjunto com precisão esperada ≥ 95%, a régua do
  case, sem folga.
- **Revisar:** 235, cada uma com sugestão de tema, a justificativa do revisor automático e o motivo. Elas não vão uma
  a uma para o professor: em produção, ficam na prática geral (simulados e listas mistas) e são reavaliadas toda semana.
- **Fora:** 3. Uma é de Direito Tributário (ITCMD) e duas citam leis que não têm tema na árvore (Lei 9.029/95 e Lei
  Geral do Esporte).
- **Cenário alternativo:** se a equipe confirmar que usa o tema original nos temas repetidos, a cobertura sobe para 53%
  com a mesma precisão prevista.

## A ideia
O problema é de vocabulário: a árvore tem temas repetidos, temas fatiados em "Partes", temas genéricos que viraram
lixeira e descrições vazias. A biblioteconomia resolve isso com um **tesauro** (vocabulário controlado, ISO 25964):
uma ficha por tema com os dispositivos de lei, os termos com que ele aparece nas questões e, onde o título não basta,
uma nota de escopo. O **Jev** (TypeSafe) lê cada questão e decide entre os conceitos do tesauro, devolvendo
probabilidades em vez de texto. Um LLM barato (**GPT-6 Luna**) faz a revisão automática: relê a questão, escolhe o tema
com uma justificativa curta e confirma ou contesta o Jev. Para medir o acerto sem gabarito, três testemunhas que erram
por motivos diferentes (o Jev, o tesauro e o assunto do site de origem) são trianguladas.

```
questão ─► tesauro: lei/artigo citado + termos de entrada ──────────────► testemunha L
        ─► assunto do site de origem, cruzado com a árvore ─────────────► testemunha O
        ─► Jev: tema entre 89 conceitos (2 ordens), subtema, verificação, "é penal?", "é mista?" ─► J
        ─► revisor (GPT-6 Luna): tema + justificativa ─► concorda ou discorda do Jev
        ─► triangulação J × L × O: quanto cada um acerta, sem gabarito (calibrada por concorda/discorda)
        ─► política: confiança calibrada × convenção → publicar | revisar | fora
```

## Como rodar
1. Baixe os anexos oficiais do case (`anexos-case-ia.zip`, em https://github.com/viciod/case-vicio-ia) e coloque
   `questoes.jsonl` e `temas.csv` em `data/raw/`. Os dados não são copiados para este repositório.
2. Rode:
```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt        # Linux/Mac: .venv/bin/pip
cp .env.example .env                                 # OPENROUTER_API_KEY só é necessária para chamadas novas
.venv/Scripts/python src/run_all.py
```
**Rodar sem o cache (opcional).** Para conferir que os resultados não dependem do cache, informe a chave da
OpenRouter no comando. Com a chave, o Jev e o revisor são chamados de novo para todas as questões; sem ela, o
pipeline usa o cache.
```bash
.venv/Scripts/python src/run_all.py --chave sk-or-...
```
- São ~2.400 chamadas, ~US$ 0,75 e ~7 minutos. Antes de começar, o script confere a chave e o saldo, e para se o
  crédito não bastar.
- O `cache/` entregue não é lido nem alterado: as respostas novas vão para `cache_ao_vivo/<data-hora>/`, fora do git.
- `publicacao.csv`, `previsao.txt` e `out/` são regravados, e `git diff publicacao.csv previsao.txt` mostra o que
  mudou em relação à entrega. Os modelos podem variar um pouco de uma rodada para outra.

`run_all.py` roda as etapas abaixo e o validador e grava `publicacao.csv` e `previsao.txt` na raiz. Todas as respostas
do Jev e do revisor estão em `cache/` (só as respostas; o texto das questões não é publicado), então **o pipeline se
regenera sem chave nenhuma**, em ~20 segundos e com resultado idêntico (conferido com a chave removida).

| Etapa | Arquivo | O que faz | Modelo |
|---|---|---|---|
| s01 | `src/s01_preprocess.py` | limpa o HTML e monta o texto (sem o `comando`, às vezes sintético, salvo quando ele traz o item de uma Certo/Errado); marca enunciados genéricos e disciplinas suspeitas | — |
| s02 | `src/s02_taxonomy.py` | árvore ativa; marca temas genéricos, "(Parte N)", duplicados e nós novos sem descrição | — |
| s03 | `src/s03_tesauro.py` | **tesauro** a partir de `tesauro/tesauro_curado.txt`: famílias, herança, 89 conceitos, cruzamento com o assunto de origem | — |
| s03b | `src/s03b_jev_tesauro.py` | o Jev ajuda a manter o tesauro: propõe termos tirados das questões, traduz etiquetas de origem, audita termos | Jev |
| s04 | `src/s04_evidencias.py` | as duas testemunhas independentes do Jev: lexical (só termos curados) e de origem | — |
| s05 | `src/s05_jev.py` | **Jev**: tema em duas ordens, subtema, verificação, "é penal?", "é mista?", "é o conceito geral?" | Jev |
| s05b | `src/s05b_jev_sem_tesauro.py` | experimento de controle: o Jev só com os títulos crus da árvore (não entra na decisão) | Jev |
| s05c | `src/s05c_jev_finalistas.py` | experimento: segunda rodada entre os 5 finalistas, em 4 ordens. Não melhorou, então fica desligado (`politica.segunda_rodada` no config) | Jev |
| s05d | `src/s05d_revisor_llm.py` | **revisor automático**: tema entre os 89 conceitos, confiança e justificativa curta | GPT-6 Luna |
| s06 | `src/s06_triangulacao.py` | taxa de acerto de cada testemunha sem gabarito, calibração do Jev (separada por revisor concorda/discorda) e comparação tesauro × Jev | — |
| s07 | `src/s07_politica.py` | política: confiança × convenção, revisor, bloqueios, limiar → `publicacao.csv`; fora quando a questão não é penal, ou cita lei sem tema na árvore e o revisor confirma | — |
| s08 | `src/s08_previsao.py` | previsão com bootstrap da triangulação → `previsao.txt` | — |
| — | `src/validar.py` | confere o formato do LEIA-ME e testa o casamento lexical do tesauro | — |

**Experimentos fora do `run_all`** (usam o cache, não precisam de chave):
- `src/comparar_modelos.py` → `out/comparacao_modelos.csv`: custo, acerto e efeito na decisão de cada revisor testado.
  Para revisar com outro modelo: `python src/s05d_revisor_llm.py --modelo anthropic/claude-haiku-5.5`. No GPT-6.1 Sol
  e no Sonnet 5.5, 3 das 359 respostas são da versão anterior do texto (sem o item do `comando`), porque o crédito da
  API acabou antes de refazê-las.
- `src/comite_revisores.py`: comitê sintético de revisores, que só vota quando todos concordam.

**Os "prompts" são as perguntas aos modelos.** As do Jev estão em `src/s05_jev.py`, com instruções, critérios por opção
e Nouls; os critérios de cada opção vêm do tesauro (`src/thesaurus.py`, função `criterio`). As do revisor estão em
`src/s05d_revisor_llm.py`: as regras e a lista dos 89 temas, também tirada do tesauro, com saída em JSON Schema estrito.

**Saídas para o professor, em `out/`:**
- `tesauro_revisao.csv`: o tesauro numa planilha.
- `termos_propostos_jev.csv`: termos que o Jev propôs, para aprovar.
- `tesauro_auditoria.csv`: termos curados que o Jev achou duvidosos.
- `fronteiras_sugeridas.csv`: pares de temas em que o Jev hesita.
- `decisoes_detalhadas.csv`: todos os sinais de cada questão, com o tema e a justificativa do revisor.
- `cenarios.json`: os cenários de convenção.
- `comparacao_modelos.csv`: a comparação de revisores.

## Modelos, custo e tempo
| Modelo | Papel | Preço (OpenRouter) |
|---|---|---|
| **`typesafe/jev-1.13-20260917`** (Jev 1.13, versão fixa) | decide o tema e mantém o tesauro | US$ 0,042 por milhão de tokens de entrada; a saída é grátis |
| **`openai/gpt-6-luna`** | revisor automático | US$ 0,10 por milhão de tokens de entrada e US$ 0,50 por milhão de saída |

| Rodada real (17/10/2026) | Chamadas | Tokens | Custo |
|---|---|---|---|
| s03b: Jev mantendo o tesauro | 626 | 5,0 mi | US$ 0,21 |
| s05: Jev classificando | ~720 | 7,9 mi | US$ 0,33 |
| s05b: controle sem tesauro | ~360 | 1,6 mi | US$ 0,07 |
| s05c: segunda rodada (experimento) | — | — | US$ 0,06 |
| s05d: revisor GPT-6 Luna | 359 | 2,1 mi de entrada + 77 mil de saída | US$ 0,07 |
| Pesquisa de revisores: Haiku 5.5, GPT-6.1 Sol e Sonnet 5.5, mais as tentativas com Gemini e DeepSeek, que falharam | 1.782 | — | US$ 2,75 |
| Rodada com erro no texto (descartada; as respostas foram apagadas do cache) | 1.953 | — | US$ 0,66 |
| **Total** | | | **~US$ 4,15** |

**Qual revisor.** Com a mesma régua, o GPT-6 Luna publica mais que os modelos caros (121 questões, contra 115 do Sol e
do Sonnet e 116 só com o Jev) por uma fração do preço:

| Revisor | R$ por semana (50 mil questões) | Publicadas |
|---|---|---|
| GPT-6 Luna | R$ 50 | 121 |
| Claude Haiku 5.5 | R$ 106 | 120 |
| GPT-6.1 Sol | R$ 551 | 115 |
| Claude Sonnet 5.5 | R$ 965 | 115 |
| Comitê dos quatro | R$ 1.672 | 104 |

**A conta de produção.** O case pede o desenho para 50 mil questões novas por semana. Em produção, rodam para cada
questão a classificação do Jev (s05, cerca de 22 mil tokens, **US$ 0,0009**) e o revisor (s05d, **US$ 0,0002**):
**US$ 0,0011 por questão**. São 50.000 × US$ 0,0011 = **US$ 56 por semana**, ou cerca de **R$ 290 por semana
(R$ 1.250 por mês)**, com o dólar a ~R$ 5,20 (cotação de fim de setembro de 2026). Do professor, o desenho pede cerca de
1 hora por semana, qualquer que seja o volume, e nenhuma revisão item a item: decisões de regra, aprovação em lote e
auditoria por amostra (ver `relatorio.md`, seção c).

## Decisões tomadas à mão (e por quê)
1. **Curadoria do tesauro** (`tesauro/tesauro_curado.txt`): dispositivos legais, termos de entrada e notas de escopo dos
   temas ambíguos. É assim que se constrói um vocabulário controlado, e o resultado é auditável e editável pelo professor.
2. **Cruzamento do assunto de origem** (`tesauro/crosswalk_origem.txt`), só para os valores que não casam pelo título.
   O Jev mapeou mais 1 dos 10 que sobraram.
3. **Lista de sobreposições entre ramos** em `src/s03_tesauro.py`. Exemplos: interceptação telefônica em Leg. Especial e
   em Provas; juizado especial e procedimento sumaríssimo.
4. **Convenção "conservador"** em `config/politica.json`: temas repetidos e partes não são publicados, porque só a equipe
   sabe qual endereço usou. Para o cenário "nós antigos", troque `"convencao"` no config (ou rode
   `python src/s07_politica.py --convencao nos_antigos`) e depois `python src/s08_previsao.py`.
5. **Alvo de 95%** de precisão esperada, a régua do case, sem folga, e piso de 0,85 de confiança por questão, para não
   publicar questão incerta compensada por outras muito certas. Com 121 publicadas, a régua tolera até 6 erros; o alvo
   de 96% publicaria 115 com risco parecido de passar disso (28% × 29%, só pelo acaso).
6. **Nunca publicar na disciplina (raiz).** A regra aceitaria, mas recriaria a lixeira.
7. **Termos propostos pelo Jev não votam como testemunha.** Eles ajudam o Jev a decidir e vão para aprovação. Se
   votassem, o Jev estaria conferindo a si mesmo.
8. **Revisor automático: GPT-6 Luna** (`revisor_llm` em `config/politica.json`), escolhido pelo custo-benefício. O voto
   dele não é somado como testemunha independente, porque erra junto com o Jev nas questões difíceis: a calibração é
   medida separadamente para "revisor concorda" e "revisor discorda". Com `"usar": false`, volta a versão só com o Jev
   (116 publicadas).
9. **O campo `comando` é descartado**, porque em parte das questões ele foi gerado artificialmente ("Explique...",
   "Indique..."). A exceção é Certo/Errado em que o próprio item a julgar está no comando e o enunciado só diz "julgue
   o próximo item" (3 questões).
10. **Fora para lei sem tema** (`politica.fora_lei_sem_tema` no config): quando a questão cita uma lei que não ancora
   nenhum tema e o revisor também não acha tema. Pega 2 questões.
11. **Os dados da empresa não vão para o repositório.** Ficam fora do git `data/raw/` e o texto das requisições (`cache_req/`).
