set -e
set -u

# スクリプト位置からリポジトリルートを解決（どのディレクトリから実行しても動く）
MAD_PATH=$(cd "$(dirname "$0")" && pwd)
system=$1
lp=$2
start=$3
version=$4


# API キー・モデル・プロバイダは .env（LLM_PROVIDER / GEMINI_API_KEY 等）から読み込まれる。
uv run --project $MAD_PATH python $MAD_PATH/code/stage1.py \
    -i $MAD_PATH/data/input.${lp}.${system}_v2.txt \
    -o $MAD_PATH/data/output_${lp}_${system}_${version} \
    -lp $lp \
    -s $start