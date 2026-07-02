"""stage2_3.py の純粋関数（L1）ユニットテスト。"""

import stage2_3
from conftest import make_completion


class TestIsNull:
    """isnull のテスト（S2-NL）。"""

    def test_empty_variants(self):
        for s in ['{"annotations": []}', '{"annotations":[]}',
                  "{'annotations': []}", "{'annotations':[]}"]:
            assert stage2_3.isnull(s) is True

    def test_non_empty(self):
        assert stage2_3.isnull('{"annotations":[{"x":1}]}') is False


class TestIsOnlyDoubleQuotes:
    """is_only_double_quotes のテスト（S2-DQ）。"""

    def test_only_quotes(self):
        assert stage2_3.is_only_double_quotes('"') is True
        assert stage2_3.is_only_double_quotes('“”') is True

    def test_mixed(self):
        assert stage2_3.is_only_double_quotes('ab"') is False

    def test_empty_is_true(self):
        # all([]) は True（現挙動）。
        assert stage2_3.is_only_double_quotes('') is True


class TestExtractAnnotations:
    """extract_annotations のテスト（S2-EA）。"""

    def test_basic(self):
        assert stage2_3.extract_annotations('{"annotations":[{"error_span":"x"}]}') == \
            {"annotations": [{"error_span": "x"}]}

    def test_single_block_with_prose(self):
        # 解析文＋単一 annotations ブロック（末尾に角括弧を含まない散文）は正しく抽出される。
        content = 'analysis text here {"annotations":[{"error_span":"y"}]}'
        assert stage2_3.extract_annotations(content) == \
            {"annotations": [{"error_span": "y"}]}

    def test_multiple_blocks_quirk_returns_empty(self):
        # 複数 annotations ブロックがあると貪欲正規表現で連結が壊れ、空を返す（現挙動）。
        content = 'noise {"annotations":[]} more {"annotations":[{"error_span":"y"}]}'
        assert stage2_3.extract_annotations(content) == {"annotations": []}

    def test_invalid_inner_json_returns_empty(self):
        # annotations 内が不正 JSON → デコード失敗フォールバック。
        assert stage2_3.extract_annotations('{"annotations":[not json]}') == {"annotations": []}

    def test_no_match_returns_none(self):
        assert stage2_3.extract_annotations('nomatch') is None


class TestGetLanguageNames:
    """get_language_names のテスト（S2-GL）。"""

    def test_pairs(self):
        assert stage2_3.get_language_names('zh-en') == ('Chinese', 'English')
        assert stage2_3.get_language_names('en-de') == ('English', 'German')
        assert stage2_3.get_language_names('he-en') == ('Hebrew', 'English')

    def test_multipart_locale_target(self):
        # ja-zh-Hans / ja-zh-Hant のような 3 要素ロケールでも解決できる（Issue #50）。
        assert stage2_3.get_language_names('ja-zh-Hans') == ('Japanese', 'Chinese (Simplified)')
        assert stage2_3.get_language_names('ja-zh-Hant') == ('Japanese', 'Chinese (Traditional)')
        assert stage2_3.get_language_names('ja-my') == ('Japanese', 'Burmese')


class TestParseArgs:
    """parse_args のテスト（#55: 入出力ディレクトリ上書きオプション）。"""

    def test_dirs_default_to_none(self, monkeypatch):
        monkeypatch.setattr('sys.argv', ['stage2_3.py', 'sys1', 'ja-en', '0', '2'])
        args = stage2_3.parse_args()
        assert args.input_dir is None
        assert args.output_dir is None

    def test_dirs_can_be_overridden(self, monkeypatch):
        monkeypatch.setattr('sys.argv', ['stage2_3.py', 'sys1', 'ja-en', '0', '2',
                                         '-i', 'in_dir', '-o', 'out_dir'])
        args = stage2_3.parse_args()
        assert args.input_dir == 'in_dir'
        assert args.output_dir == 'out_dir'


class TestMessageBuilders:
    """メッセージ構築系のテスト（S2-MSG）。"""

    def test_set_meta_prompt(self):
        assert stage2_3.set_meta_prompt('x') == {"role": "system", "content": "x"}

    def test_add_event(self):
        assert stage2_3.add_event('x') == {"role": "user", "content": "x"}

    def test_ask_prompt(self):
        assert stage2_3.ask_prompt('x') == [{"role": "user", "content": "x"}]

    def test_construct_assistant_message(self):
        assert stage2_3.construct_assistant_message(make_completion('x')) == \
            {"role": "assistant", "content": "x"}

    def test_construct_message(self):
        # 相手 context（idx=0 に content を持つ）を 1 件与える。
        other = [[{"role": "assistant", "content": "PEER"}]]
        msg = stage2_3.construct_message(other, 0)
        assert msg["role"] == "user"
        assert "PEER" in msg["content"]
        assert "other agent" in msg["content"]
        assert "annotations" in msg["content"]
