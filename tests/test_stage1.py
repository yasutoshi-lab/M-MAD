"""stage1.py の純粋関数（L1）ユニットテスト。"""

import pytest

import stage1


class TestExtractJson:
    """extract_json のテスト（S1-EJ）。"""

    def test_json_only(self):
        assert stage1.extract_json('{"a":1}') == '{"a":1}'

    def test_surrounded_by_text(self):
        assert stage1.extract_json('pre {"a":1} post') == '{"a":1}'

    def test_code_fence(self):
        assert stage1.extract_json('```json\n{"a":1}\n```') == '{"a":1}'

    def test_no_braces_returns_empty(self):
        # find/rfind が -1 のため空文字列になる（現挙動）。
        assert stage1.extract_json('no braces') == ''


class TestParseJsonObj:
    """parse_json_obj のテスト（S1-PJ）。"""

    def test_valid_json(self):
        assert stage1.parse_json_obj('{"annotations": []}') == {"annotations": []}

    def test_python_literal_fallback(self):
        # シングルクォートは json.loads で失敗 → ast.literal_eval にフォールバック。
        result = stage1.parse_json_obj("{'annotations': [{'severity': 'major'}]}")
        assert result == {"annotations": [{"severity": "major"}]}

    def test_invalid_raises(self):
        with pytest.raises((ValueError, SyntaxError)):
            stage1.parse_json_obj('not json at all')


class TestLoadFewShots:
    """load_few_shots のテスト（S1-LF）。"""

    def test_exact_pairs(self):
        assert stage1.load_few_shots('zh-en').__name__ == 'few_shot_demos'
        assert stage1.load_few_shots('en-de').__name__ == 'few_shot_demos_de'
        assert stage1.load_few_shots('he-en').__name__ == 'few_shot_demos_he'

    def test_target_fallback_english(self, capsys):
        mod = stage1.load_few_shots('fr-en')
        assert mod.__name__ == 'few_shot_demos'
        assert 'No dedicated few-shot' in capsys.readouterr().out

    def test_target_fallback_german(self, capsys):
        mod = stage1.load_few_shots('ja-de')
        assert mod.__name__ == 'few_shot_demos_de'
        assert 'No dedicated few-shot' in capsys.readouterr().out

    def test_default_fallback(self, capsys):
        mod = stage1.load_few_shots('xx-yy')
        assert mod.__name__ == 'few_shot_demos'
        assert 'No dedicated few-shot' in capsys.readouterr().out

    def test_module_exports_shots(self):
        mod = stage1.load_few_shots('zh-en')
        for name in ['accuracy_user_shot', 'accuracy_mem_shot', 'fluency_user_shot',
                     'term_user_shot', 'style_user_shot', 'nontran_user_shot', 'nontran_mem_shot']:
            assert hasattr(mod, name)
        assert len(mod.accuracy_user_shot) == 3
        assert len(mod.nontran_user_shot) >= 4
