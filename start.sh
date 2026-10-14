#!/usr/bin/env bash
# Start InfraSentinel.
#   bash start.sh            this laptop only
#   bash start.sh --lan      also machines on your Wi-Fi / network
#   bash start.sh --public   a public https link anyone on the internet can open (Cloudflare quick tunnel)
#   Permanent address: create a named tunnel in the Cloudflare dashboard (Zero Trust > Networks > Tunnels), then
#     CF_TUNNEL_TOKEN=<token> IS_PUBLIC_URL=https://scan.yourdomain.com bash start.sh --public
#   The quick tunnel's address changes on every restart; a named tunnel keeps the same address.
# AI model: Cisco Foundation-Sec-8B-Instruct (security-tuned, ~5 GB). Override with IS_MODEL=<ollama model name>.
cd "$(dirname "$0")"
PORT="${IS_PORT:-8765}"
MODEL="${IS_MODEL:-hf.co/mradermacher/Foundation-Sec-8B-Instruct-GGUF:Q4_K_M}"
FALLBACK="llama3.1:8b"
PUBLIC=0; for a in "$@"; do [ "$a" = "--public" ] && PUBLIC=1; done

# ---------- AI helper ----------
if command -v ollama >/dev/null; then
  if ! curl -s http://127.0.0.1:11434/api/tags >/dev/null; then
    echo "Starting the AI helper (Ollama)..."
    (ollama serve >/tmp/infrasentinel-ollama.log 2>&1 &)
    for i in $(seq 1 15); do curl -s http://127.0.0.1:11434/api/tags >/dev/null && break; sleep 1; done
  fi
  if ! ollama list 2>/dev/null | awk 'NR>1{print $1}' | grep -qiF "$MODEL"; then
    echo "Downloading the AI model: $MODEL (one time only)..."
    if ! ollama pull "$MODEL"; then
      echo "Could not download $MODEL. Trying $FALLBACK instead..."
      ollama pull "$FALLBACK" || echo "Model download failed. The app still works; AI explanations will be off."
    fi
  fi
  echo "AI models on this laptop:"; ollama list 2>/dev/null | awk 'NR>1{print "  - "$1}'
else
  echo "Ollama is not installed, so AI explanations are off. Install it from https://ollama.com/download"
fi

# ---------- public link ----------
TUNNEL_PID=""
cleanup() { [ -n "$TUNNEL_PID" ] && kill "$TUNNEL_PID" 2>/dev/null; }
trap cleanup EXIT INT TERM

if [ "$PUBLIC" = 1 ]; then
  if curl -s -o /dev/null "http://127.0.0.1:$PORT/login"; then
    echo "InfraSentinel is already running on port $PORT. Stop it first (Ctrl+C in its terminal, or: fuser -k $PORT/tcp)."; exit 1
  fi
  CF="$(command -v cloudflared || true)"
  if [ -z "$CF" ]; then
    mkdir -p bin; CF="$PWD/bin/cloudflared"
    if [ ! -x "$CF" ]; then
      case "$(uname -m)" in x86_64|amd64) ARCH=amd64;; aarch64|arm64) ARCH=arm64;; armv7l) ARCH=arm;; *) ARCH=amd64;; esac
      echo "Downloading Cloudflare's tunnel program (one time, about 40 MB)..."
      curl -fL --progress-bar -o "$CF" "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-$ARCH" && chmod +x "$CF" || rm -f "$CF"
    fi
  fi
  LOG=/tmp/infrasentinel-tunnel.log; : > "$LOG"; URL=""
  if [ -n "$CF_TUNNEL_TOKEN" ] && [ -x "$CF" ]; then
    if [ -z "$IS_PUBLIC_URL" ]; then echo "Set IS_PUBLIC_URL to your tunnel's address (for example https://scan.yourdomain.com)."; exit 1; fi
    echo "Starting your named Cloudflare tunnel (permanent address)..."
    "$CF" tunnel --no-autoupdate run --token "$CF_TUNNEL_TOKEN" >"$LOG" 2>&1 &
    TUNNEL_PID=$!; URL="$IS_PUBLIC_URL"
  elif [ -x "$CF" ]; then
    echo "Opening a public link with Cloudflare..."
    "$CF" tunnel --no-autoupdate --url "http://127.0.0.1:$PORT" >"$LOG" 2>&1 &
    TUNNEL_PID=$!
    for i in $(seq 1 40); do
      URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -1)"; [ -n "$URL" ] && break; sleep 1
    done
  fi
  if [ -z "$URL" ]; then
    [ -n "$TUNNEL_PID" ] && kill "$TUNNEL_PID" 2>/dev/null; TUNNEL_PID=""
    echo "Cloudflare didn't answer. Trying localhost.run instead (uses ssh)..."
    ssh -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -R 80:127.0.0.1:"$PORT" nokey@localhost.run >"$LOG" 2>&1 &
    TUNNEL_PID=$!
    for i in $(seq 1 30); do
      URL="$(grep -oE 'https://[a-z0-9.-]+\.(lhr\.life|localhost\.run)' "$LOG" | grep -v 'admin.localhost.run' | head -1)"; [ -n "$URL" ] && break; sleep 1
    done
  fi
  if [ -z "$URL" ]; then
    echo "Could not open a public link (details in $LOG). Starting on this laptop only."
  else
    export IS_PUBLIC_URL="$URL"
    echo; echo "============================================================"
    echo "  Public link (works anywhere):  $URL"
    echo "  It stays open while this window runs. Ctrl+C closes it."
    echo "============================================================"; echo
  fi
fi

python3 server.py "$@"
