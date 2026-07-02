"""ja→en（手順書ドメイン）の共有 few-shot デモ（Issue #43）。

video2manual 由来の組立マニュアル（ギアハウジング／モーターユニット）の実セグメントを
原文とする、日本語→英語の 4-shot（標準デモ 3 件＋non-translation 1 件）。
全 ja→X 言語ペアに共通適用し、言語間診断の比較可能性を担保する（デモのターゲット言語は
評価対象言語と一致させず、ソース言語 ja の一致を優先する設計。詳細は Issue #43）。

gold アノテーションは提案セット（PR レビューで Curator 検証）。パイロット／評価対象の
セグメントとは重複させないこと（リーク防止）。
"""

user_template = """
{src_lng} source:\n{source_segment}\n{tgt_lng} translation:\n{target_segment}
"""


accuracy_user_shot = [
    user_template.format(src_lng="Japanese", tgt_lng="English", source_segment="ベアリングが装着されたハウジングへシャフトを挿入し、指先などで軽く回転させて動きの滑らかさを確認する。", target_segment="Insert the housing into the shaft where the bearing is attached."),
    user_template.format(src_lng="Japanese", tgt_lng="English", source_segment="クリーナーを使用してギアハウジング内部を洗浄する。", target_segment="Clean the inside of the gear housing using a cleaner."),
    user_template.format(src_lng="Japanese", tgt_lng="English", source_segment="ブラシを用いてグリスを均一に塗布する。", target_segment="Using a small brush, apply grease evenly and carefully."),
]
accuracy_mem_shot = ['''
{"annotations": [{"error_span": "Insert the housing into the shaft", "category": "accuracy/mistranslation", "severity": "major", "is_source_error": "no"}, {"error_span": "指先などで軽く回転させて動きの滑らかさを確認する", "category": "accuracy/omission", "severity": "major", "is_source_error": "no"}]}
''',
'''
{"annotations": []}
''',
'''
{"annotations": [{"error_span": "small", "category": "accuracy/addition", "severity": "minor", "is_source_error": "no"}, {"error_span": "carefully", "category": "accuracy/addition", "severity": "minor", "is_source_error": "no"}]}
''',
]
# 3

fluency_user_shot = [
    user_template.format(src_lng="Japanese", tgt_lng="English", source_segment="圧入後はベアリングが所定の位置に正しく座っていることを目視で確認する。", target_segment="After press-fitting, visually confirm that the bearing are correctly seated in position."),
    user_template.format(src_lng="Japanese", tgt_lng="English", source_segment="組立前準備工程", target_segment="Pre-assembly preparation process"),
    user_template.format(src_lng="Japanese", tgt_lng="English", source_segment="電子トルクレンチを使用して、規定トルクにてボルトを固定する。", target_segment="Using a electronic torque wrench,secure the bolts at the specified torque."),
]
fluency_mem_shot = [
'''
{"annotations": [{"error_span": "are", "category": "fluency/grammar", "severity": "minor", "is_source_error": "no"}]}
''',
'''
{"annotations": []}
''',
'''
{"annotations": [{"error_span": "a electronic", "category": "fluency/grammar", "severity": "minor", "is_source_error": "no"}, {"error_span": ",secure", "category": "fluency/punctuation", "severity": "minor", "is_source_error": "no"}]}
''',
]

# 3

term_user_shot = [
    user_template.format(src_lng="Japanese", tgt_lng="English", source_segment="ピックツールを用いて、ハウジングの溝にOリングを損傷させないよう慎重に装着する。", target_segment="Using a pick tool, carefully install the O-ring into the ditch of the housing without damaging it."),
    user_template.format(src_lng="Japanese", tgt_lng="English", source_segment="デジタルノギスでシムの厚みを測定し、必要な枚数のシムを選択して配置する。", target_segment="Measure the thickness of the shim with digital calipers, and select and place the required number of spacers."),
    user_template.format(src_lng="Japanese", tgt_lng="English", source_segment="プレスシューを使用し、ベアリングを圧入する。", target_segment="Using a press shoe, press-fit the bearing."),
]
term_mem_shot = [
'''
{"annotations": [{"error_span": "ditch", "category": "terminology/inappropriate for context", "severity": "minor", "is_source_error": "no"}]}
''',
'''
{"annotations": [{"error_span": "spacers", "category": "terminology/inconsistent use", "severity": "minor", "is_source_error": "no"}]}
''',
'''
{"annotations": []}
'''
]

# 2
style_user_shot = [
    user_template.format(src_lng="Japanese", tgt_lng="English", source_segment="部品の外観や仕様に異常がないことを確認する。", target_segment="Confirm that there is no abnormality-existence in the appearance and specification of the parts."),
    user_template.format(src_lng="Japanese", tgt_lng="English", source_segment="ウエスを用いて隅々まで水分や残留物を完全に拭き取る。", target_segment="Using a cloth, completely wipe away all moisture and residue from every corner."),
    user_template.format(src_lng="Japanese", tgt_lng="English", source_segment="内部機構が干渉せず滑らかに動作するかを確認する。", target_segment="Confirm whether the internal mechanism does the smooth movement without doing interference.")
]
style_mem_shot = [
'''
{"annotations": [{"error_span": "abnormality-existence", "category": "style/awkward", "severity": "minor", "is_source_error": "no"}]}
''',
'''
{"annotations": []}
''',
'''
{"annotations": [{"error_span": "does the smooth movement without doing interference", "category": "style/awkward", "severity": "minor", "is_source_error": "no"}]}
'''
]

nontran_user_shot = [
    user_template.format(src_lng="Japanese", tgt_lng="English", source_segment="ギアハウジング内部を洗浄し、水分や残留物を拭き取る。", target_segment="Thank you for watching! Please subscribe to our channel."),
    user_template.format(src_lng="Japanese", tgt_lng="English", source_segment="ギアハウジング内部を洗浄し、水分や残留物を拭き取る。", target_segment="Thank you for watching! Please subscribe to our channel."),
    user_template.format(src_lng="Japanese", tgt_lng="English", source_segment="ギアハウジング内部を洗浄し、水分や残留物を拭き取る。", target_segment="Thank you for watching! Please subscribe to our channel."),
    user_template.format(src_lng="Japanese", tgt_lng="English", source_segment="ギアハウジング内部を洗浄し、水分や残留物を拭き取る。", target_segment="Thank you for watching! Please subscribe to our channel."),
]
nontran_mem_shot = [
'''
{"annotations": [{"error_span": "all", "category": "non-translation", "severity": "major", "is_source_error": "no"}]}
''',
'''
{"annotations": [{"error_span": "all", "category": "non-translation", "severity": "major", "is_source_error": "no"}]}
''',
'''
{"annotations": [{"error_span": "all", "category": "non-translation", "severity": "major", "is_source_error": "no"}]}
''',
'''
{"annotations": [{"error_span": "all", "category": "non-translation", "severity": "major", "is_source_error": "no"}]}
''',
]
