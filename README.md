# Case Vício IA, etapa 2: classificação de questões com um tesauro, sem LLM na decisão

Classifica as 659 questões de Penal, Processo Penal, Legislação Penal Especial e Criminologia na árvore de temas e
decide **publicar**, **revisar** ou **fora**. A decisão é de um sistema próprio: tesauro, embeddings guardados,
ranqueador treinado nos 100 rótulos e calibração. **Nenhum modelo de linguagem é chamado na hora de classificar.**

| Entregável | Arquivo |
|---|---|
| Decisão por questão (659) | [`publicacao.csv`](publicacao.csv) |
| Previsão de precisão e cobertura (fora da folha-verdade) | [`previsao.txt`](previsao.txt) |
| Relatório: sistema, 100 rótulos, diagnóstico, produção, memo (3 páginas) | [`relatorio.pdf`](relatorio.pdf) ([`relatorio.md`](relatorio.md)) |

**Resultado nas 559 questões avaliadas:**
- **Publicar:** 278 (49,7%), com **96,4% de acerto previsto** (faixa de 95% a 99%).
- **Revisar:** 270, com sugestão de tema e a 2ª opção.
- **Fora:** 11 (Direito Penal Militar e uma lei sem tema na árvore).

A entrega da etapa 1 (Jev + revisor LLM) está na tag [`etapa-1`](../../tree/etapa-1); o código dela, em `legado_etapa1/` (não roda mais).

## Como rodar
1. Baixe os anexos (`anexos-case-ia.zip`, em https://github.com/viciod/case-vicio-ia) e coloque `questoes.jsonl`,
   `temas.csv` e `folha_verdade.csv` em `data/raw/`.
2. Regenere a decisão, **sem rede**:
```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt     # Linux/Mac: .venv/bin/python
.venv/Scripts/python src/run_all.py
```
`run_all.py` bloqueia a rede (qualquer conexão interrompe o processo) e roda as etapas abaixo e o validador em
**~1 minuto** num notebook comum. Ele grava `publicacao.csv` e `previsao.txt` e só lê artefatos versionados.

| Etapa | Arquivo | O que faz |
|---|---|---|
| s01 | `src/s01_preprocess.py` | limpa o HTML; inclui o item de Certo/Errado que vem no `comando` |
| s02 | `src/s02_taxonomy.py` | árvore ativa; lixeiras, "(Parte N)", repetidos, nós novos |
| s03 | `src/s03_tesauro.py` | monta o tesauro: ficha curada + enriquecimento revisado + famílias + 89 conceitos |
| s04 | `src/s04_evidencias.py` | evidência lexical (termos e leis) e assunto de origem |
| s05 | `src/s05_features.py` | similaridades questão × ficha e questão × exemplos do tesauro, para os 89 conceitos |
| s06 | `src/s06_modelo.py` | ranqueador (logística) treinado na folha; validação cruzada 10 × 5; ablações |
| s07 | `src/s07_decisao.py` | calibração isotônica, regras de fora e política (≥ 95% e piso 0,85) → `publicacao.csv` |
| s08 | `src/s08_previsao.py` | previsão com bootstrap da folha → `previsao.txt` |
| — | `src/validar.py` | formato do LEIA-ME e testes do tesauro; `src/verdade.py` tem a régua e os testes da folha |

## Artefatos e de onde vieram
| Artefato | Origem | Como regenerar |
|---|---|---|
| `tesauro/tesauro_curado.txt` | Curadoria da etapa 1: dispositivos, termos e notas de escopo. Escrita com ajuda de LLM e revisada | à mão |
| `tesauro/crosswalk_origem.txt` | Mapa do assunto de origem para a árvore (etapa 1) | à mão |
| `tesauro/tesauro_enriquecido.jsonl` | Proposta do **GPT-6 Luna** (`openai/gpt-6-luna`, 21/10/2026) para 351 fichas: escopo, termos, leis e exemplos de questão. Revisão automática (leis pela regex, anti-vazamento de 8-gramas, duplicatas) e amostra para revisão humana em `out/revisao_tesauro.csv`. Nenhuma questão real foi mostrada ao LLM | `python src/preparar.py` |
| `out/termos_propostos_jev.csv` | 69 termos aceitos pelo Jev na etapa 1, usados como dado | — |
| `artefatos/embeddings.npz` | **qwen/qwen3-embedding-8b** (21/10/2026) das questões, das fichas, dos exemplos e dos assuntos de origem | `python src/preparar.py` |
| `artefatos/modelo.joblib` | Ranqueador treinado pelo `s06` (5 pesos) | `run_all.py` refaz |
| `relatorio.pdf` | `relatorio.md` convertido (pandoc + `docs/relatorio.css`, impressão A4 do Edge) | `pandoc -f gfm relatorio.md --css docs/relatorio.css` e imprimir |

**Preparação (antes da decisão).** `python src/preparar.py` usa o cache (`cache/llm`; os embeddings ficam em cache
local). Com `--chave sk-or-...`, roda **sem o cache**, chamando o Luna e o modelo de embedding de novo, por
~US$ 0,30 e ~10 min. O resultado pode variar um pouco. Depois, rode `run_all.py`.

## Modelos, custo e tempo
| Uso | Modelo | Custo nesta entrega |
|---|---|---|
| Propor o enriquecimento do tesauro (preparação) | `openai/gpt-6-luna` | US$ 0,26 (351 chamadas) |
| Embeddings (preparação) | `qwen/qwen3-embedding-8b` | US$ 0,005 |
| **Decisão** | **nenhum**: logística + isotônica no scikit-learn | US$ 0 (~1 min) |

**Produção, para 50 mil questões por semana:** ~US$ 0,30 de embeddings; a decisão leva ~70 ms por questão num núcleo de CPU (~1 h por semana, sem GPU). Detalhes na seção d)
do relatório.

## Decisões tomadas à mão (e por quê)
1. **Convenção dos nós antigos** nos temas repetidos e nas "(Parte N)": publica no tema original, como a folha
   mostrou em 21 de 22 casos.
2. **Publicar no tema (nível 1).** O gabarito em subtema conta como certo, e descer ao subtema só aumentaria o risco.
3. **Fora por regra forte:**
   - disciplina militar, porque a árvore não tem esse ramo;
   - lei citada sem tema na árvore, quando a confiança é < 0,5.
4. **Régua de 95% sem folga**, com piso de 0,85 de confiança por questão.
5. **Variante do modelo** escolhida numa grade pequena na validação cruzada (ver relatório, seção a).
6. **Teto de 0,98** na calibração: com 100 rótulos, nenhuma questão recebe certeza total.
7. **O curado à mão prevalece** sobre o proposto pelo LLM no tesauro.
8. **Os dados da empresa não vão para o repositório:** `data/raw/` e `cache_req/` ficam fora do git.
