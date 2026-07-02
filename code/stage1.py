import os
import ast
import json
# random.seed(0)
import argparse
import importlib
import traceback
from langcodes import Language
from utils.agent import Agent
from datetime import datetime
from tqdm import tqdm


NAME_LIST=[
    "Accuracy Agent",
    "Fluency Agent",
    "Terminology Agent",
    "Style Agent",
    "Judge"
]

# 言語ペアごとの few-shot デモモジュール（論文の 4-shot demonstration strategy に対応）。
# 完全一致するペアが最優先。次にソース言語（ja→X 診断では全ターゲットに同一デモを
# 共通適用して比較可能性を担保する・Issue #43）、続いてターゲット言語で選び、
# それでも無ければ English 系（zh-en の few_shot_demos）にフォールバックする。
DEMO_MODULE_BY_PAIR = {
    "zh-en": "few_shot_demos",
    "en-de": "few_shot_demos_de",
    "he-en": "few_shot_demos_he",
    "ja-en": "few_shot_demos_ja",
}
DEMO_MODULE_BY_SOURCE = {
    "ja": "few_shot_demos_ja",
}
DEMO_MODULE_BY_TARGET = {
    "en": "few_shot_demos",
    "de": "few_shot_demos_de",
}
DEFAULT_DEMO_MODULE = "few_shot_demos"


def load_few_shots(lang_pair: str):
    """言語ペアに対応する few-shot デモモジュールを解決して import する。

    Args:
        lang_pair (str): "zh-en" のような言語ペア。

    Returns:
        module: accuracy_user_shot 等の few-shot 変数群を持つモジュール。

    解決順: 1) 完全一致ペア → 2) ソース言語（設計上の共有デモ。warning なし・Issue #43）
    → 3) ターゲット言語デフォルト → 4) English 系デフォルト。
    3)・4) のフォールバック時のみ、専用 few-shot が無い旨の warning を表示する。
    """
    module_name = DEMO_MODULE_BY_PAIR.get(lang_pair)
    if module_name is None:
        src_code = lang_pair.split("-")[0]
        module_name = DEMO_MODULE_BY_SOURCE.get(src_code)
    if module_name is None:
        tgt_code = lang_pair.split("-")[-1]
        module_name = DEMO_MODULE_BY_TARGET.get(tgt_code, DEFAULT_DEMO_MODULE)
        print(
            f"[warn] No dedicated few-shot demos for language pair '{lang_pair}'. "
            f"Falling back to '{module_name}'. Results may deviate from the paper's "
            f"per-language 4-shot setup."
        )
    return importlib.import_module(module_name)

def extract_json(text):
    """テキストから最初の '{' と最後の '}' に挟まれた部分文字列を切り出す。

    LLM 応答に前後の説明文やコードフェンスが含まれても、JSON 本体らしき範囲を
    大まかに抽出するための簡易処理。抽出結果の妥当性は呼び出し側でパースして確認する。

    Args:
        text (str): LLM の生出力。

    Returns:
        str: 最初の '{' から最後の '}' までの部分文字列（見つからなければ空に近い文字列）。
    """
    brace_open = text.find("{")
    brace_close = text.rfind("}")
    return text[brace_open:brace_close+1]


def parse_json_obj(text):
    """LLM 出力の JSON 文字列を安全にパースする（eval を使わない）。

    まず json.loads を試し、失敗した場合のみ ast.literal_eval（Python リテラル）で解釈する。
    いずれも任意コード実行を伴わないため、eval の安全性・堅牢性の問題を回避できる。

    Args:
        text (str): 抽出済みの JSON/辞書リテラル文字列。

    Returns:
        dict | list: パース結果。

    Raises:
        ValueError / SyntaxError: どちらでもパースできない場合（呼び出し側でリトライ）。
    """
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return ast.literal_eval(text)


class DebatePlayer(Agent):
    """討論に参加する 1 エージェント。Agent に OpenAI API キーを付与した派生クラス。

    Agent のチャット履歴管理・LLM 呼び出し機能を継承し、API キーを保持する点のみ拡張する。

    Attributes:
        openai_api_key (str): この player が LLM 呼び出しに使う API キー（フォールバック用）。
    """

    def __init__(self, model_name: str, name: str, temperature:float, openai_api_key: str, sleep_time: float) -> None:
        """DebatePlayer を初期化し、Agent の初期化に加えて API キーを保持する。

        Args:
            model_name (str): 使用モデル名。
            name (str): エージェント名。
            temperature (float): サンプリング温度。
            openai_api_key (str): LLM 呼び出しに使う API キー（フォールバック用）。
            sleep_time (float): レート制限対策のスリープ秒。
        """
        super(DebatePlayer, self).__init__(model_name, name, temperature, sleep_time)
        self.openai_api_key = openai_api_key


