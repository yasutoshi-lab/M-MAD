# 開発ガイド（Contributing）

M-MAD への変更を行う際の開発フローと規約。

## セットアップ

```bash
uv sync                     # ランタイム + dev（pytest / ruff / pre-commit）を導入
uv run pre-commit install   # （任意）ローカルの ruff フックを有効化
```

## テスト・lint

```bash
uv run pytest tests/ -q       # ユニットテスト（L1: 純粋関数）
uv run ruff check code tests  # lint（ruff）
```

- CI（GitHub Actions, `.github/workflows/ci.yml`）が `main` への push / PR で
  `uv sync` → `ruff check` → `pytest` を実行する（**必須ゲート**）。
- pre-commit はローカルの fail-fast 補助（opt-in）。ruff 設定は `pyproject.toml` の `[tool.ruff]` を共有。
- テスト方針とケース一覧は [test-design.md](test-design.md)。

### lint ポリシー
- ルールは `["E4","E7","E9","F"]`（実バグ寄り。行長 E501 は除外＝プロンプト長文のノイズ回避）。
- `ruff format`（自動整形）は現状未導入（研究コードの一括整形による差分を避ける段階的方針）。

## ブランチ / PR / コミット

- `main` への直接 push は禁止。feature ブランチから PR を作成する。
- ブランチ名: `fix-#<ISSUE>-<title>`（例 `fix-#10-exception-observability`）。
- コミットメッセージ: `<type>(<scope>): #<Issue> <subject>`（日本語・だ/である体）。
  `<type>` は `feat` / `fix` / `refactor` / `docs` / `test` / `chore` 等。
- Issue 表題: `【項目】主題-優先度`（項目は `Infra` / `Security` / `Bug` / `Docs` / `Refactor` /
  `Test` / `Chore` / `Data` 等、優先度は `致命` / `高` / `中` / `低`）。
- PR 本文には動作テスト手順（Test plan）を含める。

## 論文整合性の厳守（最重要）

機能の修正・追加・リファクタ・バグ修正など、**いかなるコード変更でも**元論文
（*Multidimensional Multi-Agent Debate for Advanced Machine Translation Evaluation*、
arXiv:2412.20127）で定義された手法・アルゴリズム・評価プロトコルとの整合性を保つこと。

- 3 ステージ構成 / MQM 4 次元 / 討論ラウンド数 / 合意判定 / severity / non-translation の扱い /
  Judge 統合ルールなど、**設計意図を変えない**。
- リファクタや不具合修正で挙動が論文の記述と乖離しうる場合は、独断で変更せず、論文の該当箇所を
  根拠として提示したうえで確認する。
- 論文の手法自体を変更・拡張する場合は、その旨と論文との差分を PR・Issue に明記する。

詳細な設計は [architecture.md](architecture.md) を参照。

## 変更時のチェックリスト

- [ ] `uv run ruff check code tests` が通る
- [ ] `uv run pytest tests/ -q` が通る
- [ ] 新規 env / 設定を追加したら `.env.example` と関連 doc を同じ PR で更新
- [ ] 挙動が論文と乖離しないこと（乖離する場合は PR に明記）
- [ ] 生成物（`data/output_*` / `data/stage2_3_*`）をコミットしていない
