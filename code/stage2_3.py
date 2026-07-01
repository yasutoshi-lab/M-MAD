import json
import random
import os
import re
import argparse
import backoff
from langcodes import Language
from openai import RateLimitError, APIError, APIConnectionError, InternalServerError, APITimeoutError
from utils.config import build_openai_client

NUM_AGENTS = 2
MAX_ROUNDS = 4
MQM_AGENTS = ["Accuracy", "Fluency", "Terminology", "Style"]


judge_system_prompt = "You are a judge for the translation error annotations, given the translation pair and annotations from previous rounds. Your task is to integrate them and remove repeated annotations if any, where if a single error_span contains multiple errors, indicate only the one that is the most severe, and if some errors have the same severity, choose the first matching category listed in the error typology (accuracy, then fluency, then terminology, then style). But please note this rule is only applied when a single error_span contains multiple errors. However, if it is not possible to reliably identify distinct errors because the translation is too badly garbled or is unrelated to the source, then mark a special category, called non-translation, that spans the entire segment. There can be at most one non-translation error per segment, and it should span the entire segment. No other errors should be identified if non-translation is selected."

judge_agent = "Regarding the translation pair \n\n##src_lng## source:\n##source_segment##\n##tgt_lng## translation:\n##target_segment##\n\nFrom previous annotations, we have the accuracy errors detection expert annotations: \n\n##accuracy_annotations##; the fluency errors detection expert annotations: \n\n##fluency_annotations##; the terminology errors detection expert annotations: \n\n##term_annotations##; and the style errors detection expert annotations: \n\n##style_annotations##.\n\nBased on the above information, output your analyses and the final annotations in JSON format as follows: {\"analysis\":(first, judge if it is non-translation error, if yes, explain responsibly why it is; if no, explain how do you use the rule when a single error_span contains multiple errors to output final annotations), \"annotations\":[{\"error_span\":(if non-translation error is selected, provide 'all'; otherwise, the error_span must be chosen from within the translated segment), \"category\":\"({category}/{subcategory} or non-translation)\", \"severity\":\"(minor or major)\", \"is_source_error\":\"(yes or no)\"},...]}"

def set_meta_prompt(meta_prompt: str):
    """メタプロンプトを system ロールのチャットメッセージ辞書に変換する。

    Args:
        meta_prompt (str): system として与える指示文。

    Returns:
        dict: {"role": "system", "content": ...} 形式のメッセージ。
    """
    return {"role": "system", "content": f"{meta_prompt}"}

def add_event(event: str):
    """イベント文字列を user ロールのチャットメッセージ辞書に変換する。

    Args:
        event (str): user 発話として与える文字列。

    Returns:
        dict: {"role": "user", "content": ...} 形式のメッセージ。
    """
    return {"role": "user", "content": f"{event}"}

def construct_message(agents, idx):
    """相手エージェントの回答を提示し再考を促す user メッセージを構築する。

    討論の各ラウンドで、他エージェントの直近回答（agent[idx]）を引用として並べ、
    severity は迷ったら minor に寄せる・non-translation は極力避ける等の指示と、
    最終回答の JSON フォーマットを付したプロンプトを生成する。

    Args:
        agents (list): 相手エージェントのチャット履歴（context）のリスト。
        idx (int): 各履歴から引用する回答のインデックス。

    Returns:
        dict: {"role": "user", "content": ...} 形式のメッセージ。
    """
    prefix_string = "These are the annotations from the other agent:"

    for agent in agents:
        agent_response = agent[idx]["content"]
        response = "\n\n ```{}```".format(agent_response)

        prefix_string = prefix_string + response
    # When the severity is hard to decide, please lean toward "minor." Only assign "major" if it significantly impacts the meaning. 
    prefix_string = prefix_string + """\n\n Given two different answers, think about it again. Examine your annotations and the other agent's annotations step by step. When the severity is hard to decide, please lean toward "minor." Only assign "major" if it significantly impacts the meaning. Avoid assigning 'non-translation' unless absolutely necessary. Provide your answer in the following JSON format at the end of your response: ```json\n{\"annotations\":[{\"error_span\": {error span in translated segment}, \"category\":\"{category}/{subcategory}\", \"severity\":\"{minor or major}\", \"is_source_error\":\"{yes or no}\"},...]}\n. If no errors are annotated, use the json format: ```json\n{"annotations": []}\n"""

    return {"role": "user", "content": prefix_string}

