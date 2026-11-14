# Tech Challenge — Fase 4 | Amazon Insights

Preparação da base **Amazon Sales Dataset**, com dados de produtos, preços, descontos, avaliações e comentários para o dashboard em Power BI. Análise acadêmica pontual.

## Pipeline

```bash
python -m pip install -r requirements.txt
python src/dataprep.py --input amazon.csv --output-dir data/processed
python -m unittest discover -s tests -v
```

Os arquivos processados são publicados na pasta `data/processed` pelo [GitHub Actions](https://github.com/rodrigoscalioni/tech-challenge-fase-4/actions/workflows/prepare-data.yml). A automação utiliza um *commit* fixo do CSV de referência, confere seu SHA-256, executa o tratamento e versiona os resultados. Não é necessário instalar Python no computador para consumi-los no Power BI.

## Fontes para o Power BI

No Power BI Desktop use **Obter dados → Web** com autenticação **Anônima** (repositório público):

| Tabela | Link direto |
|---|---|
| `products` | [products.csv](https://raw.githubusercontent.com/rodrigoscalioni/tech-challenge-fase-4/main/data/processed/products.csv) |
| `review_bundles` | [review_bundles.csv](https://raw.githubusercontent.com/rodrigoscalioni/tech-challenge-fase-4/main/data/processed/review_bundles.csv) |
| `temas_avaliacoes` | [temas_avaliacoes.csv](https://raw.githubusercontent.com/rodrigoscalioni/tech-challenge-fase-4/main/data/processed/temas_avaliacoes.csv) |
| Relatório de qualidade | [quality_report.json](https://github.com/rodrigoscalioni/tech-challenge-fase-4/blob/main/data/processed/quality_report.json) |

**Configuração do modelo:**

- `products[product_id]` (1) → `review_bundles[product_id]` (*), relacionamento ativo, direção única.
- `review_bundles[id_bloco_avaliacao]` (1) → `temas_avaliacoes[id_bloco_avaliacao]` (*), relacionamento ativo, direção única.
- Não criar ligação adicional direta de `products` para `temas_avaliacoes`, para evitar caminhos ambíguos.
- Formate `desconto_percentual` como percentual. Preços são em **INR**, não BRL.
- Na importação em português (Brasil), converta colunas decimais **usando localidade Inglês (Estados Unidos)**; a conversão automática pode transformar `4.1` em `41` ou `0.58` em `58`. Confira `rating`, preços e descontos antes de aplicar.

**Atenção ao Power BI já iniciado:** a v2 traduz os nomes **derivados**. Os nomes de origem como `product_id`, `product_name`, `category`, `rating`, `rating_count`, `review_id` e `review_content` permanecem iguais. Para atualizar consultas antigas, revise as etapas `Tipo Alterado` e qualquer referência aos nomes de campos derivados anteriores. Para recomeçar, importe as três tabelas da v2.

## Arquivos e granularidade

- `products.csv` — **1.351 produtos únicos**; uma linha por `product_id`. Inclui categorias hierárquicas, preços, descontos, notas, `rating_count` e flags de conflito.
- `review_bundles.csv` — **1.370 blocos de comentários**; várias linhas podem estar relacionadas ao mesmo produto e cada bloco pode reunir diversas avaliações. Inclui colunas derivadas de rastreio de IDs e de textos compartilhados.
- `temas_avaliacoes.csv` — registros de **menções de temas por bloco**; um bloco pode conter vários temas e várias palavras do mesmo tema. O campo `tema` é em português e a classificação é por palavras-chave em inglês. **Não** mede sentimento, reviews individuais ou quantidade total de avaliações.
- `quality_report.json` — auditoria pontual, contagens, conflitos e premissas da preparação.

### Campos originais e derivados

Todos os nomes de colunas **originais** do Kaggle são preservados naquelas tabelas em que participam (por exemplo, `product_id`, `rating`, `rating_count`, `review_content`). Todos os campos **criados** pelo tratamento usam português sem acentuação para facilitar DAX/Power Query.

Exemplos: `categoria_nivel_1`, `categoria_final`, `preco_original_inr`, `preco_promocional_inr`, `desconto_percentual`, `desconto_percentual_calculado`, `quantidade_linhas_origem`, `preco_original_divergente`, `id_bloco_avaliacao`, `conteudo_avaliacao_tratado`, `quantidade_ids_avaliacao`, `quantidade_ids_compartilhados`, `hash_conteudo_avaliacao`, `conteudo_compartilhado_entre_produtos`.

## Decisões analíticas e limitações

1. Linhas com `product_id` repetido são consolidadas escolhendo a observação com maior `rating_count` válido, seguida de completude e ordem de origem. Sem data de captura, não podemos inferir qual observação é mais recente.
2. `rating_count` é um contador acumulado por produto, **não** um contador de vendas e **não** o número de reviews disponíveis no CSV. Produtos/variantes podem compartilhar avaliações: não publicar a soma de `rating_count` como volume global de avaliações únicas.
3. Textos não são divididos por vírgula porque existem vírgulas dentro de avaliações individuais; IDs de reviews podem ser separados e comparados, mas a contagem de IDs na amostra **não equivale** ao estoque de avaliações na Amazon.
4. Menções de temas são **exploratórias** e podem repetir-se em produtos que compartilham texto. Não equivalem a polaridade positiva/negativa; usar exemplos e interpretação qualitativa.
5. Valores ausentes permanecem ausentes; não se imputam preços ou notas como zero. Descontos são normalizados para 0–1, com cálculo independente para conferir inconsistências.
6. A base não contém dados de vendas, receita, exposição, conversão, disponibilidade atual nem série temporal. Não atribuir causalidade aos descontos nem chamar `rating_count` de visibilidade real.
7. Os valores originais em rúpias indianas (INR) são preservados; não há conversão dependente de cotação diária.

## Escopo

Entrega da disciplina: dashboard Power BI `.pbix` e vídeo executivo de até 7 minutos. O projeto privilegia métricas interpretáveis e decisões acionáveis, com documentação suficiente para explicar os dados, sem construir infraestrutura para manutenção permanente.
