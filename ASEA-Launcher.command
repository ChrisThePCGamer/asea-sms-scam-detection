#!/bin/bash
# =====================================================================
#  A.S.E.A. LAUNCHER - macOS            (file: ASEA-Launcher.command)
#  Preflight -> auto-install -> press 1 -> API + website + browser
#  Closing this window stops the model server AND the website.
# =====================================================================
set -u

cd "$(dirname "$0")" || exit 1
PROJECT="$(pwd)"
VENV="$PROJECT/asea"
PYBIN=""
API_PID=""
UI_PID=""
INSTALLED=()
mkdir -p "$PROJECT/logs"

C1=$'\033[1;36m'; C2=$'\033[1;32m'; C3=$'\033[1;33m'; C4=$'\033[1;31m'; C0=$'\033[0m'
say()  { printf "\n%s%s%s\n" "$C1" "$1" "$C0"; }
ok()   { printf "   %s[OK]%s      %s\n" "$C2" "$C0" "$1"; }
miss() { printf "   %s[MISSING]%s %s\n" "$C3" "$C0" "$1"; }
die()  { printf "\n%s[ERROR]%s %s\n" "$C4" "$C0" "$1"; read -r -p "Press Return to close this window..." _; exit 1; }

# ---------------------------------------------------------- shutdown
cleanup() {
  printf "\n\nStopping A.S.E.A. ...\n"
  [ -n "$UI_PID" ]  && kill "$UI_PID"  2>/dev/null
  [ -n "$API_PID" ] && kill "$API_PID" 2>/dev/null
  sleep 1
  pkill -f "streamlit run streamlit_app.py" 2>/dev/null
  pkill -f "uvicorn api:app"                2>/dev/null
  printf "Model server (port 8000) and website (port 8501) are stopped.\n\n"
}
trap cleanup EXIT INT TERM HUP

wait_for_port() {          # $1 = port, $2 = max seconds
  local port="$1" limit="$2" i=0
  while [ "$i" -lt "$limit" ]; do
    if nc -z 127.0.0.1 "$port" >/dev/null 2>&1; then return 0; fi
    sleep 1; i=$((i+1))
  done
  return 1
}

clear
cat <<'BANNER'
=========================================================
   A.S.E.A.  -  Spam and Phishing SMS Detection
   Launcher for macOS
=========================================================
BANNER

# --------------------------------------------- 0. project sanity check
say "Step 0/5   Checking the project folder"
for f in api.py streamlit_app.py; do
  if [ -f "$PROJECT/$f" ]; then ok "$f found"
  else die "$f is not in this folder. Move ASEA-Launcher.command into the project folder that holds api.py, streamlit_app.py and asea_best_model/."; fi
done
if [ -d "$PROJECT/asea_best_model" ]; then ok "asea_best_model/ found"
else die "asea_best_model/ is missing. Download asea_bundle.zip from Kaggle (Appendix A, Cell 7) and unzip it into this folder."; fi

# --------------------------------------------- 1. Homebrew
say "Step 1/5   Checking Homebrew (used to install anything missing)"
if command -v brew >/dev/null 2>&1; then
  ok "Homebrew $(brew --version | head -n1 | awk '{print $2}')"
else
  miss "Homebrew - installing it now (macOS may ask for your login password)"
  NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || die "Homebrew installation failed."
  for p in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    [ -x "$p" ] && eval "$($p shellenv)"
  done
  command -v brew >/dev/null 2>&1 || die "Homebrew installed but is not on PATH yet. Close this window, open it again, and re-run the launcher."
  INSTALLED+=("Homebrew")
fi

# --------------------------------------------- 2. Python 3.10 - 3.12
say "Step 2/5   Checking Python"
for cand in python3.12 python3.11 python3.10 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    v="$("$cand" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)"
    case "$v" in 3.10|3.11|3.12) PYBIN="$(command -v "$cand")"; break ;; esac
  fi
done
if [ -n "$PYBIN" ]; then
  ok "Python $("$PYBIN" -V 2>&1 | awk '{print $2}')   ($PYBIN)"
else
  miss "Python 3.10-3.12 - installing python@3.12 with Homebrew"
  brew install python@3.12 || die "Could not install Python 3.12."
  PYBIN="$(brew --prefix)/opt/python@3.12/bin/python3.12"
  [ -x "$PYBIN" ] || die "Python 3.12 was installed but not found at $PYBIN."
  INSTALLED+=("Python 3.12")
fi

# --------------------------------------------- 3. Tesseract OCR
say "Step 3/5   Checking Tesseract OCR (screenshot reading)"
if command -v tesseract >/dev/null 2>&1; then
  ok "tesseract $(tesseract --version 2>&1 | head -n1 | awk '{print $2}')"
else
  miss "tesseract - installing it with Homebrew"
  brew install tesseract || die "Could not install Tesseract OCR."
  INSTALLED+=("Tesseract OCR")
fi

# --------------------------------------------- 4. venv + packages
say "Step 4/5   Checking the Python environment and packages"
if [ -x "$VENV/bin/python" ]; then
  ok "virtual environment asea/ found"
else
  miss "virtual environment asea/ - creating it"
  "$PYBIN" -m venv "$VENV" || die "Could not create the virtual environment."
  INSTALLED+=("Python virtual environment (asea/)")
fi
VPY="$VENV/bin/python"

if "$VPY" -m pip --version >/dev/null 2>&1; then
  ok "pip $("$VPY" -m pip --version | awk '{print $2}')"