class Debate:
    """Stage1（次元分解・独立アノテーション）の 1 サンプル分の討論を統括する。

    4 次元エージェント（Accuracy / Fluency / Terminology / Style）と Judge を生成し、
    few-shot 注入・各次元の独立アノテーション・Judge 統合を実行して、最終 MQM
    アノテーションと全プレイヤーの履歴を save_file に蓄積する。

    Attributes:
        model_name (str): 使用モデル名。
        temperature (float): サンプリング温度。
        num_players (int): プレイヤー数（NAME_LIST 由来で固定＝4 次元 + Judge）。
        save_file_dir (str): 出力 JSON の保存先ディレクトリ。
        openai_api_key (str): 各エージェントに渡す API キー（フォールバック用）。
        max_round (int): 討論の最大ラウンド数。
        sleep_time (float): レート制限対策のスリープ秒。
        few_shots: 言語ペアに対応する few-shot デモモジュール。
        save_file (dict): 実行メタ情報・各次元/最終アノテーション・プレイヤー履歴を保持する辞書。
    """

    def __init__(self,
            model_name: str='gpt-4.1-mini',
            temperature: float=0,
            save_file_dir: str=None,
            openai_api_key: str=None,
            prompts_path: str=None,
            max_round: int=3,
            sleep_time: float=0,
            few_shots=None
        ) -> None:
        """Debate を初期化し、プロンプト読込・エージェント生成・独立アノテーションまで実行する。

        Args:
            model_name (str, optional): モデル名。デフォルト 'gpt-4.1-mini'。
            temperature (float, optional): サンプリング温度。デフォルト 0。
            save_file_dir (str, optional): 出力保存先ディレクトリ。
            openai_api_key (str, optional): API キー（フォールバック用）。
            prompts_path (str, optional): プロンプトテンプレート JSON のパス。
            max_round (int, optional): 最大討論ラウンド数。デフォルト 3。
            sleep_time (float, optional): スリープ秒。デフォルト 0。
            few_shots (optional): few-shot デモモジュール（load_few_shots の戻り値）。
        """
        self.model_name = model_name
        self.temperature = temperature
        # プレイヤー数は NAME_LIST（4 次元エージェント + Judge）で固定。
        self.num_players = len(NAME_LIST)
        self.save_file_dir = save_file_dir
        self.openai_api_key = openai_api_key
        self.max_round = max_round
        self.sleep_time = sleep_time
        self.few_shots = few_shots

        # init save file
        now = datetime.now()
        current_time = now.strftime("%Y-%m-%d_%H:%M:%S")
        self.save_file = {
            'start_time': current_time,
            'end_time': '',
            'model_name': model_name,
            'temperature': temperature,
            'num_players': len(NAME_LIST),
            'success': False,
            "src_lng": "",
            "tgt_lng": "",
            'source_segment': '',
            'target_segment': '',
            'accuracy_annotations': '',
            'fluency_annotations': '',
            'term_annotations': '',
            'style_annotations': '',
            'final_annotations': '',
            'players': {},
        }
        prompts = json.load(open(prompts_path))
        self.save_file.update(prompts)
        self.init_prompt()

        if self.save_file['accuracy_annotations'] == "":
            self.create_base()

        self.create_agents()
        self.init_agents()


    def init_prompt(self):
        """各エージェントのプロンプト内プレースホルダを実際の言語・原文/訳文で置換する。

        `##src_lng##` / `##tgt_lng##` / `##source_segment##` / `##target_segment##` を
        save_file の対応値で埋め、4 次元エージェントと Judge のプロンプトを完成させる。

        Returns:
            None
        """
        def prompt_replace(key):
            """save_file[key] 内の 4 種プレースホルダを実値で置換する。"""
            self.save_file[key] = self.save_file[key].replace("##src_lng##", self.save_file["src_lng"]).replace("##tgt_lng##", self.save_file["tgt_lng"]).replace("##source_segment##", self.save_file["source_segment"]).replace("##target_segment##", self.save_file["target_segment"])
        prompt_replace("accuracy_agent")
        prompt_replace("fluency_agent")
        prompt_replace("term_agent")
        prompt_replace("style_agent")
        prompt_replace("judge_agent")

    def create_base(self):
        """評価タスク開始のバナーを標準出力に表示する。

        Returns:
            None
        """
        print("\n===== Translation Eval Task =====\n")

    def create_agents(self):
        """NAME_LIST に基づき 5 プレイヤー（4 次元エージェント + Judge）を生成する。

        生成した player を self.players に格納し、次元別・Judge の参照属性にも割り当てる。

        Returns:
            None
        """
        self.players = [
            DebatePlayer(model_name=self.model_name, name=name, temperature=self.temperature, openai_api_key=self.openai_api_key, sleep_time=self.sleep_time) for name in NAME_LIST
        ]
        self.accuracy_agent = self.players[0]
        self.fluency_agent = self.players[1]
        self.term_agent = self.players[2]
        self.style_agent = self.players[3]
        self.judge = self.players[4]

    def _eval_dimension(self, agent, user_shots, mem_shots, nontran_user, nontran_mem, task_prompt):
        """1 次元エージェントの few-shot 注入・タスク付与・リトライ実行を共通化する。

        Args:
            agent: 対象の DebatePlayer。
            user_shots / mem_shots: few-shot の user / assistant 例（各 3 件）。
            nontran_user / nontran_mem: non-translation の few-shot 例（1 件）。
            task_prompt (str): 評価タスクのプロンプト。

        Returns:
            str: エージェントのアノテーション。全リトライ失敗時は空アノテーションを返す。
        """
        for user_shot, mem_shot in zip(user_shots, mem_shots):
            agent.add_event(user_shot)
            agent.add_memory(mem_shot)
        agent.add_event(nontran_user)
        agent.add_memory(nontran_mem)

        agent.add_event(task_prompt)
        annotations = '{"annotations": []}'  # 全リトライ失敗時のフォールバック
        count = 0
        retry = True
        while retry and count < 10:
            count += 1
            try:
                annotations = agent.ask()
                retry = False
            except Exception as e:
                print(f"An error occurred: {e}")

        agent.add_memory(annotations)
        return annotations

    def init_agents(self):
        """メタプロンプト設定・few-shot 注入・各次元の独立アノテーション・Judge 統合を実行する。

        4 次元エージェントに base_system_prompt を、Judge に judge_system_prompt を設定し、
        言語ペア別の few-shot を注入して各次元の注釈を取得（_eval_dimension）。最後に 4 次元の
        結果を Judge に渡して最終 MQM アノテーション（self.judge_ans）を生成する。

        Returns:
            None
        """
        # 言語ペアに応じて選択された few-shot デモをローカルに束ねる（以降の参照はそのまま）。
        fs = self.few_shots
        accuracy_user_shot, accuracy_mem_shot = fs.accuracy_user_shot, fs.accuracy_mem_shot
        fluency_user_shot, fluency_mem_shot = fs.fluency_user_shot, fs.fluency_mem_shot
        term_user_shot, term_mem_shot = fs.term_user_shot, fs.term_mem_shot
        style_user_shot, style_mem_shot = fs.style_user_shot, fs.style_mem_shot
        nontran_user_shot, nontran_mem_shot = fs.nontran_user_shot, fs.nontran_mem_shot

        self.accuracy_agent.set_meta_prompt(self.save_file['base_system_prompt'])
        self.fluency_agent.set_meta_prompt(self.save_file['base_system_prompt'])
        self.term_agent.set_meta_prompt(self.save_file['base_system_prompt'])
        self.style_agent.set_meta_prompt(self.save_file['base_system_prompt'])
        self.judge.set_meta_prompt(self.save_file['judge_system_prompt'])
        

        self.accuracy_annotations = self._eval_dimension(
            self.accuracy_agent, accuracy_user_shot, accuracy_mem_shot,
            nontran_user_shot[0], nontran_mem_shot[0], self.save_file['accuracy_agent'])

        self.fluency_annotations = self._eval_dimension(
            self.fluency_agent, fluency_user_shot, fluency_mem_shot,
            nontran_user_shot[1], nontran_mem_shot[1], self.save_file['fluency_agent'])

        self.term_annotations = self._eval_dimension(
            self.term_agent, term_user_shot, term_mem_shot,
            nontran_user_shot[2], nontran_mem_shot[2], self.save_file['term_agent'])

        self.style_annotations = self._eval_dimension(
            self.style_agent, style_user_shot, style_mem_shot,
            nontran_user_shot[3], nontran_mem_shot[3], self.save_file['style_agent'])

        self.judge.add_event(self.save_file['judge_agent'].replace('##accuracy_annotations##', self.accuracy_annotations).replace('##fluency_annotations##', self.fluency_annotations).replace('##term_annotations##', self.term_annotations).replace('##style_annotations##', self.style_annotations))
        count = 0
        self.judge_ans = None
        while count < 10:
            count += 1
            try:
                raw = self.judge.ask()
            except Exception as e:
                print(f"An error occurred: {e}")
                continue

            match = extract_json(raw)
            if match:
                try:
                    self.judge_ans = parse_json_obj(match)
                    self.judge.add_memory(self.judge_ans)
                    break
                except Exception as e:
                    print(f"Error parsing judge output: {e}. Retrying...")

        # 10 回で有効な JSON を得られなかった場合は non-translation にフォールバック
        if not isinstance(self.judge_ans, dict):
            self.judge_ans = {'annotations': [{'error span': 'all', 'category': 'non-translation', 'severity': 'major', 'is_source_error': 'no'}]}
            self.judge.add_memory(self.judge_ans)

    def save_file_to_json(self, id):
        """save_file を `{id}_v1.json` として出力ディレクトリに書き出す。

        Args:
            id (int): 出力ファイル名に使うサンプル ID。

        Returns:
            None
        """
        now = datetime.now()
        current_time = now.strftime("%Y-%m-%d_%H:%M:%S")
        save_file_path = os.path.join(self.save_file_dir, f"{id}_v1.json")

        self.save_file['end_time'] = current_time
        json_str = json.dumps(self.save_file, ensure_ascii=False, indent=4)
        with open(save_file_path, 'w') as f:
            f.write(json_str)

    def save_file_to_json_without_annotation(self, id):
        """アノテーション対象外（annotated == "no"）のサンプルとして "None" を書き出す。

        Args:
            id (int): 出力ファイル名に使うサンプル ID。

        Returns:
            None
        """
        save_file_path = os.path.join(self.save_file_dir, f"{id}_v1.json")
        json_str = json.dumps("None")
        with open(save_file_path, 'w') as f:
            f.write(json_str)



    def run(self):
        """Judge の最終結果を save_file に統合し、成功フラグと全プレイヤー履歴を確定する。

        self.judge_ans（最終アノテーション）を save_file にマージし、success を True に設定、
        各プレイヤーのチャット履歴を save_file['players'] に格納する。

        Returns:
            None
        """
        self.save_file.update(self.judge_ans)
        self.save_file['success'] = True

        for player in self.players:
            self.save_file['players'][player.name] = player.memory_lst


