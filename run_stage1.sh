version="v1"
DIR=$(cd "$(dirname "$0")" && pwd)

sh "$DIR/stage1.sh"  ANVITA "zh-en" 0 ${version}
