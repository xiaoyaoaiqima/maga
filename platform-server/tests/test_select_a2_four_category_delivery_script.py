from scripts.select_a2_four_category_delivery import _brand_case, _jaccard, _ngrams


def test_brand_case_only_normalizes_brand_not_a2_protein():
    assert _brand_case("A2到了，A2蛋白也看了") == "a2到了，A2蛋白也看了"


def test_ngram_jaccard_detects_identical_and_different_comments():
    first = _ngrams("a2终于到货了")
    same = _ngrams("a2终于到货了！")
    different = _ngrams("罐底扫码能查报告")

    assert _jaccard(first, same) == 1.0
    assert _jaccard(first, different) < 0.2
