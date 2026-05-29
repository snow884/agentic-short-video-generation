set -eu

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

git add src/test_gguf.py src/run_gguf_code.sh
if ! git diff --cached --quiet; then
  git commit -m 'make changes'
fi
git push
echo "--- pushed code ---"

sshpass -p "Doner142142" ssh -tt -o StrictHostKeyChecking=no "adamivansky@192.168.1.122" /bin/bash << 'EOF'
  echo "--- Connected to remote ---"
  cd /home/adaivasnky/Documents/src/agentic_tasks/agentic-tasks
  git pull
  echo "--- Pulled code ---"
  conda run -n gguf python src/test_gguf.py
  echo "--- Finished executing code on remote ---"
  exit
EOF