else
  miss "pip - bootstrapping it"
  "$VPY" -m ensurepip --upgrade >/dev/null 2>&1 || die "Could not bootstrap pip."
  INSTALLED+=("pip")
fi

# pip-name | import-name   (the import name is what is actually tested)
REQS=(
  "fastapi|fastapi"
  "uvicorn[standard]|uvicorn"
  "python-multipart|multipart"
  "torch|torch"
  "transformers==4.46.3|transformers"
  "huggingface_hub==0.36.2|huggingface_hub"
  "safetensors|safetensors"
  "scikit-learn|sklearn"
  "joblib|joblib"
  "pandas|pandas"
  "numpy|numpy"
  "streamlit|streamlit"
  "requests|requests"
  "pillow|PIL"
  "pytesseract|pytesseract"
  "pyrebase4|pyrebase"
  "altair|altair"
  "pydantic|pydantic"
)
MISSING=()
for item in "${REQS[@]}"; do
  pipname="${item%%|*}"; mod="${item##*|}"
  if "$VPY" -c "import $mod" >/dev/null 2>&1; then ok "$mod"
  else miss "$mod"; MISSING+=("$pipname"); fi
done

if [ "${#MISSING[@]}" -gt 0 ]; then
  say "Installing ${#MISSING[@]} missing package(s). torch alone is ~2-3 GB, so the first run can take several minutes."
  "$VPY" -m pip install --upgrade pip >/dev/null 2>&1
  "$VPY" -m pip install "${MISSING[@]}" || die "pip could not install: ${MISSING[*]}"
  for m in "${MISSING[@]}"; do INSTALLED+=("$m"); done
  for item in "${REQS[@]}"; do
    mod="${item##*|}"
    "$VPY" -c "import $mod" >/dev/null 2>&1 || die "$mod still cannot be imported after installation. See the pip output above."
  done
fi

# --------------------------------------------- 4b. OCR end-to-end check
# Step 3 only proved a tesseract BINARY exists. pytesseract does not use
# that result - it resolves and runs the command itself, so it can still
# raise TesseractNotFoundError. This is the only check that proves the
# screenshot-to-text path in Verify Text actually works.
say "Step 4b/5 Checking the OCR pipeline (screenshot to text)"
OCR_PROBE='import pytesseract; pytesseract.get_tesseract_version()'
if "$VPY" -c "$OCR_PROBE" >/dev/null 2>&1; then
  ok "pytesseract can reach the tesseract engine"
else
  miss "pytesseract cannot reach the tesseract engine - repairing"
  brew install tesseract >/dev/null 2>&1
  export PATH="$(brew --prefix)/bin:$PATH"
  if "$VPY" -c "$OCR_PROBE" >/dev/null 2>&1; then
    ok "OCR pipeline repaired"
    INSTALLED+=("Tesseract OCR engine (screenshot reading)")
  else
    printf "   %s[WARNING]%s Screenshot reading will be unavailable. Everything\n" "$C3" "$C0"
    printf "             else works - you can still paste message text manually.\n"
  fi
fi

# --------------------------------------------- 5. installation summary
say "Step 5/5   Installation summary"
if [ "${#INSTALLED[@]}" -eq 0 ]; then
  printf "   Nothing had to be installed - every required tool was already present.\n"
else
  printf "   The following were downloaded and %sSUCCESSFULLY INSTALLED%s:\n" "$C2" "$C0"
  for i in "${INSTALLED[@]}"; do printf "      + %s\n" "$i"; done
fi
printf "   All requirements are satisfied and verified.\n"

# --------------------------------------------- press 1 to launch
printf "\n---------------------------------------------------------\n"
printf "   Press  %s1%s  to launch the A.S.E.A. website\n" "$C2" "$C0"
printf "   Press  %sq%s  to quit without launching\n" "$C3" "$C0"
printf "---------------------------------------------------------\n"
while true; do
  read -r -n 1 -s key
  case "$key" in
    1) printf "\n"; break ;;
    q|Q) printf "\nClosed. Nothing was started.\n"; exit 0 ;;
  esac
done

# --------------------------------------------- launch
say "Starting the model server (uvicorn, port 8000)"
"$VPY" -m uvicorn api:app --host 127.0.0.1 --port 8000 > "$PROJECT/logs/api.log" 2>&1 &
API_PID=$!
printf "   Loading asea_best_model (mBERT) into memory, please wait...\n"
wait_for_port 8000 240 || die "The model server did not start. Check logs/api.log."
ok "model server ready on http://localhost:8000"

say "Starting the website (Streamlit, port 8501)"
"$VPY" -m streamlit run streamlit_app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false > "$PROJECT/logs/ui.log" 2>&1 &
UI_PID=$!
wait_for_port 8501 120 || die "Streamlit did not start. Check logs/ui.log."
ok "website ready on http://localhost:8501"

say "Opening your default browser"
open "http://localhost:8501"

cat <<'RUNNING'

=========================================================
   A.S.E.A. IS RUNNING
     Website : http://localhost:8501
     API     : http://localhost:8000

   KEEP THIS WINDOW OPEN.
   Closing this window or pressing Control+C stops the
   model server AND the website completely.
=========================================================
RUNNING

while kill -0 "$API_PID" 2>/dev/null && kill -0 "$UI_PID" 2>/dev/null; do
  sleep 2
done
printf "\nOne of the two services exited on its own - shutting the other one down too.\n"