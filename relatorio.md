# Relatório, etapa 2: classificação com um tesauro, sem LLM na decisão

Nas 559 questões avaliadas, o sistema publica **278 (49,7%)**, com **96,4% de acerto previsto (faixa de 95% a 99%)**.
Mandamos 270 para revisar e 11 para fora. **Nenhum modelo de linguagem é chamado na decisão:** `src/run_all.py`
bloqueia a rede e regenera tudo em ~1 minuto.

## a) O sistema

| Peça | O que faz e por quê |
|---|---|
| **Limpeza** (`s01`) | Tira o HTML. Em Certo/Errado, inclui o item que vem no `comando`; em 3 questões, ele só existia ali |
| **Árvore** (`s02`) | Marca lixeiras, "(Parte N)", temas repetidos e nós novos sem descrição |
| **Tesauro** (`s03`, `tesauro/`) | Uma ficha por tema (ISO 25964). Ver detalhe abaixo da tabela. É o conhecimento do sistema |
| **Embeddings** (`prep_embeddings`) | qwen3-embedding-8b das questões, das fichas e dos exemplos, gravados em `artefatos/embeddings.npz` |
| **Ranqueador** (`s05`, `s06`) | Para cada questão e cada um dos 89 temas: similaridade com a ficha e com os exemplos. Regressão logística com 5 pesos |
| **Calibração e regra** (`s07`) | Isotônica sobre a probabilidade do 1º tema (teto 0,98). Publica o maior grupo com precisão esperada ≥ 95%, sem nenhuma questão abaixo de 0,85. Fora só por regra forte |

**A ficha do tesauro tem:**
- os termos curados (1.512) e as leis;
- as famílias de temas repetidos e fatiados;
- escopo, termos (2.222), leis (408) e exemplos de questão (2.098) propostos pelo GPT-6 Luna.

**O LLM entrou só antes da decisão.** As propostas do Luna passaram por revisão automática:
- regex das leis;
- descarte de exemplos com 30%+ de 8-gramas iguais aos de uma questão real (8 descartados);
- o curado à mão prevalece;
- cada campo guarda a sua origem.

O Luna nunca viu as questões do case. Os 69 termos que o Jev aceitou na etapa 1 entraram como dado.

**Testado e descartado** (acerto do 1º tema, validação cruzada 10 × 5 na folha):

| Variante | Acerto |
|---|---|
| Embedding só do título do tema (sem tesauro) | 67% |
| Embedding da ficha do tesauro | 79% |
| **+ exemplos do tesauro (escolhido)** | **79%, e 98% nos 40% mais confiantes** |
| + léxico explícito, origem, disciplina ou kNN nos rótulos | 74–75%: pioram por sobreajuste; os termos já estão na ficha |
| Calibração logística | nunca passava de 0,9: não publicava nada |
| Etapa 1 (Jev decidindo) | proibida pela regra nova; está na tag `etapa-1` |

Escolhi a variante numa grade pequena na mesma validação cruzada. Esse viés de seleção leve está coberto pelo
intervalo da previsão.

## b) Os 100 rótulos

**Uso:**
1. **Treino:** os 5 pesos.
2. **Calibração:** a isotônica sobre as previsões fora da dobra.
3. **Teste e previsão:** validação cruzada 10 × 5. Nenhuma questão é medida pelo modelo que a viu.

**O que mostraram:**
- **Temas repetidos e partes:** a equipe usa o **nó original** em 21 de 22 casos. Publicamos sempre no nó-base.
- **Fora da taxonomia:** **8%**, inclusive questões que parecem classificáveis. Publicar uma delas é erro, e é o
  principal limite: o ranqueador dá a elas confiança menor (0,61 contra 0,77), mas não o bastante para separá-las.
- **Extras e subtemas:** 39% têm extras, que também contam como acerto. O gabarito é subtema em 39%. Como publicar no
  tema-pai conta como certo, publicamos no tema.
