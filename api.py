import json, time, hashlib, os, csv, re, unicodedata
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import torch, pandas as pd
from transformers import AutoTokenizer, AutoModelForSequenceClassification

HAM_LABELS = {"HAM", "Ham", "Legit", "Legitimate", "Not Spam"}
MODEL_DIR = "asea_best_model"

# ---------------------------------------------------------------------
#  v5.3 — INPUT NORMALISATION, SERVER-SIDE
#  v5.2 canonicalised the text inside the website, which fixed the
#  "same message, two verdicts" problem for the website only. curl, the
#  /docs page and any future client still sent raw text, so the SAME
#  wording could get a different answer depending on who asked. The
#  canonical form now lives behind the endpoint, where nothing can
#  bypass it. Keep this function byte-identical to the Streamlit copy.
# ---------------------------------------------------------------------
DOT_GLUE_RE = re.compile(r"(?<![A-Z]\.)(?<=[.!?])(?=[A-Z])")   # "Atty.Nympha"
PUNCT_GLUE_RE = re.compile(r"(?<=[,;:])(?=[A-Za-z])")
SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.!?;:])")

def normalize_text(s):
    """Canonical surface form of a message, as fed to the tokenizer."""
    zw = (chr(0x200b), chr(0x200c), chr(0x200d), chr(0xfeff))
    s = "".join(c for c in (s or "") if c not in zw)   # v5.4: chr(), not
    # \u escapes — Notion rewrites them inside code blocks, and the mangled
    # class below was deleting every HYPHEN from the message. Line kept as
    # a comment only: re.sub('[\-\‍\﻿]', "", s or "")      # zero-width junk
    s = unicodedata.normalize("NFKC", s)
    s = (s.replace("‘", "'").replace("’", "'")
          .replace("“", '"').replace("”", '"')
          .replace("–", "-").replace("—", "-"))
    s = re.sub(r"\s+", " ", s)          # line wraps and blank lines -> one space
    s = DOT_GLUE_RE.sub(" ", s)         # leaves bit.ly and U.S.A. intact
    s = PUNCT_GLUE_RE.sub(" ", s)
    s = SPACE_BEFORE_PUNCT_RE.sub(r"\1", s)
    return s.strip()

tok = AutoTokenizer.from_pretrained(MODEL_DIR)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR).eval()
id2label = {int(k): v for k, v in model.config.id2label.items()}
best_name = json.load(open(f"{MODEL_DIR}/meta.json"))["best_model"]

# ---------------- Number reputation (SHA-256, RA 10173 style) ----------------
# Two sources feed one hashed reputation table:
#   (1) reported_numbers.csv — a seed list of already-reported numbers; the API
#       also APPENDS to it whenever a scam text carries a sender number, so a
#       number flagged in Verify Text later shows up in Verify Number.
#   (2) brand sender IDs from the training corpus ("BDO Deals", "GCash", ...),
#       scam rows only. The old corpus was all "N/A" and skipped entirely, so this
#       path never actually ran; V3 populates it, which exposes two bugs it must
#       now guard against:
#         - masked numbers are EXCLUDED. _norm_num strips the "*" out of
#           "+63640****000", producing a key no user-typed number can ever match,
#           and one mask string collapses hundreds of real numbers spanning up to
#           11 different intents into a single meaningless count.
#         - HAM rows are EXCLUDED. Without this, legitimate senders such as "NTC"
#           (70 rows) and "eGovPH" (56) clear the >=30 threshold and Verify Number
#           answers HIGH RISK for a government sender ID.
REPORTS_CSV = "reported_numbers.csv"
rep = {}

def _norm_num(n):
    n = str(n).strip()
    if n in ("", "N/A", "nan", "None"):
        return ""
    return re.sub(r"[^\d+]", "", n) or n.upper()   # ignore spaces / dashes / parentheses; brand IDs are case-folded so "smart" == "SMART"

def _add_report(number, scam_type, n=1):
    num = _norm_num(number)
    if not num:
        return
    e = rep.setdefault(hashlib.sha256(num.encode()).hexdigest(),
                       {"count": 0, "types": {}})
    e["count"] += n
    t = str(scam_type or "Unknown")
    e["types"][t] = e["types"].get(t, 0) + n

