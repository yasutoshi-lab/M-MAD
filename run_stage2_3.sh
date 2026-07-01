DIR=$(cd "$(dirname "$0")" && pwd)

uv run --project "$DIR" python "$DIR/code/stage2_3.py"  synthetic_ref "zh-en" 0 1000