def ask_prompt(content):
    """単一 user メッセージからなる messages リストを構築する。

    Args:
        content (str): user 発話の内容。

    Returns:
        list[dict]: [{"role": "user", "content": ...}]。
    """
    return [{"role": "user", "content": content}]

def construct_assistant_message(completion):
    """ChatCompletion レスポンスから assistant メッセージ辞書を構築する。

    Args:
        completion: openai 1.x の ChatCompletion オブジェクト。

    Returns:
        dict: {"role": "assistant", "content": ...} 形式のメッセージ。
    """
    content = completion.choices[0].message.content
    return {"role": "assistant", "content": content}


def _log_backoff(details):
    """backoff リトライ時に試行回数・待機・例外内容を標準出力へ記録する。"""
    exc = details.get("exception")
    print(f"[warn] LLM call failed (attempt {details['tries']}), backing off {details['wait']:.1f}s: {exc}")


@backoff.on_exception(
    backoff.expo,
    (RateLimitError, APIError, APIConnectionError, InternalServerError, APITimeoutError),
    max_tries=5,
    on_backoff=_log_backoff,
)
def generate_answer(answer_context):
    """設定（OpenAI / Gemini / Vertex）に基づき LLM へ問い合わせ応答を得る。

    build_openai_client() で client とモデルを解決し、与えられたチャット履歴で
    chat.completions を 1 件生成する。API 由来の一時的エラーは backoff により指数
    バックオフで最大 5 回までリトライし、各リトライ内容をログ出力する。

    Args:
        answer_context (list[dict]): messages 形式のチャット履歴。

    Returns:
        ChatCompletion: LLM の応答オブジェクト。
    """
    # プロバイダ設定（OpenAI / Gemini）から client と使用モデルを解決（呼び出し時に生成）。
    client, model = build_openai_client()
    completion = client.chat.completions.create(
                model=model,
                messages=answer_context,
                n=1)
    return completion

def isnull(content):
    """アノテーション文字列が「空（エラー無し）」を表すかを判定する。

    シングル/ダブルクォート・空白有無の 4 バリエーションの空 annotations を許容する。

    Args:
        content (str): 判定対象のアノテーション文字列。

    Returns:
        bool: 空アノテーションなら True。
    """
    if content == '{"annotations": []}' or content == '{"annotations":[]}' or content == "{'annotations': []}" or content == "{'annotations':[]}":
        return True
    return False

def is_only_double_quotes(text):
    """テキストが引用符（" “ ”）のみで構成されるかを判定する。

    原文・訳文が引用符だけの退化ケースを検出し、Judge をスキップするために使う。

    Args:
        text (str): 判定対象の文字列。

    Returns:
        bool: すべての文字が引用符種であれば True。
    """
    double_quote_forms = {'"', '“', '”'}
    return all(char in double_quote_forms for char in text)

def load_json_files(folder_path):
    """フォルダ内の `{数値}_v1.json` を ID 昇順に読み込みリストで返す。

    ファイル名が数値 ID の JSON のみを対象にソートして読み込む。読み込みに失敗した
    要素は None として位置を保持する（インデックス＝サンプル ID の対応を維持）。

    Args:
        folder_path (str): Stage1 出力ディレクトリのパス。

    Returns:
        list: 各サンプルの JSON（dict）または None のリスト。
    """
    json_data = []
    
    files = os.listdir(folder_path)
    
    json_files = sorted(
        [f for f in files if f.endswith('_v1.json') and f.split('_v1.json')[0].isdigit()],
        key=lambda x: int(x.split('_v1.json')[0])
)

    for json_file in json_files:
        try:
            file_path = os.path.join(folder_path, json_file)
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                json_data.append(data)
        except Exception as e:
            print(f"[warn] Failed to load {json_file}: {e}")
            json_data.append(None)
    return json_data

