# Relatório: classificação de questões por tema (Case de IA · Método VDE)

**Em cinco linhas.** Tratei o case como um problema de **vocabulário**: a árvore tem temas repetidos, temas fatiados em
"Partes", temas genéricos que viraram lixeira e descrições vazias. A biblioteconomia resolve isso com um **tesauro**
(vocabulário controlado, ISO 25964). O **Jev** (TypeSafe) lê cada questão e decide entre os conceitos do tesauro, com
probabilidades; um LLM barato (**GPT-6 Luna**) faz a revisão automática. Publicamos **121 das 359 questões (34%)**, com
**95,6% de acerto previsto (faixa de 92% a 97%)**, na régua de 95% do case, sem folga. O desenho **não depende de
revisão questão a questão pelo professor**. Com uma única decisão de cadastro sobre os temas repetidos, a cobertura vai a
**53%**. Custo total desta entrega: ~US$ 4,15.

## a) Como pensei

**1. O problema é de vocabulário.** A árvore tem:
- 20 temas novos sem descrição (IDs 6716 a 6738);
- 8 pares de temas repetidos em dois ramos (ex.: "Lei Maria da Penha" em Legislação Especial e em Penal);
- 6 temas fatiados em "(Parte N)" ao lado do tema original;
- 17 temas genéricos e descrições do tipo "Subtema de X. N questões no source".

Pela regra do case, publicar no gêmeo ou na parte errada é erro. Um modelo melhor não resolve isso; um vocabulário
controlado resolve. Daí o tesauro.

**2. O tesauro.** Cada um dos 375 temas virou uma ficha (`tesauro/tesauro_curado.txt`): os dispositivos legais que o
ancoram (ex.: Peculato, CP arts. 312-313), os termos com que ele aparece nas questões e, onde o título não basta, uma
nota de escopo. O código monta as famílias de nós concorrentes (gêmeos, partes, homógrafos como Ação Penal no CP e no
CPP, sobreposições entre ramos) e os **89 conceitos** que o Jev vê, com gêmeos e partes unidos ao tema original. O Jev
ajuda a manter o tesauro: propôs 69 termos tirados das questões, marcou 135 termos curados como duvidosos e apontou 58
pares de temas que se confundem.

**3. O Jev e as fraquezas dele.** O Jev escolhe entre opções e dá a probabilidade de cada uma (US$ 0,042 por milhão
de tokens). Ele lê ao pé da letra, funciona melhor em inglês e tende a escolher a primeira opção. O desenho responde a
isso:
- critério de cada opção vindo do tesauro, com nota de escopo em inglês;
- gêmeos unidos num conceito só;
- duas ordens para cada escolha;
- uma pergunta de verificação.

**4. Medir sem gabarito.** Usei a **triangulação** entre três testemunhas que erram por motivos diferentes: o Jev, o
tesauro (lei e termos citados) e o assunto que o site de origem deu à questão. A frequência com que cada par concorda
revela a taxa de acerto de cada uma (Dawid & Skene, 1979). O mesmo cálculo, por faixa de probabilidade, calibra a
confiança do Jev. Os termos propostos pelo Jev não votam, e o revisor LLM não é somado como testemunha independente,
porque erra junto com o Jev. Medimos direto quanto acerta cada caso: "revisor concorda" e "revisor discorda".

**5. O que testei.**

| Teste | Resultado |
|---|---|
| Jev **sem** tesauro × **com** tesauro | acerto 67% × 71% (diferença pequena); respostas estáveis 79% × **88%** |
| Tesauro sozinho | ~90% de acerto quando se manifesta, mas só se manifesta em 177 das 359 |
| Voto vindo só da lei citada | ~52%: o artigo citado costuma ser o do crime da história, não o da pergunta |
| Segunda rodada do Jev, só com os 5 finalistas | não melhorou (71% × 71%): descartada |
| Questões em que o Jev muda de resposta / não confirma o tema | ~55% / ~45% de acerto: não são publicadas |

**Qual IA revisa melhor por real gasto.** Testei quatro LLMs como revisor, e comitês deles, na mesma tarefa e com a
mesma régua de fora (o assunto de origem, corrigido pelo erro dele, nas questões em que o modelo indica um tema). O
custo por semana considera 50 mil questões, com o dólar a R$ 5,20.

| Revisor | R$ por semana | Acerto sozinho | Acerto quando concorda com o Jev | Publicadas |
|---|---|---|---|---|
| (nenhum: só Jev) | — | 71% | — | 116 |
| **GPT-6 Luna** | **R$ 50** | 74% | 83% | **121** |
| Claude Haiku 5.5 | R$ 106 | 73% | 87% | 120 |
| GPT-6.1 Sol | R$ 551 | 78% | 91% | 115 |
| Claude Sonnet 5.5 | R$ 965 | 77% | 86% | 115 |
| Comitês (Sol + Sonnet; os 4 LLMs) | R$ 1.500 a 1.700 | — | 93% | 104 a 110 |

O Luna dá o maior ganho, por uma fração do preço. **Mesmo quando os cinco modelos (o Jev e os quatro
LLMs) concordam, o acerto fica em ~93%**: somar modelos não basta para publicar o resto com 95%.

