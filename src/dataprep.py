"""Pipeline reproduzível para o Tech Challenge Amazon (Power BI).

Uso:
    python src/dataprep.py --input amazon.csv \
        --output-dir data/processed

Mantém preços em rúpias indianas (INR), sem taxa de câmbio dinâmica.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from pathlib import Path

import pandas as pd

# Colunas obrigatórias da base Amazon: sem elas não há dados suficientes para
# criar produtos, analisar preços e notas ou associar comentários a produtos.
REQUIRED_COLUMNS = {
    "product_id", "product_name", "category", "discounted_price", "actual_price",
    "discount_percentage", "rating", "rating_count", "review_id",
    "review_title", "review_content",
}
# Os campos opcionais enriquecem os registros; se faltarem, serão criados vazios.
OPTIONAL_COLUMNS = ("about_product", "img_link", "product_link")


# Os nomes originais da Amazon permanecem em inglês.
# Os campos derivados são criados diretamente em português,
# evitando mapeamentos e renomeações intermediárias.

# Menções temáticas exploratórias, sem classificar sentimentos ou avaliações individuais.
# Dicionário de classificação temática: cada chave é um tema do dashboard e
# cada lista reúne padrões em inglês que podem aparecer nos comentários.
# As expressões regulares (regex) usam \b para delimitar palavras;
# -? aceita hífen opcional (wifi / wi-fi) e (?:...) aceita variações de sufixo.
# Procuramos assuntos, não sentimentos: 'battery is good' e 'battery is bad'
# mencionam o tema Bateria e carregamento, embora expressem opiniões diferentes.
# Um mesmo texto pode mencionar vários temas e originar várias associações.
TEMAS = {
    "Preço e custo-benefício": [r"\bprice\b", r"\bexpensive\b", r"\bcheap\b", r"\bvalue for money\b", r"\bworth\b", r"\baffordable\b", r"\bcost\b"],
    "Qualidade e durabilidade": [r"\bquality\b", r"\bdurab(?:le|ility)\b", r"\bbroken\b", r"\bbroke\b", r"\bsturdy\b", r"\bflimsy\b", r"\bbuild\b"],
    "Desempenho": [r"\bperformance\b", r"\bspeed\b", r"\bfast\b", r"\bslow\b", r"\bworking\b", r"\bworks\b", r"\blag\b"],
    "Entrega e embalagem": [r"\bdelivery\b", r"\bdelivered\b", r"\bpackaging\b", r"\bpackage\b", r"\bshipping\b", r"\barrived\b"],
    "Bateria e carregamento": [r"\bbattery\b", r"\bcharging\b", r"\bcharger\b", r"\bcharge\b", r"\bbackup\b"],
    "Usabilidade": [r"\beasy to use\b", r"\buser friendly\b", r"\binstallation\b", r"\bsetup\b", r"\bcomfortable\b"],
    "Som e áudio": [r"\bsound\b", r"\baudio\b", r"\bbass\b", r"\bvolume\b", r"\bspeaker\b", r"\bmicrophone\b"],
    "Imagem e vídeo": [r"\bimage\b", r"\bpicture\b", r"\bdisplay\b", r"\bscreen\b", r"\bresolution\b", r"\bvideo\b", r"\bcamera\b"],
    "Conectividade": [r"\bwi-?fi\b", r"\bbluetooth\b", r"\bconnection\b", r"\bconnectivity\b", r"\bwireless\b", r"\bpairing\b"],
}



# Converte preços, percentuais e contadores de texto para números.
# O padrão informado remove símbolos, espaços ou separadores de milhar;
# valores não interpretáveis permanecem ausentes.
def to_numeric(series: pd.Series, strip_pattern: str = r"[,\s]") -> pd.Series:
    """Converte valores com agrupamentos indianos, símbolo monetário e porcentagens."""
    cleaned = series.astype("string").str.replace(strip_pattern, "", regex=True)
    return pd.to_numeric(cleaned, errors="coerce")


# Higieniza o conteúdo textual: decodifica entidades HTML, remove URLs e
# normaliza espaços, mas preserva vírgulas para não corromper os comentários.
def clean_review_text(value: object) -> str:
    """Limpa texto preservando vírgulas e sem dividir avaliações agrupadas."""
    if pd.isna(value):
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"https?://[^\s,]+", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


# Função principal: transforma o CSV bruto nas três bases do modelo analítico
# e em um relatório de qualidade com contagens, conflitos e premissas.
def prepare(input_path: Path, output_dir: Path) -> dict:
    """Gera produtos, blocos, temas e relatório de qualidade para o Power BI."""
    input_path, output_dir = Path(input_path), Path(output_dir)
    # Leitura como texto evita que a localidade do computador altere pontos
    # decimais ou separadores de milhar antes da limpeza controlada.
    raw = pd.read_csv(input_path, dtype="string", keep_default_na=False, encoding="utf-8-sig")
    # Validamos o esquema de entrada antes de qualquer transformação.
    missing = REQUIRED_COLUMNS - set(raw.columns)
    if missing:
        raise ValueError(f"Colunas obrigatórias ausentes: {', '.join(sorted(missing))}")
    if raw.empty:
        raise ValueError("O arquivo CSV está vazio.")
    # Garantimos a presença dos campos opcionais para simplificar as etapas seguintes.
    for col in OPTIONAL_COLUMNS:
        if col not in raw.columns:
            raw[col] = ""

    # Conservamos raw intacta; as transformações ocorrem sobre uma cópia.
    df = raw.copy()
    # Identificamos a linha no CSV original para manter rastreabilidade.
    df["linha_origem"] = range(2, len(df) + 2)  # número da linha no CSV, com cabeçalho
    # Eliminamos espaços extras nas bordas e convertemos campos vazios em ausentes.
    for col in REQUIRED_COLUMNS | set(OPTIONAL_COLUMNS):
        df[col] = df[col].astype("string").str.strip()
        df[col] = df[col].replace("", pd.NA)

    # Criamos preços e descontos derivados diretamente em português (valores em
    # INR e percentual de desconto como fração 0–1). As colunas originais rating
    # e rating_count preservam os nomes e passam a conter valores numéricos.
    df["preco_original_inr"] = to_numeric(df["actual_price"], r"[₹,\s]")
    df["preco_promocional_inr"] = to_numeric(df["discounted_price"], r"[₹,\s]")
    df["desconto_percentual"] = to_numeric(df["discount_percentage"], r"[%\s]") / 100
    df["rating"] = to_numeric(df["rating"], r"\s")
    df["rating_count"] = to_numeric(df["rating_count"], r"[,\s]")

    # Valores inválidos são ausentes, não zeros, para não distorcer indicadores.
    # Preços não positivos, percentuais fora de 0–100%, notas fora de 0–5 e
    # contadores negativos não são substituídos por zero: ficam ausentes.
    for col in ("preco_original_inr", "preco_promocional_inr"):
        df.loc[df[col].le(0), col] = float("nan")
    df.loc[~df["desconto_percentual"].between(0, 1), "desconto_percentual"] = float("nan")
    df.loc[~df["rating"].between(0, 5), "rating"] = float("nan")
    df.loc[df["rating_count"].lt(0), "rating_count"] = float("nan")

    # A categoria original chega em uma string separada por '|'.
    # Criamos diretamente categoria_nivel_1 a categoria_nivel_4 e categoria_final.
    levels = df["category"].fillna("").str.split("|", regex=False)
    for i in range(1, 5):
        df[f"categoria_nivel_{i}"] = levels.str.get(i - 1).replace("", pd.NA)
    df["categoria_final"] = levels.apply(lambda xs: xs[-1] if xs else "")

    # Conferência independente do desconto anunciado:
    # desconto calculado = 1 - preço promocional / preço original.
    # Marcamos divergência superior a 2 pontos percentuais e preço invertido.
    df["desconto_percentual_calculado"] = (
        1 - df["preco_promocional_inr"] / df["preco_original_inr"]
    ).where(df["preco_original_inr"].gt(0))
    df["desconto_inconsistente"] = (
        (df["desconto_percentual"] - df["desconto_percentual_calculado"]).abs().gt(0.02)
    ).fillna(False)
    df["preco_invertido"] = df["preco_promocional_inr"].gt(df["preco_original_inr"]).fillna(False)

    # Um produto pode aparecer em várias linhas de origem. Não somamos rating_count,
    # pois é um contador histórico do produto, não uma contagem de linhas ou vendas.
    # Selecionamos o maior contador válido; em empate, o registro mais completo;
    # persistindo o empate, mantemos o primeiro registro da fonte.
    # A completude conta quantos campos relevantes foram preenchidos e será
    # usada apenas para desempatar registros com o mesmo rating_count.
    completeness_fields = [
        "preco_original_inr", "preco_promocional_inr", "desconto_percentual",
        "rating", "rating_count", "product_name", "category",
    ]
    df["completeness"] = df[completeness_fields].notna().sum(axis=1)
    # Ordenamos pela preferência do registro e descartamos product_id repetido.
    # O resultado contém exatamente uma linha por identificador de produto.
    selected = (
        df.sort_values(
            ["product_id", "rating_count", "completeness", "linha_origem"],
            ascending=[True, False, False, True], na_position="last", kind="stable",
        )
        .drop_duplicates("product_id", keep="first")
        .sort_values("product_id", kind="stable")
        .copy()
    )

    # A auditoria consulta TODAS as observações de cada produto, mesmo após
    # a deduplicação, para sinalizar divergências entre os registros originais.
    grp = df.groupby("product_id", dropna=False)
    observations = grp.size().rename("quantidade_linhas_origem")
    conflict_cols = {
        "preco_original_inr": "preco_original_divergente",
        "preco_promocional_inr": "preco_promocional_divergente",
        "rating_count": "quantidade_avaliacoes_divergente",
        "desconto_percentual": "desconto_divergente",
    }
    # Se um campo apresentar mais de um valor distinto para o mesmo produto,
    # sinalizamos um conflito e também registramos a quantidade de linhas de origem.
    for raw_col, flag_col in conflict_cols.items():
        flags = grp[raw_col].nunique(dropna=True).gt(1).rename(flag_col)
        selected = selected.join(flags, on="product_id")
    selected = selected.join(observations, on="product_id")

    # Selecionamos o conjunto final de campos: preços, notas, categorias,
    # dados do produto e indicadores que permitem avaliar a qualidade da fonte.
    product_columns = [
        "product_id", "product_name", "category", "categoria_nivel_1",
        "categoria_nivel_2", "categoria_nivel_3", "categoria_nivel_4",
        "categoria_final", "preco_original_inr", "preco_promocional_inr",
        "desconto_percentual", "desconto_percentual_calculado", "rating",
        "rating_count", "about_product", "img_link", "product_link",
        "quantidade_linhas_origem", "preco_original_divergente", "preco_promocional_divergente",
        "quantidade_avaliacoes_divergente", "desconto_divergente", "desconto_inconsistente",
        "preco_invertido", "linha_origem",
    ]
    # BASE 1 — products: granularidade de um registro por product_id.
    products = selected[product_columns].copy()

    # A base original agrupa IDs, títulos e textos de avaliações na mesma célula.
    # Como os textos podem conter vírgulas comuns, não os dividimos por vírgula.
    # Cada linha será um BLOCO de avaliações, não uma avaliação individual.
    # BASE 2 — review_bundles: granularidade de um bloco textual por registro
    # distinto de produto, IDs, título e conteúdo de avaliação.
    reviews = df[["linha_origem", "product_id", "review_id", "review_title", "review_content"]].copy()
    # Removemos duplicatas exatas desse conjunto de campos, preservando
    # comentários diferentes associados ao mesmo produto.
    reviews = reviews.drop_duplicates(
        ["product_id", "review_id", "review_title", "review_content"], keep="first"
    )
    # Blocos sem texto não podem ser classificados em assuntos.
    reviews = reviews.loc[reviews["review_content"].notna()].copy()
    # Criamos diretamente titulo_avaliacao_tratado e conteudo_avaliacao_tratado,
    # preservando os campos originais em inglês.
    reviews["titulo_avaliacao_tratado"] = reviews["review_title"].map(clean_review_text)
    reviews["conteudo_avaliacao_tratado"] = reviews["review_content"].map(clean_review_text)
    # Criamos id_bloco_avaliacao diretamente em português, permitindo o
    # relacionamento um-para-muitos com temas_avaliacoes.
    reviews.insert(0, "id_bloco_avaliacao", range(1, len(reviews) + 1))
    reviews = reviews.sort_values(["product_id", "id_bloco_avaliacao"], kind="stable")

    # IDs podem ser separados por vírgula; textos NÃO são separados.
    # Os identificadores de avaliações PODEM ser separados por vírgulas,
    # ao contrário dos textos, nos quais vírgulas são parte do conteúdo.
    ids_por_bloco = reviews["review_id"].fillna("").map(
        lambda x: [valor.strip() for valor in x.split(",") if valor.strip()]
    )
    reviews["quantidade_ids_avaliacao"] = ids_por_bloco.map(len)
    # Ao expandir os IDs, descobrimos em quantos produtos cada um aparece.
    # Isso ajuda a detectar avaliações compartilhadas entre variantes.
    produtos_por_id = (
        reviews.assign(id_avaliacao=ids_por_bloco).explode("id_avaliacao")
        .dropna(subset=["id_avaliacao"])
        .groupby("id_avaliacao")["product_id"].nunique()
    )
    # Registramos o conjunto dos IDs compartilhados e sua presença em cada bloco.
    ids_compartilhados = set(produtos_por_id[produtos_por_id.gt(1)].index)
    reviews["quantidade_ids_compartilhados"] = ids_por_bloco.map(
        lambda valores: sum(valor in ids_compartilhados for valor in set(valores))
    )
    # SHA-256 gera uma impressão digital do texto, ignorando diferenças de
    # maiúsculas/minúsculas. Textos idênticos produzem o mesmo hash e podem
    # ser contados uma única vez com DISTINCTCOUNT no Power BI.
    reviews["hash_conteudo_avaliacao"] = reviews["conteudo_avaliacao_tratado"].map(
        lambda txt: hashlib.sha256(txt.casefold().encode("utf-8")).hexdigest()
    )
    # Contamos quantos produtos apresentam o mesmo conteúdo textual.
    quantidade_produtos_texto = reviews.groupby("hash_conteudo_avaliacao")["product_id"].nunique()
    reviews["quantidade_produtos_mesmo_conteudo"] = (
        reviews["hash_conteudo_avaliacao"].map(quantidade_produtos_texto).astype("int64")
    )
    # Identificamos casos em que o texto foi reutilizado entre produtos.
    reviews["conteudo_compartilhado_entre_produtos"] = reviews["quantidade_produtos_mesmo_conteudo"].gt(1)

    # Uma linha por tema identificado em um bloco; sem inferência de polaridade.
    # BASE 3 — temas_avaliacoes: cada linha associa UM bloco a UM tema.
    # Um bloco pode gerar várias linhas, pois os temas não são mutuamente exclusivos.
    linhas_temas = []
    # Percorremos os blocos de avaliação individualmente.
    for registro in reviews.itertuples(index=False):
        # casefold normaliza maiúsculas e minúsculas para a busca das regex.
        texto = registro.conteudo_avaliacao_tratado.casefold()
        # Para o mesmo texto, verificamos TODOS os nove temas cadastrados.
        for tema, padroes in TEMAS.items():
            # re.search identifica se cada padrão ocorre pelo menos uma vez.
            # O resultado conta PADRÕES diferentes encontrados, não a frequência
            # de repetição de cada palavra no texto.
            termos = [padrao for padrao in padroes if re.search(padrao, texto)]
            # Havendo correspondência, registramos o assunto com a chave do bloco.
            # Não inferimos elogio, crítica, emoção nem nota individual.
            if termos:
                linhas_temas.append({
                    "id_bloco_avaliacao": registro.id_bloco_avaliacao,
                    "product_id": registro.product_id,
                    "hash_conteudo_avaliacao": registro.hash_conteudo_avaliacao,
                    "tema": tema,
                    "quantidade_termos_encontrados": len(termos),
                    "metodo_classificacao": "regras de palavras-chave (exploratório)",
                })
    # Criamos a tabela final de associações temáticas, com rastreabilidade por
    # produto, bloco e hash, além do número de padrões e do método utilizado.
    temas = pd.DataFrame(linhas_temas, columns=[
        "id_bloco_avaliacao", "product_id", "hash_conteudo_avaliacao", "tema",
        "quantidade_termos_encontrados", "metodo_classificacao",
    ])
    # Relação no Power BI: products[product_id] (1) -> (*) review_bundles[product_id].
    # Verificações mínimas de integridade: identificador de produto único e
    # todos os blocos vinculados a um produto existente.
    assert products["product_id"].is_unique, "Produtos ainda duplicados após deduplicação"
    assert reviews["product_id"].isin(products["product_id"]).all(), "Review sem produto correspondente"

    # O relatório documenta volume de dados, perdas, conflitos, campos ausentes,
    # sobreposições entre avaliações e limitações da análise exploratória.
    report = {
        "arquivo_origem": input_path.name,
        "linhas_origem": int(len(df)),
        "produtos_unicos": int(len(products)),
        "linhas_duplicadas_de_produtos": int(len(df) - len(products)),
        "produtos_com_multiplas_linhas": int(products["quantidade_linhas_origem"].gt(1).sum()),
        "blocos_avaliacoes": int(len(reviews)),
        "blocos_desconsiderados_duplicados_ou_vazios": int(len(df) - len(reviews)),
        "linhas_origem_nota_invalida": int(df["rating"].isna().sum()),
        "linhas_origem_qtde_avaliacoes_ausente": int(df["rating_count"].isna().sum()),
        "produtos_sem_nota": int(products["rating"].isna().sum()),
        "produtos_sem_qtde_avaliacoes": int(products["rating_count"].isna().sum()),
        "produtos_com_preco_original_divergente": int(products["preco_original_divergente"].sum()),
        "produtos_com_preco_promocional_divergente": int(products["preco_promocional_divergente"].sum()),
        "produtos_com_qtde_avaliacoes_divergente": int(products["quantidade_avaliacoes_divergente"].sum()),
        "produtos_com_desconto_inconsistente": int(products["desconto_inconsistente"].sum()),
        "produtos_com_preco_invertido": int(products["preco_invertido"].sum()),
        "ids_avaliacao_distintos": int(len(produtos_por_id)),
        "ids_avaliacao_compartilhados_entre_produtos": int(len(ids_compartilhados)),
        "blocos_com_ids_compartilhados": int(reviews["quantidade_ids_compartilhados"].gt(0).sum()),
        "blocos_com_conteudo_compartilhado": int(reviews["conteudo_compartilhado_entre_produtos"].sum()),
        "registros_de_temas": int(len(temas)),
        "moeda": "INR",
        "premissas": [
            "rating_count é um contador acumulado por produto, não reviews únicos disponíveis",
            "cada bloco pode reunir vários reviews; review_content não é separado por vírgulas",
            "temas representam menções por bloco, não sentimento nem reviews individuais",
            "sem datas, vendas, receita, exposição ou taxa de conversão",
            "preços em INR sem conversão cambial",
            "produtos repetidos: escolher a linha com maior rating_count válido",
        ],
    }

    # Preparamos a pasta de destino, criando-a quando necessário.
    output_dir.mkdir(parents=True, exist_ok=True)
    # Exportamos cada granularidade separadamente em CSV UTF-8 com BOM,
    # facilitando a importação e a leitura de caracteres no Power BI.
    products.to_csv(output_dir / "products.csv", index=False, encoding="utf-8-sig")
    reviews.to_csv(output_dir / "review_bundles.csv", index=False, encoding="utf-8-sig")
    temas.to_csv(output_dir / "temas_avaliacoes.csv", index=False, encoding="utf-8-sig")
    # Registramos a auditoria em JSON legível, sem perder caracteres acentuados.
    (output_dir / "quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


# Interface de linha de comando: recebe o caminho do CSV de entrada e a
# pasta de saída; ao final, exibe o relatório de qualidade.
def main() -> None:
    parser = argparse.ArgumentParser(description="Prepara Amazon CSV para análise no Power BI")
    parser.add_argument("--input", required=True, type=Path, help="CSV original amazon.csv")
    parser.add_argument("--output-dir", default=Path("data/processed"), type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.input, args.output_dir), ensure_ascii=False, indent=2))


# Evita executar o pipeline ao importar este módulo nos testes automatizados.
if __name__ == "__main__":
    main()