def parse_args():
    """Stage1 の CLI 引数を解析して返す。

    Returns:
        argparse.Namespace: input_file / output_dir / lang_pair / api_key /
            model_name / temperature / start_line を持つ引数オブジェクト。
    """
    parser = argparse.ArgumentParser("", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument("-i", "--input-file", type=str, required=True, help="Input file path")
    parser.add_argument("-o", "--output-dir", type=str, required=True, help="Output file dir")
    parser.add_argument("-lp", "--lang-pair", type=str, required=True, help="Language pair")
    parser.add_argument("-k", "--api-key", type=str, default=None, help="API key (省略時は .env / 環境変数から取得)")
    parser.add_argument("-m", "--model-name", type=str, default="gpt-3.5-turbo", help="Model name")
    parser.add_argument("-t", "--temperature", type=float, default=0, help="Sampling temperature")
    parser.add_argument("-s", "--start-line", type=int, default=1, help="Dataset starting line")

    return parser.parse_args()



if __name__ == "__main__":
    args = parse_args()
    openai_api_key = args.api_key

    current_script_path = os.path.abspath(__file__)
    MAD_path = current_script_path.rsplit("/", 2)[0]

    src_lng, tgt_lng = args.lang_pair.split('-')
    src_full = Language.make(language=src_lng).display_name()
    tgt_full = Language.make(language=tgt_lng).display_name()

    config = json.load(open(f"{MAD_path}/code/utils/stage1.json", "r"))

    # 言語ペアに対応する few-shot デモを解決（専用が無ければフォールバック）。
    few_shots = load_few_shots(args.lang_pair)

    start_line = args.start_line
    inputs = open(args.input_file, "r").readlines()
    inputs = [line.strip() for line in inputs[start_line-1:]]

    save_file_dir = args.output_dir
    if not os.path.exists(save_file_dir):
            os.mkdir(save_file_dir)

    for id, input in enumerate(tqdm(inputs)):
        try:
            prompts_path = f"{save_file_dir}/{id+start_line-1}-config_v1.json"

            config['source_segment'] = input.split('\t')[0]
            config['target_segment'] = input.split('\t')[1]
            annotated = input.split('\t')[2]
            config['src_lng'] = src_full
            config['tgt_lng'] = tgt_full

            with open(prompts_path, 'w') as file:
                json.dump(config, file, ensure_ascii=False, indent=4)
                
            debate = Debate(save_file_dir=save_file_dir, openai_api_key=openai_api_key, prompts_path=prompts_path, temperature=0, sleep_time=0, few_shots=few_shots)
            if annotated == "no":
                debate.save_file_to_json_without_annotation(id+start_line-1)
            else:
                debate.run()
                debate.save_file_to_json(id+start_line-1)
        except Exception as e:
            # 失敗サンプルを黙って欠落させず、ID と例外内容・トレースバックを記録して継続する。
            print(f"[error] Failed to process sample {id+start_line-1}: {e}")
            traceback.print_exc()
            continue