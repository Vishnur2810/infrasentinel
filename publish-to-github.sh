#!/usr/bin/env bash
# Put this project on GitHub.
#   bash publish-to-github.sh            -> creates a PUBLIC repo called "infrasentinel"
#   bash publish-to-github.sh --private  -> creates a PRIVATE repo
#   REPO=my-name bash publish-to-github.sh   -> choose another repo name
set -e
cd "$(dirname "$0")"
NAME="${REPO:-infrasentinel}"
VIS="--public"; [ "$1" = "--private" ] && VIS="--private"

command -v git >/dev/null || { echo "Install git first:  sudo apt install git"; exit 1; }
git config user.name  >/dev/null || git config user.name  "$(whoami)"
git config user.email >/dev/null || git config user.email "$(whoami)@users.noreply.github.com"

if [ ! -d .git ]; then git init -q -b main; fi
git add -A
echo "Files that will be uploaded:"; git status --short | sed 's/^/  /'
if git ls-files --cached | grep -qE '^data/(users|accounts|settings)\.json|^data/hosts/|^bin/'; then
  echo "Stopping: private runtime files are staged. Check .gitignore."; exit 1
fi
git diff --cached --quiet || git commit -q -m "InfraSentinel prototype: dashboard, read-only checker, local AI assistant"

if command -v gh >/dev/null; then
  gh auth status >/dev/null 2>&1 || gh auth login --web
  if git remote get-url origin >/dev/null 2>&1; then git push -u origin main
  else gh repo create "$NAME" $VIS --source . --remote origin --push --description "Plain-language security checks for small organizations"
  fi
  echo; echo "Done: $(gh repo view --json url -q .url)"
else
  echo
  echo "GitHub CLI (gh) isn't installed. Either install it:  sudo apt install gh   and run this script again,"
  echo "or create an empty repo named '$NAME' at https://github.com/new (no README), then run:"
  echo "  git remote add origin https://github.com/YOUR-USERNAME/$NAME.git"
  echo "  git push -u origin main"
fi
