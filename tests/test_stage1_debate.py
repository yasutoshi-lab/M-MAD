"""stage1.Debate の API 失敗可観測化テスト（LLM モック使用・Issue #52）。

doc/test-design.md の L2-ED-2 / L2-JG-1 相当。Debate.__new__ で __init__ をスキップし、
フェイク agent を注入して API 全滅／パース失敗／正常応答の分岐を検証する。
"""

import stage1


class FakeAgent:
    """ask の挙動を制御できるフェイク agent（add_event / add_memory は無視）。"""

    def __init__(self, name="Accuracy Agent", ask_results=None):
        self.name = name
        self._ask_results = list(ask_results or [])

    def add_event(self, *_args):
        pass

    def add_memory(self, *_args):
        pass

    def ask(self):
        if self._ask_results:
            return self._ask_results.pop(0)
        raise RuntimeError("api down")


def make_debate():
    """__init__（プロンプト読込・API 実行）をスキップした素の Debate を作る。"""
    debate = stage1.Debate.__new__(stage1.Debate)
    debate.api_failures = []
    return debate


class TestEvalDimensionApiFailure:
    """_eval_dimension の API 全滅記録（L2-ED-2 相当）。"""

    def test_all_attempts_fail_records_api_failure(self):
        debate = make_debate()
        agent = FakeAgent(name="Accuracy Agent")  # ask は毎回例外
        result = debate._eval_dimension(agent, [], [], "u", "m", "task")
        assert result == '{"annotations": []}'  # 従来どおり空フォールバック
        assert len(debate.api_failures) == 1
        assert "Accuracy Agent" in debate.api_failures[0]

    def test_success_leaves_no_failure_record(self):
        debate = make_debate()
        agent = FakeAgent(ask_results=['{"annotations": [{"severity": "minor"}]}'])
        result = debate._eval_dimension(agent, [], [], "u", "m", "task")
        assert result == '{"annotations": [{"severity": "minor"}]}'
        assert debate.api_failures == []


class TestRunJudge:
    """_run_judge の API 失敗／パース失敗の区別（L2-JG-1 相当）。"""

    def test_api_failure_records_and_falls_back(self):
        debate = make_debate()
        debate.judge = FakeAgent(name="Judge")  # 応答ゼロ（API 全滅）
        ans = debate._run_judge()
        assert ans["annotations"][0]["category"] == "non-translation"
        assert len(debate.api_failures) == 1
        assert "Judge" in debate.api_failures[0]

    def test_parse_failure_falls_back_without_record(self):
        debate = make_debate()
        # 応答は得られるが JSON を含まない → 従来どおり non-translation（記録なし）
        debate.judge = FakeAgent(name="Judge", ask_results=["not json"] * 10)
        ans = debate._run_judge()
        assert ans["annotations"][0]["category"] == "non-translation"
        assert debate.api_failures == []

    def test_valid_json_is_returned(self):
        debate = make_debate()
        debate.judge = FakeAgent(name="Judge", ask_results=['{"annotations": []}'])
        ans = debate._run_judge()
        assert ans == {"annotations": []}
        assert debate.api_failures == []


class TestRunSuccessFlag:
    """run() の success 判定と api_failures の格納。"""

    def _base_debate(self):
        debate = make_debate()
        debate.judge_ans = {"annotations": []}
        debate.players = []
        debate.save_file = {"success": False, "players": {}}
        return debate

    def test_success_true_without_failures(self):
        debate = self._base_debate()
        debate.run()
        assert debate.save_file["success"] is True
        assert debate.save_file["api_failures"] == []

    def test_success_false_with_failures(self):
        debate = self._base_debate()
        debate.api_failures.append("Judge: all attempts failed (last error: boom)")
        debate.run()
        assert debate.save_file["success"] is False
        assert debate.save_file["api_failures"] == debate.api_failures
