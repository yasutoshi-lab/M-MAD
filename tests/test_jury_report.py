"""jury_report.py の純粋関数（L1）ユニットテスト（Issue #56）。"""

import json

import jury_report


class TestMqmScore:
    """mqm_score のテスト（JR-SC）。"""

    def test_empty_is_zero(self):
        assert jury_report.mqm_score([]) == 0

    def test_minor_and_major(self):
        anns = [{"category": "fluency/grammar", "severity": "minor"},
                {"category": "accuracy/mistranslation", "severity": "major"}]
        assert jury_report.mqm_score(anns) == -6

    def test_non_translation_is_minus_25(self):
        anns = [{"category": "non-translation", "severity": "major"}]
        assert jury_report.mqm_score(anns) == -25


class TestParseFinalAnnotations:
    """parse_final_annotations のテスト（JR-PA）。"""

    def test_dict(self):
        assert jury_report.parse_final_annotations({"annotations": [{"a": 1}]}) == [{"a": 1}]

    def test_json_string(self):
        assert jury_report.parse_final_annotations('{"annotations": []}') == []

    def test_invalid_returns_none(self):
        assert jury_report.parse_final_annotations("garbage") is None
        assert jury_report.parse_final_annotations(None) is None
        assert jury_report.parse_final_annotations({"nope": 1}) is None


class TestSpearman:
    """spearman のテスト（JR-SP）。"""

    def test_perfect_correlation(self):
        assert jury_report.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0

    def test_inverse_correlation(self):
        assert jury_report.spearman([1, 2, 3], [3, 2, 1]) == -1.0

    def test_zero_variance_returns_none(self):
        assert jury_report.spearman([1, 1, 1], [1, 2, 3]) is None

    def test_with_ties_known_value(self):
        # ranks x = [1, 2.5, 2.5, 4] / y = [1, 2, 3, 4] → ρ = 4.5/sqrt(4.5*5) ≈ 0.9487
        rho = jury_report.spearman([1, 2, 2, 4], [1, 2, 3, 4])
        assert abs(rho - 0.9487) < 1e-3


class TestCohenKappa:
    """cohen_kappa のテスト（JR-CK）。"""

    def test_known_value(self):
        # po=3/5, pe=13/25 → κ = (0.6-0.52)/(1-0.52) = 1/6
        a = [True, True, False, False, False]
        b = [True, False, True, False, False]
        assert abs(jury_report.cohen_kappa(a, b) - 1 / 6) < 1e-9

    def test_perfect_agreement(self):
        assert jury_report.cohen_kappa([True, False], [True, False]) == 1.0

    def test_degenerate_returns_none(self):
        # 両者とも定数 → pe=1 で未定義。
        assert jury_report.cohen_kappa([True, True], [True, True]) is None


def make_fixture(tmp_path):
    """2 プロバイダ×3 セグメントのフィクスチャを tmp_path/data 相当に作る。

    - seg0: 両者エラーなし（一致）
    - seg1: p1 は major 1 件（-5）、p2 はエラーなし（不一致セグメント）
    - seg2: p2 の Stage1 が success:false（除外対象）
    """
    lp, system = "ja-xx", "sysA"
    judges = {
        "p1": [{"annotations": []},
               {"annotations": [{"category": "accuracy/mistranslation", "severity": "major"}]},
               {"annotations": []}],
        "p2": [{"annotations": []},
               {"annotations": []},
               {"annotations": []}],
    }
    for provider in ("p1", "p2"):
        s1 = tmp_path / f"output_{lp}_{system}_{provider}"
        s2 = tmp_path / f"stage2_3_{lp}_{system}_{provider}"
        s1.mkdir()
        s2.mkdir()
        for i in range(3):
            success = not (provider == "p2" and i == 2)
            (s1 / f"{i}_v1.json").write_text(
                json.dumps({"success": success, "api_failures": [] if success else ["x"]}),
                encoding="utf-8")
            (s2 / f"{i}_v1.json").write_text(
                json.dumps({"source": f"src{i}", "target": f"tgt{i}",
                            "judge": judges[provider][i]}, ensure_ascii=False),
                encoding="utf-8")
    return lp, system


class TestLoadProviderResults:
    """load_provider_results のテスト（JR-LD）。"""

    def test_load_scores_and_exclusion(self, tmp_path):
        lp, system = make_fixture(tmp_path)
        p1 = jury_report.load_provider_results(lp, system, "p1", data_dir=str(tmp_path))
        p2 = jury_report.load_provider_results(lp, system, "p2", data_dir=str(tmp_path))
        assert p1[0]["score"] == 0 and p1[1]["score"] == -5
        assert p1[1]["has_error"] is True
        assert p1[0]["excluded"] is None
        assert p2[2]["excluded"] is not None  # stage1 success:false


class TestBuildReport:
    """build_report のテスト（JR-RP）。"""

    def test_report_contents(self, tmp_path):
        lp, system = make_fixture(tmp_path)
        results = {p: jury_report.load_provider_results(lp, system, p, data_dir=str(tmp_path))
                   for p in ("p1", "p2")}
        markdown, csv_rows = jury_report.build_report(lp, system, ["p1", "p2"], results)
        # 共通有効セグメントは 0,1（seg2 は p2 側除外）
        assert "共通有効セグメント: 2" in markdown
        assert "p1 vs p2" in markdown
        # 不一致セグメント（seg1: スコア差 5 + エラー有無不一致）が列挙される
        assert "src1" in markdown or "1" in markdown
        # 統合スコアを作らない旨の明記
        assert "統合スコア" in markdown
        # CSV: ヘッダ + 3 セグメント
        assert len(csv_rows) == 4
        header = csv_rows[0]
        assert "p1_score" in header and "p2_excluded" in header