- **Lexical e origem:** só o tesauro lexical acerta 78% das 55 em que se manifesta; o assunto de origem acerta 47%.

## c) Diagnóstico

**O que atrapalha:**
- assunto de origem errado em metade dos casos;
- item escondido no `comando`;
- 10 questões de Direito Penal Militar, ramo inexistente na árvore (vão para fora);
- leis sem tema (Lei 9.029/95, Lei Geral do Esporte);
- temas repetidos, "Partes" sem recorte, lixeiras e 20 temas novos sem descrição.

**O que o sistema ainda erra, e o que resolveria:**

| Tipo de erro | O que resolveria |
|---|---|
| Questões "fora" que parecem classificáveis | Uma regra escrita da equipe para "fora" e mais exemplos |
| "Assinale a correta" com temas misturados | Exemplos mistos no tesauro e o 2º tema como extra |
| Caso narrativo em que o crime da história não é o assunto | Exemplos desse formato nas fichas |
| Fronteiras finas do CPP | Notas "não confundir com" do professor |

A folha só tem questões antigas. As novas (Q0360+) publicam 54%, contra 45% das antigas, e esse é o maior risco para a
previsão.

## d) Produção (50 mil questões por semana)

**Custo e tempo:**
- **Embedding das questões novas:** ~US$ 0,30 por semana.
- **Decisão:** ~70 ms por questão num núcleo de CPU, ~1 hora por semana, paralelizável, sem GPU.
- **Refazer o tesauro inteiro:** ~US$ 0,30, quando a árvore muda.

**A correção do professor vira dado:**
- a questão corrigida entra como **exemplo rotulado** na ficha do tema;
- termos e "não confundir com" apontados entram no tesauro.

**Retreino:**
- **Toda semana:** pesos e calibração, em segundos. Só entra em produção se a validação cruzada mantiver ≥ 95%.
- **Todo mês:** auditoria por amostra.
- **Reporte de aluno:** devolve a questão à revisão.

## Previsão

- **Publicar:** 278 de 559 (49,7%; faixa de 44% a 55% se a avaliação usar só parte delas).
- **Precisão esperada:** 96,4%, com faixa de 95% a 99% pelo bootstrap das 100 questões, que refaz calibração e limiar
  e sorteia os acertos.
- **Conferência direta:** o mesmo limiar, na validação cruzada, publica metade da folha com 97,5% de acerto.

**Com mais tempo:**
- regra de "fora" da equipe;
- rótulos de questões novas;
- revisão humana das fichas;
- subtema quando a confiança for alta.

**Custo da etapa:** US$ 0,27.

## e) Memo para o professor

**Professor,**

Montamos um sistema que coloca as questões nos temas **sem usar IA na hora de decidir**. Ele compara cada questão com
uma ficha por tema (o que o tema cobre, termos e leis típicas, exemplos) e aprende com as 100 questões que a equipe já
classificou. Das 559 a avaliar, **278 vão direto ao aluno**, com acerto previsto de 96%. **11 ficam fora**: 10 de
Direito Penal Militar, que não tem ramo na árvore, e 1 sobre a Lei Geral do Esporte. **270 vão para a sua revisão**
com uma sugestão.

**O que encontramos:**
- temas repetidos e fatiados em "Partes" (a equipe usa o tema original, e o sistema também);
- temas genéricos que atraem questões alheias;
- 8% de questões consideradas fora mesmo parecendo classificáveis;
- o assunto do site de origem acerta só metade das vezes.

**O que recomendamos:**
1. Um endereço por assunto, e as "Partes" juntadas ao tema original.
2. Escopo escrito nos temas genéricos.
3. Criar o ramo de Direito Penal Militar e temas para as leis que faltam.
4. Escrever o critério de "fora".

**Do que precisamos do senhor:**
1. Corrigir as revisões: cada correção vira exemplo, e o sistema aprende na semana seguinte.
2. Aprovar em lote as fichas dos temas (`out/revisao_tesauro.csv`).
3. Conferir uma amostra das publicadas por mês.
