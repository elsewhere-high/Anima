#!/bin/zsh
set -eu
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! command -v node >/dev/null; then
  echo '请先安装 Node.js 22 或更新版本。'
  read -r '?按回车关闭。'
  exit 1
fi
node launch.mjs
read -r '?按回车关闭此窗口。'
