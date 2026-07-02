"""prepare_input.py の純粋関数（L1）ユニットテスト。"""

import prepare_input


def make_manual(title="油圧ポンプの組立作業手順", desc2="部品を確認する。\n【部品】ケーシング、カバー", notes1=""):
    """テスト用の手順書 dict を生成する（2 mainSteps / detailedSteps 付き）。"""
    return {
        "title": title,
        "titleTruncated": False,
        "mainSteps": [
            {
                "id": "1", "order": 1, "title": "事前準備",
                "detailedSteps": [
                    {"id": "1-1", "order": 1, "description": desc2, "notes": notes1},
                ],
            },
            {
                "id": "2", "order": 2, "title": "組立",
                "detailedSteps": [
                    {"id": "2-1", "order": 1, "description": "ベアリングを圧入する。", "notes": "工具に注意"},
                ],
            },
        ],
    }


class TestFlattenText:
    """flatten_text のテスト（PI-FL）。"""

    def test_newlines_and_tabs_to_single_space(self):
        assert prepare_input.flatten_text("a\nb\tc") == "a b c"

    def test_collapse_multiple_spaces_and_strip(self):
        assert prepare_input.flatten_text("  a   b  ") == "a b"

    def test_empty_and_whitespace_only(self):
        assert prepare_input.flatten_text("") == ""
        assert prepare_input.flatten_text(" \n\t ") == ""


class TestExtractSegments:
    """extract_segments のテスト（PI-EX）。"""

    def test_paths_order_and_flatten(self):
        segs = prepare_input.extract_segments(make_manual())
        paths = [p for p, _ in segs]
        # 空 notes（mainSteps[0].detailedSteps[0].notes）はスキップされる
        assert paths == [
            "title",
            "mainSteps[0].title",
            "mainSteps[0].detailedSteps[0].description",
            "mainSteps[1].title",
            "mainSteps[1].detailedSteps[0].description",
            "mainSteps[1].detailedSteps[0].notes",
        ]
        texts = dict(segs)
        # description 内の改行は単一スペースへ正規化される
        assert texts["mainSteps[0].detailedSteps[0].description"] == "部品を確認する。 【部品】ケーシング、カバー"

    def test_missing_keys_are_tolerated(self):
        assert prepare_input.extract_segments({}) == []
        assert prepare_input.extract_segments({"title": "t", "mainSteps": None}) == [("title", "t")]


class TestBuildPairs:
    """build_pairs のテスト（PI-BP）。"""

    def test_aligned_pairs(self):
        ja = make_manual()
        en = make_manual(title="Hydraulic Pump Assembly", desc2="Verify the parts.", notes1="")
        pairs, skipped = prepare_input.build_pairs(ja, en)
        assert skipped == []
        assert pairs[0] == ("title", "油圧ポンプの組立作業手順", "Hydraulic Pump Assembly")
        assert len(pairs) == 6

    def test_skip_when_one_side_empty(self):
        ja = make_manual(notes1="ここに注記")   # ja 側のみ notes あり
        en = make_manual(title="T", notes1="")  # en 側は空 notes
        pairs, skipped = prepare_input.build_pairs(ja, en)
        assert "mainSteps[0].detailedSteps[0].notes" in skipped
        assert all(path != "mainSteps[0].detailedSteps[0].notes" for path, _, _ in pairs)

    def test_skip_extra_path_on_target_side(self):
        ja = make_manual()
        en = make_manual(title="T", notes1="only-en notes")  # en 側のみ notes あり
        pairs, skipped = prepare_input.build_pairs(ja, en)
        assert "mainSteps[0].detailedSteps[0].notes" in skipped
        assert len(pairs) == 6
