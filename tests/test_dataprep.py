"""Testes mínimos de qualidade, com unittest da biblioteca padrão."""

# Importamos ferramentas para ler relatórios JSON, trabalhar com arquivos
# temporários e executar verificações automatizadas sem usar a base real.
import json
import sys
import tempfile
import unittest
from pathlib import Path

# Pandas gera os dados fictícios e permite verificar os CSVs exportados.
import pandas as pd

# A pasta src é incluída no caminho para importar o dataprep que será testado.
# O comentário noqa: E402 é uma diretiva técnica para verificação de estilo.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from dataprep import prepare, clean_review_text  # noqa: E402


# Cada método iniciado por test_ representa uma regra do tratamento que queremos
# preservar. Se alguma asserção falhar, o teste sinaliza uma regressão.
class AmazonDataprepTests(unittest.TestCase):
    # TESTE 1 — Simula produtos repetidos, valores ausentes e comentários,
    # confirmando a geração das três bases e do relatório de qualidade.
    def test_dedupe_products_without_summing_rating_count(self):
        # Criamos três linhas usando os mesmos campos da Amazon. O produto A
        # aparece duas vezes; o produto B tem nota inválida e contador ausente.
        rows = [
            # Primeira linha do produto A: 1.000 avaliações e dois IDs de review
            # armazenados no mesmo bloco.
            dict(product_id="A", product_name="Cabo", category="Eletronicos|Cabos",
                 actual_price="₹1,000", discounted_price="₹600",
                 discount_percentage="40%", rating="4.3", rating_count="1,000",
                 review_id="R1,R2", review_title="Bom,Ótimo", review_content="Bom, gostei"),
            # Segunda linha do produto A: 1.200 avaliações e preço promocional
            # diferente; pela regra do dataprep, ela deve prevalecer.
            dict(product_id="A", product_name="Cabo", category="Eletronicos|Cabos",
                 actual_price="₹1,000", discounted_price="₹500",
                 discount_percentage="50%", rating="4.3", rating_count="1,200",
                 review_id="R3", review_title="Barato", review_content="Bom, resistente"),
            # Produto B: nota '|', contador vazio e uma URL no comentário.
            # Servem para validar o tratamento de ausências e de textos.
            dict(product_id="B", product_name="Mouse", category="Eletronicos|Mouse",
                 actual_price="₹300", discounted_price="₹200",
                 discount_percentage="33%", rating="|", rating_count="",
                 review_id="R4", review_title="Ruim", review_content="http://abc.com/x.jpg Frágil"),
        ]
        # O diretório temporário isola a execução e é apagado ao fim do teste.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            # Gravamos o CSV de entrada a partir dos dados simulados.
            pd.DataFrame(rows).to_csv(p / "raw.csv", index=False)
            # Executamos a função prepare real e lemos seus arquivos de saída.
            report = prepare(p / "raw.csv", p / "processed")
            products = pd.read_csv(p / "processed/products.csv")
            reviews = pd.read_csv(p / "processed/review_bundles.csv")
            # Três linhas originais devem resultar em dois produtos únicos.
            self.assertEqual(report["linhas_origem"], 3)
            self.assertEqual(report["produtos_unicos"], 2)
            # Selecionamos o maior rating_count de A (1.200), sem somar os
            # contadores de suas duas linhas de origem.
            self.assertEqual(products.loc[products.product_id == "A", "rating_count"].iloc[0], 1200)
            # O único produto com conflito de preço promocional é o produto A.
            self.assertEqual(report["produtos_com_preco_promocional_divergente"], 1)
            # A nota inválida deve ser registrada na auditoria e preservada
            # como ausente (NaN), em vez de ser convertida para zero.
            self.assertEqual(report["linhas_origem_nota_invalida"], 1)
            self.assertTrue(pd.isna(products.loc[products.product_id == "B", "rating"].iloc[0]))
            # Os três blocos distintos permanecem na base de comentários.
            # Os IDs R1, R2, R3 e R4 são quatro identificadores únicos.
            self.assertEqual(len(reviews), 3)
            self.assertEqual(report["ids_avaliacao_distintos"], 4)
            # Confirmamos a convenção de nomenclatura: nomes originais em
            # inglês e campos derivados diretamente em português.
            self.assertEqual(products.columns[3], "categoria_nivel_1")
            self.assertIn("quantidade_ids_avaliacao", reviews.columns)
            # Os três CSVs analíticos e o arquivo de auditoria devem existir.
            self.assertTrue((p / "processed/temas_avaliacoes.csv").exists())
            self.assertTrue((p / "processed/quality_report.json").exists())
            # A moeda original da base é INR (rúpia indiana), sem conversão.
            self.assertEqual(json.loads((p / "processed/quality_report.json").read_text())["moeda"], "INR")

    # TESTE 2 — Uma entrada incompleta deve produzir erro explícito,
    # pois só product_id não é suficiente para o processamento.
    def test_invalid_schema_fails_fast(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            pd.DataFrame({"product_id": ["A"]}).to_csv(p / "bad.csv", index=False)
            # Validamos o tipo e o conteúdo da mensagem de erro esperada.
            with self.assertRaisesRegex(ValueError, "Colunas obrigatórias ausentes"):
                prepare(p / "bad.csv", p / "out")

    # TESTE 3 — A limpeza remove URLs sem apagar vírgulas, que podem fazer
    # parte das frases e não devem ser usadas para dividir comentários.
    def test_review_text_preserves_commas(self):
        self.assertEqual(clean_review_text("bom, ótimo https://site.com/img.jpg produto"), "bom, ótimo produto")


# Este bloco permite executar o arquivo diretamente, além de usar a descoberta
# automática de testes no GitHub Actions.
if __name__ == "__main__":
    unittest.main()
