cat > README.md <<'EOF'
# A.S.E.A. — SMS Scam Detection and Triage System

A 12-class scam intent classifier for Philippine SMS messages, built to handle
code-switched Tagalog-English fraud that generic spam filters miss.

Undergraduate capstone project, BS Computer Science, Angeles University Foundation.

## Problem

Filipinos receive a high volume of SMS scams. Off-the-shelf spam filters are
trained largely on English text and perform poorly on Taglish messages that mix
languages mid-sentence. A.S.E.A. classifies incoming messages into 12 scam intent
categories so they can be triaged rather than just flagged.

## Results

Six transformer models were fine-tuned and benchmarked against three classical
baselines on the same dataset split.

| Model | Accuracy | Macro F1 | AUC-ROC | Latency |
|---|---|---|---|---|
| **mBERT** (selected) | 77.3% | **0.733** | 0.963 | 8.2 ms |
| Tagalog-RoBERTa | 77.9% | 0.701 | 0.967 | 7.4 ms |
| SVM (baseline) | 79.6% | 0.686 | 0.948 | 3.9 ms |
| ALBERT | 77.2% | 0.660 | 0.955 | 8.6 ms |
| Tagalog-BERT | 77.5% | 0.633 | 0.945 | 7.8 ms |
| LSTM (baseline) | 76.3% | 0.631 | 0.944 | 0.6 ms |
| Tagalog-DistilBERT | 75.9% | 0.618 | 0.936 | 4.1 ms |
| Tagalog-ELECTRA | 73.1% | 0.541 | 0.933 | 9.0 ms |
| Naive Bayes (baseline) | 75.0% | 0.537 | 0.912 | 1.0 ms |

**On model selection:** SVM has the highest raw accuracy, but selection was made
on macro F1. With 12 unevenly sized scam categories, accuracy rewards predicting
the frequent classes well while ignoring rare ones. Macro F1 weights every class
equally, which matches the goal of catching all scam types rather than only the
common ones. Full per-run metrics are in `model_comparison.csv`; the confusion
matrix is in `confusion_matrix.csv` and `confusion_matrix.png`.

## Stack

Python, PyTorch, HuggingFace Transformers, FastAPI, Streamlit, Firebase,
Scrapy, Tesseract OCR, SHAP

## Repository contents

| Path | Description |
|---|---|
| `streamlit_app.py` | Web interface with Firebase auth |
| `api.py` | FastAPI inference service |
| `asea_desktop.py` | Desktop client |
| `train.csv` / `val.csv` / `test.csv` | Dataset splits |
| `Combined_Dataset_Augmented.csv` | Augmented training data |
| `Final_Dataset/` | Merged source dataset |
| `model_comparison.csv` | Full benchmark results |
| `confusion_matrix.csv` / `.png` | Best-model confusion matrix |
| `labels.json` | Class label mapping |
| `asea_best_model/` | Model config and tokenizer settings |

Trained weights (~711 MB) are excluded from version control. See Setup.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# fill in your Firebase credentials

streamlit run streamlit_app.py
```

To run the API instead:

```bash
uvicorn api:app --reload
```

## Model weights

`asea_best_model/model.safetensors` is not in this repository due to size limits.
Download it from the Releases page and place it in `asea_best_model/`.

## Data and privacy

The dataset contains SMS messages collected for research. User-submitted reports,
message history, and profile data generated at runtime are excluded from version
control and are not published here.

## Authors

Christopher Pineda, Andrei Lorenzo A. Gumiran, Christian Paul L. Santana,
Louis Felice D. Vicencio, James A. Esquivel

College of Computer Studies, Angeles University Foundation

A research paper based on this work is in preparation, targeting SOICT 2026.
EOF