def extract_annotations(content):
    """LLM 出力から annotations 配列を正規表現で抽出し dict として返す。

    `"annotations": [...]` に一致する最後のマッチを JSON として解釈する。JSON デコードに
    失敗した場合や一致が無い場合は空アノテーション相当を返す（後段の統合が壊れないように）。

    Args:
        content (str): LLM の生出力。

    Returns:
        dict | None: {"annotations": [...]}。一致が無い場合は None。
    """
    print("content: ", content)

    # pattern = r'\{\s*"annotations"\s*:\s*\[(.*?)\]\s*\}'
    # pattern = r'"annotations"\s*:\s*\[(.*?)\]'
    # pattern = r'"annotations"\s*:\s*\[(.+?)\]'
    pattern = r'"annotations"\s*:\s*\[(.*)\]'


    matches = re.findall(pattern, content, re.DOTALL)

    if matches:
        last_match = matches[-1]
        json_string = f'{{"annotations":[{last_match}]}}'
        print("json_string: ", json_string)
        try:
            json_data = json.loads(json_string)  # 将字符串解析为字典
            return json_data
        except json.JSONDecodeError as e:
            print("Error decoding JSON:", e)
            return json.loads('{"annotations":[]}')
    else:
        print("No matching JSON found.")


system_prompts = [
    "You are an expert in detecting accuracy errors in translations. Accuracy errors occur when the target content does not accurately reflect the propositional content of the source text. Review the provided translation and identify any errors in the following subcategories: addition, mistranslation, omission, and untranslated text. If no errors are found, return {\"annotations\": []}. If errors are found, list each error with the following details: the exact error span, the subcategory, and the severity (major or minor). Major errors significantly impact meaning and may confuse or mislead the reader. Minor errors have a slight impact, but do not cause loss of meaning or confusion. In case when it is not possible to reliably identify distinct errors because the translation is too badly garbled or is unrelated to the source, then mark a special category, called non-translation. No other errors should be identified if non-translation is selected.", 
    
    "You are an expert in detecting fluency errors in translations. Fluency errors are related to the linguistic well-formedness of the text. Review the provided translation and identify any errors in the following subcategories: character encoding, grammar, inconsistency, punctuation, register, and spelling. If no errors are found, return {\"annotations\": []}. If errors are found, list each error with the following details: the exact error span, the subcategory, and the severity (major or minor). Major errors significantly impact meaning and may confuse or mislead the reader. Minor errors have a slight impact, but do not cause loss of meaning or confusion. In case when it is not possible to reliably identify distinct errors because the translation is too badly garbled or is unrelated to the source, then mark a special category, called non-translation. No other errors should be identified if non-translation is selected.",
    
    "You are an expert in detecting terminology errors in translations. Terminology errors occur when a term deviates from standard subject field or organizational terminology, or when the target term is not the correct equivalent of the source term. Review the provided translation and identify any errors in the following subcategories: inappropriate for context, and inconsistent use. If no errors are found, return {\"annotations\": []}. If errors are found, list each error with the following details: the exact error span, the subcategory, and the severity (major or minor). Major errors significantly impact meaning and may confuse or mislead the reader. Minor errors have a slight impact, but do not cause loss of meaning or confusion. In case when it is not possible to reliably identify distinct errors because the translation is too badly garbled or is unrelated to the source, then mark a special category, called non-translation. No other errors should be identified if non-translation is selected.",
    
    "You are an expert in detecting style errors in translations. Style errors occur when the text is grammatically correct but deviates from organizational style guides or uses inappropriate language. Review the provided translation and identify any style errors. If no errors are found, return {\"annotations\": []}. If errors are found, list each error with the following details: the exact error span, the subcategory (which is always 'awkward' in the style category), and the severity (major or minor). Major errors significantly impact meaning and may confuse or mislead the reader. Minor errors have a slight impact, but do not cause loss of meaning or confusion. In case when it is not possible to reliably identify distinct errors because the translation is too badly garbled or is unrelated to the source, then mark a special category, called non-translation. No other errors should be identified if non-translation is selected."
]

