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

REQUIRED_COLUMNS = {
    "product_id", "product_name", "category", "discounted_price", "actual_price",
    "discount_percentage", "rating", "rating_count", "review_id",
    "review_title", "review_content",
}
OPTIONAL_COLUMNS = ("about_product", "img_link", "product_link")


# Só campos derivados são traduzidos; os nomes de origem permanecem inalterados.
RENOMEAR_PRODUTOS = {
    "category_level_1": "categoria_nivel_1",
    "category_level_2": "categoria_nivel_2",
    "category_level_3": "categoria_nivel_3",
    "category_level_4": "categoria_nivel_4",
    "category_leaf": "categoria_final",
    "actual_price_inr": "preco_original_inr",
    "discounted_price_inr": "preco_promocional_inr",
    "discount_pct": "desconto_percentual",
    "discount_pct_calculated": "desconto_percentual_calculado",
    "source_rows": "quantidade_linhas_origem",
    "price_conflict": "preco_original_divergente",
    "discounted_price_conflict": "preco_promocional_divergente",
    "rating_count_conflict": "quantidade_avaliacoes_divergente",
    "discount_conflict": "desconto_divergente",
    "discount_inconsistent": "desconto_inconsistente",
    "price_inverted": "preco_invertido",
    "source_row": "linha_origem",
}
RENOMEAR_AVALIACOES = {
    "source_row": "linha_origem",
    "review_bundle_key": "id_bloco_avaliacao",
    "review_title_clean": "titulo_avaliacao_tratado",
    "review_content_clean": "conteudo_avaliacao_tratado",
}

# Menções temáticas exploratórias, não sentimento nem contagem de reviews únicos.
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



def to_numeric(series: pd.Series, strip_pattern: str = r"[,\s]") -> pd.Series:
    """Converte valores com agrupamentos indianos, símbolo monetário e porcentagens."""
    cleaned = series.astype("string").str.replace(strip_pattern, "", regex=True)
    return pd.to_numeric(cleaned, errors="coerce")