**6. Becos sem saída.**
- **Desenhos com vários LLMs gerando o tesauro e rotulando:** troquei por conhecimento curado e um modelo de decisão.
- **Comitês de modelos fortes:** publicam menos, porque se abstêm quando discordam.
- **O assunto de origem como rótulo:** acerta ~49% das vezes.
- **As contagens "N questões no source" como ponto de partida:** estão infladas pelas lixeiras.
- **Publicar na disciplina (raiz):** a regra aceitaria, mas recriaria a lixeira.
- **Assumir que a equipe usou os temas antigos:** daria 53%, mas só fica acima de 95% se pelo menos 98% dessas questões
  estiverem mesmo neles.
- **Notas de fronteira em lote:** as hesitações estão espalhadas por 58 pares, quase todos com uma questão só.
- **Descartar sempre o campo `comando`** (às vezes ele é sintético): escondia o item de 3 questões Certo/Errado. Uma
  delas estava publicada em "Homicídio", mas o item cobra concurso de pessoas. Agora o comando entra quando traz o item.

## b) Diagnóstico

**Dados.**
- **Formato:** 255 questões de cinco alternativas, 46 de quatro, 58 de certo/errado.
- **Enunciados genéricos:** 67 ("assinale a correta").
- **Disciplina de origem estranha ao recorte:** 8, incluindo uma de Direito Tributário sobre ITCMD (fora).
- **Item no lugar errado:** em 3 questões Certo/Errado, o item a julgar está no campo `comando`, e o enunciado só diz
  "julgue o próximo item".
- **Leis sem tema na árvore:** 2 questões (Lei 9.029/95, discriminação de gestante no trabalho; Lei 14.597/2023, Lei
  Geral do Esporte), que vão para fora.
- **Assunto de origem:** vazio em 18 e certo só em cerca de metade das demais.

**Árvore.** Temas repetidos, partes sem recorte, temas genéricos e erros de digitação ("Estaturo", "Comeptência").

**O que é difícil, e por quê.**
1. **Caso narrativo em que o crime citado não é o assunto.** Na Q0157, a pergunta é o prazo da prisão temporária, e
   as palavras apontam "Saúde Pública".
2. **"Assinale a correta" com alternativas de temas diferentes.**
3. **Fronteiras do CPP.** Exemplos: suspeição do juiz entre "Sujeitos" e "Exceção de Suspeição"; direitos do ofendido
   entre "Sujeitos" e "Declaração do Ofendido". Na conferência manual de 12 publicadas, 10 estavam claramente certas e
   2 caíram nessas fronteiras.
4. **Temas repetidos e fatiados:** o conteúdo está certo e o endereço é incerto.
5. **Temas genéricos.**

**Por que 235 não foram publicadas.**
- 95 caem em temas repetidos ou partes: os cinco modelos concordam no conteúdo de 81 delas, falta só o endereço;
- 77 têm confiança baixa;
- 63 dispararam um alarme do Jev ou do revisor.

## c) Produção (50 mil questões por semana): zero revisão item a item

O professor é escasso, então **nenhuma questão espera por ele**. Cada questão segue este caminho:
1. Importação e limpeza: duplicatas detectadas por embeddings herdam o tema já validado; o item de Certo/Errado que
   vem no campo `comando` entra no texto.
2. Evidências do tesauro.
3. Jev.
4. Revisor LLM (GPT-6 Luna), que dá sugestão e justificativa.
5. Triangulação e política.
6. Desfecho:
   - **publicar**, quando passa a régua de 95%;
   - **fora**, quando nenhum tema serve: a questão não é penal, ou cita uma lei sem tema e o revisor confirma. No
     segundo caso, vira um alerta de "tema faltando" para o professor;
   - **prática geral**, no lugar da fila do professor. A questão fica em simulados e listas mistas, onde o tema não
     importa, e é reavaliada toda semana com o tesauro e as convenções atualizados. Os **sinais dos alunos** também
     contam: o desempenho de quem domina cada tema e os reportes. Quando a evidência passa a régua, a questão é
     publicada sozinha.

Reporte de aluno numa questão publicada a devolve à prática geral e reabre a análise.

**Do professor: cerca de 1 hora por semana, qualquer que seja o volume, sem revisão item a item.**
1. **Decisões que valem por centenas de questões**, tomadas uma vez: qual dos temas repetidos vale, o que entra em
   cada "Parte" e quais temas criar quando chega um alerta de tema faltando. Aqui, a decisão sobre os repetidos
   publica mais 69 questões.
2. **Aprovar em lote** as sugestões do Jev para o tesauro.
3. **Auditoria por amostra:** cerca de 50 publicadas por semana; em um mês, 200, o que mede a precisão com ±3 pontos.

