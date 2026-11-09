# Tech Challenge — Fase 4 | Amazon Dataprep

Pipeline Python de preparação da base Kaggle *Amazon Sales Dataset* para um dashboard de **Power BI**. Código desenvolvido independentemente, usando as consultas do projeto do grupo como referência de requisitos.

## Execução

Requisitos: Python 3.10+ e `pandas>=2.0,<3.0`. Na raiz do repositório:

```bash
python -m pip install -r requirements.txt
python src/dataprep.py --input /caminho/para/amazon.csv --output-dir data/processed
python -m unittest discover -s tests -v
```

Substitua `/caminho/para/amazon.csv` pelo caminho do arquivo fornecido na disciplina. A base original **não** precisa ser publicada no GitHub.

## Power BI — CSVs publicados no GitHub

Os dados tratados são gerados automaticamente pelo [workflow do GitHub Actions](https://github.com/rodrigoscalioni/tech-challenge-fase-4/actions/workflows/prepare-data.yml), que baixa uma versão fixa da base original, valida o SHA-256, executa os testes e publica os resultados em `data/processed/`.

**Conexão:** no Power BI Desktop, selecione **Página Inicial → Obter dados → Web → Básico**. Cole uma URL por vez e escolha **Anônimo** (repositório público):

- **Produtos:** https://raw.githubusercontent.com/rodrigoscalioni/tech-challenge-fase-4/main/data/processed/products.csv
- **Conjuntos de avaliações:** https://raw.githubusercontent.com/rodrigoscalioni/tech-challenge-fase-4/main/data/processed/review_bundles.csv

Após importar, configure `products[product_id]` (lado 1) → `review_bundles[product_id]` (lado muitos), com filtragem unidirecional. Use `products` para métricas de produtos, sem somar `rating_count` na tabela de reviews. O `quality_report.json` está disponível para auditoria no repositório.

O botão **Atualizar** no Power BI busca novamente os CSVs do GitHub, mas **não** executa o script Python. Para regenerar os CSVs, execute manualmente o workflow na aba Actions ou atualize o código/testes no repositório. Os resultados são publicados automaticamente ao final de uma execução bem-sucedida.

## Arquivos gerados

- **products.csv**: uma linha por `product_id`. Preços em INR, desconto em escala de 0 a 1, nota, quantidade de avaliações, categorias hierárquicas e alertas de conflito. Use como dimensão/fato de indicadores de produtos.
- **review_bundles.csv**: conjuntos de comentários, vinculados por `product_id`. Contém os textos originais e tratados, sem presumir que cada linha é uma avaliação individual.
- **quality_report.json**: contagens, ausências, inconsistências e hipóteses adotadas.

Power BI: relacione `products[product_id]` (lado **1**) a `review_bundles[product_id]` (lado **muitos**), filtro em direção única de produtos para comentários. Use `products` para KPIs de produtos: misturar com a tabela de comentários pode duplicar contagens e valores. Formate `discount_pct` como percentual. Valores monetários estão em **₹ (INR)**, não em R$.

## Decisões de qualidade e limitações

1. Produtos duplicados são consolidados pelo `product_id`. O registro escolhido tem maior `rating_count` válido, seguido de completude e ordem de origem. Não é uma deduplicação temporal, pois não há datas.
2. `rating_count` é um **estoque de avaliações atribuídas ao produto**, não volume de vendas, visualizações ou comentários coletados neste CSV; **não somamos** valores em duplicatas.
3. `rating`, preços e descontos inválidos tornam-se ausentes (`NaN`), e são auditados. Não removemos produtos por uma única informação faltante.
4. Textos do Kaggle frequentemente combinam vários reviews em uma única célula separados por vírgula. Como os comentários também contêm vírgulas, **não separamos** esse conteúdo em supostas avaliações individuais. Analise temas qualitativamente nos *bundles*, sem chamar seu número de "total de avaliações".
5. Sem data de captura, vendas, receita ou visualizações, não se inferem crescimento, faturamento, causalidade de descontos ou visibilidade real. `rating_count` é apenas um proxy de engajamento.
6. Conservamos a moeda original (INR), sem conversão online que comprometeria a reprodutibilidade.
7. O relatório registra conflitos entre observações de um mesmo produto, inclusive preços, descontos e `rating_count`.

## Próxima etapa

Analisar distribuição de ratings, categorias, faixas de desconto, padrões de engajamento e temas textuais; construir páginas do Power BI e documentar recomendações com evidências. Este pacote entrega **somente a preparação**.
