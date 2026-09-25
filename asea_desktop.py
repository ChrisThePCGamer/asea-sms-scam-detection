# =====================================================================
#  A.S.E.A. DESKTOP SHELL                    (file: asea_desktop.py)
#  A web app in a native window: FastAPI :8000 + Streamlit :8501,
#  wrapped in the system webview. Preflight and auto-install happen
#  inside the window. Closing the window stops BOTH servers.
# =====================================================================
import atexit
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time


# ---------------------------------------------------------------------
#  Bootstrap: the shell verifies and installs its OWN dependencies,
#  exactly the way ASEA-Launcher.command does for the runtime packages.
# ---------------------------------------------------------------------
def _ensure_shell_dep(pip_name, mod):
    try:
        __import__(mod)
        return
    except ImportError:
        pass
    print("[setup] missing shell dependency: %s - installing it now ..." % pip_name)
    subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
                   capture_output=True)
    r = subprocess.run([sys.executable, "-m", "pip", "install", pip_name],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("Could not install %s:\n%s" % (pip_name, r.stderr.strip()[-1200:]))
    import importlib
    importlib.invalidate_caches()
    __import__(mod)
    print("[setup] SUCCESSFULLY INSTALLED: %s" % pip_name)


if not getattr(sys, "frozen", False):          # a packaged .app already has them
    _SHELL_DEPS = [("pywebview", "webview")]
    if platform.system() == "Darwin":
        _SHELL_DEPS += [("pyobjc-framework-Cocoa", "Cocoa"),
                        ("pyobjc-framework-WebKit", "WebKit")]
    for _pip, _mod in _SHELL_DEPS:
        _ensure_shell_dep(_pip, _mod)

import webview

APP_TITLE = "A.S.E.A."
API_PORT = 8000
UI_PORT = 8501
IS_WIN = platform.system() == "Windows"
TESS_WIN = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# pip name -> import name (the import name is what is actually tested)
REQS = {
    "fastapi": "fastapi",
    "uvicorn[standard]": "uvicorn",
    "python-multipart": "multipart",
    "torch": "torch",
    "transformers==4.46.3": "transformers",
    "huggingface_hub==0.36.2": "huggingface_hub",
    "safetensors": "safetensors",
    "scikit-learn": "sklearn",
    "joblib": "joblib",
    "pandas": "pandas",
    "numpy": "numpy",
    "streamlit": "streamlit",
    "requests": "requests",
    "pillow": "PIL",
    "pytesseract": "pytesseract",
    "pyrebase4": "pyrebase",
    "altair": "altair",
    "pydantic": "pydantic",
}


def project_dir():
    """The folder holding api.py, streamlit_app.py and asea_best_model."""
    if getattr(sys, "frozen", False):
        exe = os.path.realpath(sys.executable)
        marker = ".app/Contents/MacOS"
        if marker in exe:                     # inside an ASEA.app bundle
            return os.path.dirname(exe.split(marker)[0])
        return os.path.dirname(exe)           # ASEA.exe next to the project
    return os.path.dirname(os.path.realpath(__file__))


PROJECT = project_dir()
VENV = os.path.join(PROJECT, "asea")
LOGDIR = os.path.join(PROJECT, "logs")


def venv_python():
    p = (os.path.join(VENV, "Scripts", "python.exe") if IS_WIN
         else os.path.join(VENV, "bin", "python"))
    return p if os.path.exists(p) else None


def find_system_python():
    """Any Python 3.10-3.12 we can build the venv with."""
    if IS_WIN:
        for v in ("3.12", "3.11", "3.10"):
            try:
                r = subprocess.run(["py", "-" + v, "-c", "print(1)"],
                                   capture_output=True, text=True)
                if r.returncode == 0:
                    return ["py", "-" + v]
            except FileNotFoundError:
                pass
    for name in ("python3.12", "python3.11", "python3.10", "python3", "python"):
        exe = shutil.which(name)
        if not exe:
            continue
        r = subprocess.run(
            [exe, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
            capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip() in ("3.10", "3.11", "3.12"):
            return [exe]
    return None


def port_open(port):
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_port(port, limit):
    for _ in range(limit):
        if port_open(port):
            return True
        time.sleep(1)
    return False


class Shell:
    """Everything the HTML page can call lives here (js_api)."""

    def __init__(self):
        self.log = []
        self.installed = []
        self.state = "checking"   # checking | installing | ready | running | error
        self.vpy = None
        self.api = None
        self.ui = None

    # ------------------------------------------------ exposed to JavaScript
    def poll(self):
        return {"state": self.state, "log": self.log, "installed": self.installed}

    def preflight(self):
        threading.Thread(target=self._preflight, daemon=True).start()
        return True

    def launch(self):
        if self.state != "ready":
            return False
        self.state = "running"
        threading.Thread(target=self._launch, daemon=True).start()
        return True

    # ------------------------------------------------ helpers
    def say(self, line=""):
        self.log.append(line)

    def fail(self, msg):
        self.say()
        self.say("ERROR: " + msg)
        self.state = "error"
        return False

    def _spawn(self, args, out, err):
        kw = {}
        if IS_WIN:
            kw["creationflags"] = (subprocess.CREATE_NEW_PROCESS_GROUP
                                   | subprocess.CREATE_NO_WINDOW)
        else:
            kw["start_new_session"] = True     # own process group, so we can killpg
        # Hand the children a PATH that can find tesseract. On Windows the
        # winget PATH update never reaches an already-running process, so
        # streamlit_app.py raises TesseractNotFoundError on the first
        # screenshot upload until the machine is restarted. Prepending the
        # install directory here fixes it without a reboot.
        env = os.environ.copy()
        extra = os.path.dirname(TESS_WIN) if IS_WIN else "/opt/homebrew/bin"
        if os.path.isdir(extra) and extra not in env.get("PATH", ""):
            env["PATH"] = extra + os.pathsep + env.get("PATH", "")
        kw["env"] = env
        return subprocess.Popen(args, cwd=PROJECT,
                                stdout=open(out, "wb"), stderr=open(err, "wb"), **kw)

    def _kill(self, proc):
        if not proc or proc.poll() is not None:
            return
        try:
            if IS_WIN:
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                               capture_output=True)
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                time.sleep(1)
                if proc.poll() is None:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            pass

    def _sweep(self):
        """Safety net. If a child was re-parented to launchd/init before
        killpg could reach it, the process group no longer exists and _kill
        silently does nothing. Match on the command line instead - this is
        what ASEA-Launcher.command already does on exit."""
        pats = ("uvicorn api:app", "streamlit run streamlit_app.py")
        for pat in pats:
            try:
                if IS_WIN:
                    subprocess.run(
                        ["powershell", "-NoProfile", "-Command",
                         "Get-CimInstance Win32_Process | Where-Object { "
                         "$_.CommandLine -like '*" + pat + "*' } | "
                         "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
                        capture_output=True)
                else:
                    subprocess.run(["pkill", "-f", pat], capture_output=True)
            except Exception:
                pass

    def shutdown(self, *_args):
        """Called when the window closes, and again at interpreter exit.
        Takes *_args because pywebview passes the window to event handlers."""
        for p in (self.ui, self.api):
            self._kill(p)
        self.ui = None
        self.api = None
        self._sweep()

    # ------------------------------------------------ preflight
    def _preflight(self):
        try:
            self.say("Checking the project folder ...")
            for f in ("api.py", "streamlit_app.py"):
                if not os.path.exists(os.path.join(PROJECT, f)):
                    return self.fail(
                        f + " was not found next to the app. Put A.S.E.A. in the "
                        "project folder that holds api.py, streamlit_app.py and "
                        "asea_best_model.")
                self.say("  OK        " + f)
            if not os.path.isdir(os.path.join(PROJECT, "asea_best_model")):
                return self.fail("asea_best_model is missing. Download "
                                 "asea_bundle.zip from Kaggle (Appendix A, Cell 7) "
                                 "and unzip it into this folder.")
            self.say("  OK        asea_best_model")
            os.makedirs(LOGDIR, exist_ok=True)

            # ---- virtual environment
            vpy = venv_python()
            if vpy is None:
                sys_py = find_system_python()
                if sys_py is None:
                    return self.fail("No Python 3.10-3.12 was found. Run "
                                     "ASEA-Launcher.command once (it installs "
                                     "Python), or install Python 3.12 manually.")
                self.state = "installing"
                self.say("  MISSING   virtual environment asea - creating it")
                subprocess.run(sys_py + ["-m", "venv", VENV], cwd=PROJECT, check=True)
                self.installed.append("Python virtual environment (asea)")
                vpy = venv_python()
                if vpy is None:
                    return self.fail("Could not create the virtual environment.")
            self.say("  OK        virtual environment asea")
            self.vpy = vpy

            # ---- Tesseract OCR (non-fatal)
            if shutil.which("tesseract") or (IS_WIN and os.path.exists(TESS_WIN)):
                self.say("  OK        tesseract OCR")
            else:
                self.state = "installing"
                self.say("  MISSING   tesseract OCR - installing it")
                try:
                    if IS_WIN:
                        subprocess.run(["winget", "install", "-e", "--id",
                                        "UB-Mannheim.TesseractOCR",
                                        "--accept-package-agreements",
                                        "--accept-source-agreements"],
                                       capture_output=True)
                    else:
                        subprocess.run(["brew", "install", "tesseract"],
                                       capture_output=True)
                except Exception:
                    pass
                if shutil.which("tesseract") or (IS_WIN and os.path.exists(TESS_WIN)):
                    self.installed.append("Tesseract OCR")
                    self.say("  OK        tesseract OCR")
                else:
                    self.say("  WARNING   tesseract still not found - screenshot "
                             "reading will be unavailable, everything else works")

            # ---- packages, one import at a time
            missing = []
            for pip_name, mod in REQS.items():
                r = subprocess.run([vpy, "-c", "import " + mod], capture_output=True)
                if r.returncode == 0:
                    self.say("  OK        " + mod)
                else:
                    self.say("  MISSING   " + mod)
                    missing.append(pip_name)

            if missing:
                self.state = "installing"
                self.say()
                self.say("Installing %d missing package(s). torch alone is about "
                         "2-3 GB, so the first run can take several minutes."
                         % len(missing))
                subprocess.run([vpy, "-m", "pip", "install", "--upgrade", "pip"],
                               capture_output=True)
                r = subprocess.run([vpy, "-m", "pip", "install"] + missing,
                                   cwd=PROJECT, capture_output=True, text=True)
                if r.returncode != 0:
                    self.say(r.stderr.strip()[-1200:])
                    return self.fail("pip could not install: " + ", ".join(missing))
                self.installed.extend(missing)
                for pip_name, mod in REQS.items():      # verify, do not assume
                    if subprocess.run([vpy, "-c", "import " + mod],
                                      capture_output=True).returncode != 0:
                        return self.fail(mod + " still cannot be imported after "
                                               "installation.")

            # ---- OCR end to end. shutil.which above only proved a binary
            # exists; pytesseract resolves the command itself, so this is the
            # only check that proves screenshot-to-text actually works.
            probe = ("import os, shutil, pytesseract\n"
                     "p = shutil.which('tesseract') or r'" + TESS_WIN + "'\n"
                     "if os.path.exists(p):\n"
                     "    pytesseract.pytesseract.tesseract_cmd = p\n"
                     "pytesseract.get_tesseract_version()\n")
            if subprocess.run([vpy, "-c", probe],
                              capture_output=True).returncode == 0:
                self.say("  OK        OCR pipeline (pytesseract -> tesseract)")
            else:
                self.say("  WARNING   pytesseract cannot reach the tesseract "
                         "engine - screenshot reading will be unavailable, "
                         "everything else works")

            self.say()
            if self.installed:
                self.say("SUCCESSFULLY INSTALLED:")
                for i in self.installed:
                    self.say("   + " + i)
            else:
                self.say("Nothing had to be installed - every required tool was "
                         "already present.")
            self.say("All requirements are satisfied and verified.")
            self.state = "ready"
        except Exception as e:
            self.fail(str(e))

    # ------------------------------------------------ launch
    def _launch(self):
        try:
            self.say()
            self.say("Starting the model server (uvicorn, port %d) ..." % API_PORT)
            self.api = self._spawn(
                [self.vpy, "-m", "uvicorn", "api:app",
                 "--host", "127.0.0.1", "--port", str(API_PORT)],
                os.path.join(LOGDIR, "api.log"), os.path.join(LOGDIR, "api.err"))
            self.say("   loading asea_best_model (mBERT) into memory ...")
            if not wait_port(API_PORT, 240):
                return self.fail("The model server did not start. See logs/api.err.")
            self.say("   model server ready")

            self.say("Starting the website (Streamlit, port %d) ..." % UI_PORT)
            self.ui = self._spawn(
                [self.vpy, "-m", "streamlit", "run", "streamlit_app.py",
                 "--server.port", str(UI_PORT),
                 "--server.headless", "true",
                 "--browser.gatherUsageStats", "false"],
                os.path.join(LOGDIR, "ui.log"), os.path.join(LOGDIR, "ui.err"))
            if not wait_port(UI_PORT, 120):
                return self.fail("Streamlit did not start. See logs/ui.err.")
            self.say("   website ready - opening it in this window")

            webview.windows[0].load_url("http://localhost:%d" % UI_PORT)
            threading.Thread(target=self._watch, daemon=True).start()
        except Exception as e:
            self.fail(str(e))

    def _watch(self):
        """If either server dies on its own, close the app instead of showing
        a broken page."""
        while True:
            time.sleep(2)
            dead = ((self.api and self.api.poll() is not None)
                    or (self.ui and self.ui.poll() is not None))
            if dead:
                self.shutdown()
                try:
                    webview.windows[0].destroy()
                except Exception:
                    pass
                return


SETUP_HTML = """
<!doctype html><html><head><meta charset="utf-8">
<style>
  :root{color-scheme:dark}
  body{margin:0;background:#0b0d12;color:#e7ecf5;
       font:14px/1.5 -apple-system,"Segoe UI",system-ui,sans-serif}
  .wrap{padding:30px 36px}
  h1{margin:0;font-size:22px;letter-spacing:4px}
  .sub{color:#8b96a8;margin:6px 0 18px}
  #log{background:#111521;border:1px solid #1e2534;border-radius:10px;
       padding:14px 16px;height:430px;overflow:auto;white-space:pre-wrap;
       font:12.5px/1.6 ui-monospace,Menlo,Consolas,monospace}
  #bar{margin-top:18px;display:flex;align-items:center;gap:16px}
  button{background:#1f6feb;color:#fff;border:0;border-radius:8px;
         padding:12px 22px;font-size:14px;font-weight:600;letter-spacing:.5px;
         cursor:pointer}
  button[disabled]{background:#222938;color:#5d6577;cursor:default}
  .hint{color:#8b96a8}
  .err{color:#ff7b72}
</style></head><body><div class="wrap">
  <h1>A.S.E.A.</h1>
  <div class="sub">Checking the required tools before launch</div>
  <div id="log"></div>
  <div id="bar">
    <button id="go" disabled>LAUNCH A.S.E.A.</button>
    <span class="hint" id="hint">Please wait ...</span>
  </div>
</div>
<script>
let started = false;
async function tick(){
  const s = await window.pywebview.api.poll();
  const log = document.getElementById('log');
  log.textContent = s.log.join('\\n');
  log.scrollTop = log.scrollHeight;
  const go = document.getElementById('go'), hint = document.getElementById('hint');
  if (s.state === 'installing') hint.textContent = 'Installing missing tools ...';
  if (s.state === 'ready' && !started) {
    go.disabled = false;
    hint.textContent = 'Ready - click LAUNCH or press the 1 key';
  }
  if (s.state === 'running') {
    go.disabled = true;
    hint.textContent = 'Starting the model server and the website ...';
  }
  if (s.state === 'error') {
    go.disabled = true; hint.className = 'err';
    hint.textContent = 'Setup stopped - see the log above.';
  }
}
function launch(){
  if (document.getElementById('go').disabled) return;
  started = true;
  window.pywebview.api.launch();
}
document.getElementById('go').addEventListener('click', launch);
document.addEventListener('keydown', e => { if (e.key === '1') launch(); });
window.addEventListener('pywebviewready', () => {
  window.pywebview.api.preflight();
  setInterval(tick, 400);
});
</script></body></html>
"""

shell = Shell()
window = webview.create_window(APP_TITLE, html=SETUP_HTML, js_api=shell,
                               width=1240, height=860, min_size=(960, 680))
window.events.closing += shell.shutdown     # fires BEFORE the window tears down
window.events.closed += shell.shutdown      # closing the window quits both servers
atexit.register(shell.shutdown)             # belt and braces
webview.start()