def _persist_report(number, scam_type):
    if not _norm_num(number):
        return
    newfile = not os.path.exists(REPORTS_CSV)
    with open(REPORTS_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if newfile:
            w.writerow(["number", "scam_type", "count"])
        w.writerow([_norm_num(number), scam_type or "Unknown", 1])

# (1) seed from reported_numbers.csv (optional `count` column: one row = many reports)
try:
    # encoding="utf-8-sig" is REQUIRED, not optional. If reported_numbers.csv
    # was ever saved from Excel as "CSV UTF-8" it carries a BOM, which makes
    # the first header "﻿number" instead of "number". Every
    # r.get("number", "") then returns "", _norm_num rejects it, and the whole
    # seed table is silently discarded with no error — Verify Number just
    # answers "NO REPORTS FOUND" forever.
    rdf = pd.read_csv(REPORTS_CSV, dtype=str, encoding="utf-8-sig").fillna("")
    for _, r in rdf.iterrows():
        try:
            cnt = max(1, int(float(r.get("count", "") or 1)))
        except Exception:
            cnt = 1
        _add_report(r.get("number", ""), r.get("scam_type", ""), cnt)
except FileNotFoundError:
    pass
except Exception as ex:
    print("reported_numbers.csv skipped:", ex)

# (2) seed from brand sender IDs in the corpus (scam rows only, no masked numbers)
try:
    for _, r in pd.read_csv("Combined-Dataset-V3(Sheet).csv", encoding="utf-8-sig").iterrows():
        sender = str(r.get("masked_celphone_number", "") or "").strip()
        intent = str(r.get("intent", "") or "").strip()
        if not sender or "*" in sender:   # masked numbers are unmatchable — skip
            continue
        if intent in HAM_LABELS:          # NTC, eGovPH, ... are legitimate senders
            continue
        _add_report(sender, intent)
except Exception as ex:
    print("corpus reputation skipped:", ex)

app = FastAPI(title="A.S.E.A. API")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

class TextIn(BaseModel):
    sender: str | None = None
    text: str

class NumIn(BaseModel):
    number: str

class ReportIn(BaseModel):
    number: str
    scam_type: str | None = None

def _spam_prob(text):
    if not text.strip():
        return 0.0
    enc = tok(text, truncation=True, max_length=128, return_tensors="pt")
    with torch.no_grad():
        probs = torch.softmax(model(**enc).logits, dim=1)[0]
    return float(sum(probs[i] for i, l in id2label.items() if l not in HAM_LABELS))

def top_tokens(text, k=5):
    # Occlusion-based attribution (fast SHAP alternative): drop each word,
    # measure how much the spam probability falls.
    base = _spam_prob(text)
    words = text.split()
    scored = [(w, base - _spam_prob(" ".join(words[:i] + words[i+1:])))
              for i, w in enumerate(words)]
    scored.sort(key=lambda x: x[1], reverse=True)
    # v5.5 — return BARE tokens. The old sentence form ("token 'x' pushed
    # toward spam") was rendered verbatim as a chip, so a HAM message still
    # displayed "pushed toward spam" next to a LIKELY LEGITIMATE verdict.
    return [w for w, s in scored[:k] if s > 0]

@app.post("/predict-text")
def predict_text(inp: TextIn):
    t0 = time.time()
    text = normalize_text(inp.text)          # v5.3 — every caller, same form
    enc = tok(text, truncation=True, max_length=128, return_tensors="pt")
    with torch.no_grad():
        probs = torch.softmax(model(**enc).logits, dim=1)[0]
    idx = int(probs.argmax()); conf = float(probs[idx]); label = id2label[idx]
    is_spam = label not in HAM_LABELS
    if is_spam and _norm_num(inp.sender or ""):
        # Option 1: a scam message with a sender number "reports" that number,
        # so Verify Number reflects it (in memory now, and on disk for restarts).
        _add_report(inp.sender, label)
        _persist_report(inp.sender, label)
    return {
        "verdict": "SPAM DETECTED!" if is_spam else "HAM — LIKELY LEGITIMATE",
        "subtype": label if is_spam else None,
        "sub": ("Type of Spam: " + label) if is_spam
               else "No strong scam indicators detected.",
        "confidence": round(conf, 4),
        "latency_ms": round((time.time() - t0) * 1000, 1),
        "model": best_name,
        # v5.5 — no token list for HAM. Occlusion measures how far a word
        # pushes the message TOWARD spam; on a legitimate message that is
        # not an explanation of the verdict, so send nothing.
        "reasons": top_tokens(text) if is_spam else [],
        "normalized_text": text,     # v5.3 — exactly what the model scored
    }

@app.post("/verify-number")
def verify_number(inp: NumIn):
    h = hashlib.sha256(_norm_num(inp.number).encode()).hexdigest()
    info = rep.get(h, {"count": 0, "types": {}})
    count = info["count"]
    top = max(info["types"], key=info["types"].get) if info["types"] else None
    risk = ("HIGH RISK" if count >= 30 else "MEDIUM RISK" if count >= 8
            else "LOW RISK" if count >= 1 else "NO REPORTS FOUND")
    return {"risk": risk, "reports": count, "top_type": top, "hashed": h[:16] + "…"}

@app.post("/report-number")
def report_number(inp: ReportIn):
    # Option 1 (manual): report a number as scam from anywhere (e.g. curl or a
    # future button). Records in memory + appends to reported_numbers.csv.
    if not _norm_num(inp.number):
        return {"ok": False, "error": "no number provided"}
    _add_report(inp.number, inp.scam_type or "Unknown")
    _persist_report(inp.number, inp.scam_type or "Unknown")
    h = hashlib.sha256(_norm_num(inp.number).encode()).hexdigest()
    return {"ok": True, "reports": rep[h]["count"], "hashed": h[:16] + "…"}