def clean_review_text(value: object) -> str:
    """Limpa texto preservando vírgulas e sem tentar separar reviews compostos."""
    if pd.isna(value):
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"https?://[^\s,]+", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def prepare(input_path: Path, output_dir: Path) -> dict:
    """Gera produtos, blocos, temas e relatório de qualidade para o Power BI."""
    input_path, output_dir = Path(input_path), Path(output_dir)
    raw = pd.read_csv(input_path, dtype="string", keep_default_na=False, encoding="utf-8-sig")
    missing = REQUIRED_COLUMNS - set(raw.columns)
    if missing:
        raise ValueError(f"Colunas obrigatórias ausentes: {', '.join(sorted(missing))}")
    if raw.empty:
        raise ValueError("O arquivo CSV está vazio.")
    for col in OPTIONAL_COLUMNS:
        if col not in raw.columns:
            raw[col] = ""

    df = raw.copy()
    df["source_row"] = range(2, len(df) + 2)  # número da linha no CSV, com cabeçalho
    for col in REQUIRED_COLUMNS | set(OPTIONAL_COLUMNS):
        df[col] = df[col].astype("string").str.strip()
        df[col] = df[col].replace("", pd.NA)

    df["actual_price_inr"] = to_numeric(df["actual_price"], r"[₹,\s]")
    df["discounted_price_inr"] = to_numeric(df["discounted_price"], r"[₹,\s]")
    df["discount_pct"] = to_numeric(df["discount_percentage"], r"[%\s]") / 100
    df["rating_value"] = to_numeric(df["rating"], r"\s")
    df["rating_count_value"] = to_numeric(df["rating_count"], r"[,\s]")

    # Invalid values become missing, not zero (avoids distorting averages).
    for col in ("actual_price_inr", "discounted_price_inr"):
        df.loc[df[col].le(0), col] = float("nan")
    df.loc[~df["discount_pct"].between(0, 1), "discount_pct"] = float("nan")
    df.loc[~df["rating_value"].between(0, 5), "rating_value"] = float("nan")
    df.loc[df["rating_count_value"].lt(0), "rating_count_value"] = float("nan")

    levels = df["category"].fillna("").str.split("|", regex=False)
    for i in range(1, 5):
        df[f"category_level_{i}"] = levels.str.get(i - 1).replace("", pd.NA)
    df["category_leaf"] = levels.apply(lambda xs: xs[-1] if xs else "")

    df["discount_pct_calculated"] = (
        1 - df["discounted_price_inr"] / df["actual_price_inr"]
    ).where(df["actual_price_inr"].gt(0))
    df["discount_inconsistent"] = (
        (df["discount_pct"] - df["discount_pct_calculated"]).abs().gt(0.02)
    ).fillna(False)
    df["price_inverted"] = df["discounted_price_inr"].gt(df["actual_price_inr"]).fillna(False)

    # Same ID can occur more than once. Never sum rating_count across source rows.
    # Select the most informative observation (largest non-null rating_count),
    # then the most complete observation, then the first in the source CSV.
    completeness_fields = [
        "actual_price_inr", "discounted_price_inr", "discount_pct",
        "rating_value", "rating_count_value", "product_name", "category",
    ]
    df["completeness"] = df[completeness_fields].notna().sum(axis=1)
    selected = (
        df.sort_values(
            ["product_id", "rating_count_value", "completeness", "source_row"],
            ascending=[True, False, False, True], na_position="last", kind="stable",
        )
        .drop_duplicates("product_id", keep="first")
        .sort_values("product_id", kind="stable")
        .copy()
    )

    grp = df.groupby("product_id", dropna=False)
    observations = grp.size().rename("source_rows")
    conflict_cols = {
        "actual_price_inr": "price_conflict",
        "discounted_price_inr": "discounted_price_conflict",
        "rating_count_value": "rating_count_conflict",
        "discount_pct": "discount_conflict",
    }
    for raw_col, flag_col in conflict_cols.items():
        flags = grp[raw_col].nunique(dropna=True).gt(1).rename(flag_col)
        selected = selected.join(flags, on="product_id")
    selected = selected.join(observations, on="product_id")

    product_columns = [
        "product_id", "product_name", "category", "category_level_1",
        "category_level_2", "category_level_3", "category_level_4",
        "category_leaf", "actual_price_inr", "discounted_price_inr",
        "discount_pct", "discount_pct_calculated", "rating_value",
        "rating_count_value", "about_product", "img_link", "product_link",
        "source_rows", "price_conflict", "discounted_price_conflict",
        "rating_count_conflict", "discount_conflict", "discount_inconsistent",
        "price_inverted", "source_row",
    ]
    products = selected[product_columns].rename(
        columns={"rating_value": "rating", "rating_count_value": "rating_count", **RENOMEAR_PRODUTOS}
    )

    # Kaggle puts multiple comma-separated review IDs/titles/texts in one cell.
    # Commas can also occur *inside* a review, so blind splitting corrupts text.
    # Each row below is a review BUNDLE, not necessarily an individual review.
    reviews = df[["source_row", "product_id", "review_id", "review_title", "review_content"]].copy()
    reviews = reviews.drop_duplicates(
        ["product_id", "review_id", "review_title", "review_content"], keep="first"
    )
    reviews = reviews.loc[reviews["review_content"].notna()].copy()
    reviews["review_title_clean"] = reviews["review_title"].map(clean_review_text)
    reviews["review_content_clean"] = reviews["review_content"].map(clean_review_text)
    reviews.insert(0, "review_bundle_key", range(1, len(reviews) + 1))
    reviews = reviews.sort_values(["product_id", "review_bundle_key"], kind="stable")

    # IDs podem ser separados por vírgula; textos NÃO são separados.
    ids_por_bloco = reviews["review_id"].fillna("").map(
        lambda x: [valor.strip() for valor in x.split(",") if valor.strip()]
    )
    reviews["quantidade_ids_avaliacao"] = ids_por_bloco.map(len)
    produtos_por_id = (
        reviews.assign(id_avaliacao=ids_por_bloco).explode("id_avaliacao")
        .dropna(subset=["id_avaliacao"])
        .groupby("id_avaliacao")["product_id"].nunique()
    )
    ids_compartilhados = set(produtos_por_id[produtos_por_id.gt(1)].index)
    reviews["quantidade_ids_compartilhados"] = ids_por_bloco.map(
        lambda valores: sum(valor in ids_compartilhados for valor in set(valores))
    )
    reviews["hash_conteudo_avaliacao"] = reviews["review_content_clean"].map(
        lambda txt: hashlib.sha256(txt.casefold().encode("utf-8")).hexdigest()
    )
    quantidade_produtos_texto = reviews.groupby("hash_conteudo_avaliacao")["product_id"].nunique()
    reviews["quantidade_produtos_mesmo_conteudo"] = (
        reviews["hash_conteudo_avaliacao"].map(quantidade_produtos_texto).astype("int64")
    )
    reviews["conteudo_compartilhado_entre_produtos"] = reviews["quantidade_produtos_mesmo_conteudo"].gt(1)

    # Uma linha por tema identificado em um bloco; sem inferência de polaridade.
    linhas_temas = []
    for registro in reviews.itertuples(index=False):
        texto = registro.review_content_clean.casefold()
        for tema, padroes in TEMAS.items():
            termos = [padrao for padrao in padroes if re.search(padrao, texto)]
            if termos:
                linhas_temas.append({
                    "id_bloco_avaliacao": registro.review_bundle_key,
                    "product_id": registro.product_id,
                    "hash_conteudo_avaliacao": registro.hash_conteudo_avaliacao,
                    "tema": tema,
                    "quantidade_termos_encontrados": len(termos),
                    "metodo_classificacao": "regras de palavras-chave (exploratório)",
                })
    temas = pd.DataFrame(linhas_temas, columns=[
        "id_bloco_avaliacao", "product_id", "hash_conteudo_avaliacao", "tema",
        "quantidade_termos_encontrados", "metodo_classificacao",
    ])
    reviews = reviews.rename(columns=RENOMEAR_AVALIACOES)

    # Relationship contract for Power BI: products[product_id] 1 -> * review_bundles[product_id].
    assert products["product_id"].is_unique, "Produtos ainda duplicados após deduplicação"
    assert reviews["product_id"].isin(products["product_id"]).all(), "Review sem produto correspondente"

    report = {
        "arquivo_origem": input_path.name,
        "linhas_origem": int(len(df)),
        "produtos_unicos": int(len(products)),
        "linhas_duplicadas_de_produtos": int(len(df) - len(products)),
        "produtos_com_multiplas_linhas": int(products["quantidade_linhas_origem"].gt(1).sum()),
        "blocos_avaliacoes": int(len(reviews)),
        "blocos_desconsiderados_duplicados_ou_vazios": int(len(df) - len(reviews)),
        "linhas_origem_nota_invalida": int(df["rating_value"].isna().sum()),
        "linhas_origem_qtde_avaliacoes_ausente": int(df["rating_count_value"].isna().sum()),
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

    output_dir.mkdir(parents=True, exist_ok=True)
    products.to_csv(output_dir / "products.csv", index=False, encoding="utf-8-sig")
    reviews.to_csv(output_dir / "review_bundles.csv", index=False, encoding="utf-8-sig")
    temas.to_csv(output_dir / "temas_avaliacoes.csv", index=False, encoding="utf-8-sig")
    (output_dir / "quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepara Amazon CSV para análise no Power BI")
    parser.add_argument("--input", required=True, type=Path, help="CSV original amazon.csv")
    parser.add_argument("--output-dir", default=Path("data/processed"), type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.input, args.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