user_prompt = """
{src_lng} source:\n{source_segment}\n{tgt_lng} translation:\n{target_segment}
"""

judge_prompt = "Compare the error annotations provided by two agents for the same machine-translated segment. Determine if the annotations are essentially consistent. The first agent annotations are: {first_annotations}; the other agent annotations are: {second_annotations}. Return \"yes\" if they are consistent, or \"no\" if they are inconsistent. Provide no additional output."


# run_dimension_debate が「合意に至らず未設定」を表す番兵（元コードの
# response_dict[dim] 未設定＝後段 KeyError の挙動を保持するため）。
_NO_RESULT = object()


def parse_args():
    """CLI 引数（system / lp / starting / ending）をパースする。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("system", type=str, help="MT system name")
    parser.add_argument("lp", type=str, help="Language pair (e.g. zh-en)")
    parser.add_argument("starting", type=int, help="Start sample index")
    parser.add_argument("ending", type=int, help="End sample index (2000 = all)")
    return parser.parse_args()


def get_language_names(lang_pair):
    """言語ペア（例 zh-en）から src/tgt の表示名を返す（stage1 と同方式）。"""
    src_code, tgt_code = lang_pair.split("-")
    return (
        Language.make(language=src_code).display_name(),
        Language.make(language=tgt_code).display_name(),
    )


def run_dimension_debate(mqm_agent_index, annotation, source_seg, target_seg, source_lang, target_lang):
    """1 つの MQM 次元について反対意見を立てて討論し、合意アノテーションを返す。

    合意（judge が yes/no）に至らなかった場合は `_NO_RESULT` を返す（元コードの
    response_dict[dim] 未設定＝後段 KeyError の挙動を保持するため）。
    """
    if "non-translation" in annotation:
        other_annotation = "I do not think it meets the criteria of being too badly garbled or entirely unrelated to the source, so it cannot be counted as a non-translation error."
    else:
        other_annotation = annotation.replace("major", "minor")
    content = [annotation, other_annotation]

    if annotation == other_annotation:
        return annotation

    agent_contexts = [[{"role": "system", "content": system_prompts[mqm_agent_index]},
                    {"role": "user", "content": user_prompt.format(src_lng=source_lang, tgt_lng=target_lang, source_segment=source_seg, target_segment=target_seg)}]
                    for agent in range(NUM_AGENTS)]

    judge_ans = ""
    for round in range(MAX_ROUNDS):
        for j, agent_context in enumerate(agent_contexts):

            if round == 0:
                assistant_message = {"role": "assistant", "content": content[j]}
                agent_context.append(assistant_message)
            else:
                agent_contexts_other = agent_contexts[:j] + agent_contexts[j+1:]
                message = construct_message(agent_contexts_other, 2 * round)
                agent_context.append(message)
                completion = generate_answer(agent_context)
                assistant_message = construct_assistant_message(completion)
                agent_context.append(assistant_message)

        if round != 0:
            print(agent_contexts[0][-1]['content'])
            print(agent_contexts[1][-1]['content'])
            annotation1 = extract_annotations(agent_contexts[0][-1]['content'])
            annotation2 = extract_annotations(agent_contexts[1][-1]['content'])
            print("annotation1: ", agent_contexts[0][-1]['content'], "\n", annotation1)
            print("annotation2: ", agent_contexts[1][-1]['content'], "\n",annotation2)

            judge_response = generate_answer(ask_prompt(judge_prompt.format(first_annotations = annotation1, second_annotations = annotation2)))
            judge_ans = judge_response.choices[0].message.content

            if "yes" in judge_ans:
                return extract_annotations(agent_contexts[0][-1]['content'])

    if "no" in judge_ans:
        return extract_annotations(agent_contexts[0][-1]['content'])
    return _NO_RESULT


def run_final_judge(response_dict, source_seg, target_seg, source_lang, target_lang):
    """4 次元の合意結果を統合 Judge に渡し、最終 MQM アノテーション(JSON)を返す。"""
    system_prompt = set_meta_prompt(judge_system_prompt)
    use_prompt = add_event(judge_agent.replace("##src_lng##", source_lang).replace("##tgt_lng##", target_lang).replace("##source_segment##", source_seg).replace("##target_segment##", target_seg).replace('##accuracy_annotations##', str(response_dict[MQM_AGENTS[0]])).replace('##fluency_annotations##', str(response_dict[MQM_AGENTS[1]])).replace('##term_annotations##', str(response_dict[MQM_AGENTS[2]])).replace('##style_annotations##', str(response_dict[MQM_AGENTS[3]])))

    print("judge user prompt\n", use_prompt)

    if isnull(response_dict[MQM_AGENTS[0]]) and isnull(response_dict[MQM_AGENTS[1]]) and isnull(response_dict[MQM_AGENTS[2]]) and isnull(response_dict[MQM_AGENTS[3]]):
        response = '{"annotations":[]}'
    elif is_only_double_quotes(source_seg) and is_only_double_quotes(target_seg):
        response = '{"annotations":[]}'
    else:
        response = generate_answer([system_prompt, use_prompt]).choices[0].message.content
    print("response", response)
    return extract_annotations(response)


def process_sample(sample, source_lang, target_lang):
    """Stage1 出力 1 件から討論＋最終判定を行い response_dict を返す。"""
    # サンプルごとに初期化し、前サンプルの値が最終 Judge に混入しないようにする。
    response_dict = {}
    source_seg = sample["source_segment"]
    target_seg = sample["target_segment"]
    print("source: ", source_seg)
    print("target: ", target_seg)
    response_dict["source"] = source_seg
    response_dict["target"] = target_seg
    for mqm_agent_index in range(len(MQM_AGENTS)):
        annotation = sample["players"][MQM_AGENTS[mqm_agent_index]+" Agent"][-1]["content"]
        result = run_dimension_debate(mqm_agent_index, annotation, source_seg, target_seg, source_lang, target_lang)
        if result is not _NO_RESULT:
            response_dict[MQM_AGENTS[mqm_agent_index]] = result

    response_dict["judge"] = run_final_judge(response_dict, source_seg, target_seg, source_lang, target_lang)
    return response_dict


def main():
    """Stage2&3 のエントリポイント。引数解析→入力ロード→サンプル毎処理→出力を行う。

    CLI 引数（system / lp / starting / ending）を解析し、Stage1 出力
    （data/output_{lp}_{system}_v1）を読み込む。starting..ending の各サンプルを
    process_sample で処理し、結果を data/stage2_3_{lp}_{system}/{i}_v1.json に書き出す。
    既存の非空出力はスキップし、annotated=="no"（"None"）のサンプルは空ファイルを残す。

    Returns:
        None
    """
    args = parse_args()
    system, lp, starting, ending = args.system, args.lp, args.starting, args.ending
    source_lang, target_lang = get_language_names(lp)

    # リポジトリルートをスクリプト位置から解決（実行ディレクトリに依存しない）。
    MAD_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Stage1 の出力（入力）: data/output_{lp}_{system}_v1
    input_dir = os.path.join(MAD_PATH, "data", f"output_{lp}_{system}_v1")
    all_json_data = load_json_files(input_dir)
    n = len(all_json_data)

    random.seed(0)

    # Stage2&3 の出力先も data/ 配下に統一（Stage1 出力と同じ場所に揃える）。
    folder_path = os.path.join(MAD_PATH, "data", f"stage2_3_{lp}_{system}")
    os.makedirs(folder_path, exist_ok=True)
    if ending == 2000:
        ending = n
    for i in range(starting, ending):
        print(f"-------------------The {i}th sample:---------------------")
        out_path = os.path.join(folder_path, f"{i}_v1.json")
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            continue
        with open(out_path, "w", encoding='utf-8') as f:
            if all_json_data[i] == "None":
                continue
            response_dict = process_sample(all_json_data[i], source_lang, target_lang)
            json.dump(response_dict, f, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    main()