| Tipo de IA | Usaria? | Onde e por quê |
|---|---|---|
| **Jev** | Sim, em todas | Decisão de tema e alarmes |
| **Tesauro** | Sim, em todas | O conhecimento: o Jev sugere, o professor aprova em lote |
| **LLM revisor (GPT-6 Luna)** | Sim, em todas | Segunda opinião com justificativa; troca a sugestão do Jev quando é mais provável |
| **Embeddings** | Sim, na importação | Duplicatas entre bancas herdam o tema validado |
| **Classificador treinado** | Depois | Com milhares de questões auditadas: mais uma testemunha e atalho para os casos fáceis |
| **Agentes** | Não | O fluxo é fixo e auditável |
| **Revisão humana** | Mínima | Decisões de regra, aprovação em lote e amostra; nada item a item |

**Custo, na conta.**
- **Por questão:** Jev US$ 0,0009 + Luna US$ 0,0002 = **US$ 0,0011**.
- **50.000 questões por semana:** **US$ 56**, ou **R$ 290 por semana** (~R$ 1.250 por mês), com o dólar a ~R$ 5,20.
- **Professor:** custo fixo de ~1 hora por semana.

**Qualidade contínua.**
1. A auditoria por amostra mede a precisão real.
2. A triangulação semanal serve de alarme de deriva.
3. Os reportes de alunos são acompanhados por tema.
4. Um detector de lixeira avisa quando um tema genérico recebe volume anormal.
5. A recalibração mensal ajusta o limiar para manter a precisão ≥ 95%.

## Resultado e previsão

| Cenário | Publicadas | Precisão prevista |
|---|---|---|
| **Entregue:** temas repetidos e partes aguardam a decisão de cadastro | 121 (34%) | 95,6% (92% a 97%) |
| Depois da decisão de cadastro (tema original nos repetidos) | 190 (53%) | 95,6% |

A previsão (`previsao.txt`) é a média das confianças calibradas das publicadas; no cabeçalho do arquivo ela aparece
como 0.96, porque o LEIA-ME pede duas casas. O intervalo vem de um bootstrap que refaz a triangulação sorteando as
hipóteses do método.

**A régua, sem folga.** Publicamos o maior conjunto com precisão esperada ≥ 95%, a régua do case, e nenhuma questão
com confiança abaixo de 0,85. Com 121 publicadas, a régua tolera até 6 erros. A chance de passar disso só pelo acaso é
de ~28%, antes de somar a incerteza da calibração; com o alvo de 96%, seriam 115 publicadas e risco parecido (29%).
Tirar também o piso daria 126 publicadas, mas com risco de 42%.

**Com mais tempo.**
- Obter da equipe a decisão sobre os temas repetidos.
- Escrever e aprovar as notas de fronteira.
- Validar a triangulação com uma amostra pequena conferida por especialista.
- Testar os sinais dos alunos para reclassificar as questões da prática geral.

**Custo da entrega:**
- Jev: US$ 0,67, incluindo os experimentos.
- Luna na entrega: US$ 0,07.
- Pesquisa de modelos: US$ 2,75, incluindo as tentativas com Gemini e DeepSeek, que falharam.
- Uma rodada com erro no texto, descartada: US$ 0,66.

## d) Memo para o professor

**Professor,**

Classificamos as 359 questões de Penal, Processo Penal, Legislação Especial e Criminologia. **121 podem ir direto ao
aluno**, com acerto previsto de 95,6% (a régua é 95%). **Três ficam fora**: uma não é de Direito Penal (isenção de ITCMD) e duas tratam
de leis que não têm tema na árvore. As outras **235 não pedem revisão do senhor uma a uma**: ficam na prática geral
(simulados e listas mistas) com a sugestão de tema e a justificativa do revisor automático, e são publicadas sozinhas
quando a evidência for suficiente.

**O que encontramos.** A maior parte das dúvidas vem da lista de temas.
- Há temas **repetidos** em dois lugares, como "Lei Maria da Penha" em Legislação Especial e em Penal.
- Há temas **fatiados** em "Parte 1" e "Parte 2" sem recorte.
- Há temas **genéricos** que atraíram questões que não eram deles.
- O **assunto que veio do site de origem** acerta só cerca de metade das vezes.
- **Faltam temas** para algumas leis cobradas em prova.

**O que recomendamos mudar nos temas.**
1. Um único endereço por assunto.
2. Dizer o que cobre cada "Parte", ou juntá-las ao tema original.
3. Uma frase de escopo em cada tema genérico.
4. Corrigir os erros de digitação.
5. Criar temas para as leis que não têm lugar na árvore, começando pela Lei 9.029/95 (discriminação no trabalho) e
   pela Lei Geral do Esporte (Lei 14.597/2023).

**Do que precisamos do senhor: cerca de 1 hora por semana, nunca questão por questão.**
1. **Uma decisão, uma vez:** quais dos temas repetidos valem. Isso publica sozinho mais 69 questões agora (cobertura
   de 34% para 53%) e todas as futuras desses temas.
2. **Cerca de 30 minutos por semana** aprovando em lote as sugestões para o dicionário de temas
   (`out/termos_propostos_jev.csv`, `out/tesauro_auditoria.csv`, `out/fronteiras_sugeridas.csv`).
3. **Cerca de 30 minutos por semana** conferindo uma amostra das publicadas, para medirmos com números a régua de 95%.
