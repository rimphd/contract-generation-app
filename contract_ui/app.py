#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import requests
from io import BytesIO
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from dotenv import load_dotenv
load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "meta-llama/llama-3.1-70b-instruct"  # change si besoin

app = Flask(__name__)
app.secret_key = "dev-secret"  # change en prod

def call_openrouter(model_id: str, prompt: str, temperature: float = 0.4, max_tokens: int = 1600) -> str:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY manquante. Défini-la dans ton terminal avant de lancer l'app.")
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "Contract-UI",
    }
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": "Tu es un assistant juridique et tu rédiges des contrats complets et soignés."},
            {"role": "user", "content": prompt},
        ],
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
        "stream": False,
    }
    r = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=180)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"].strip()

def build_prompt(p):
    return f"""
Tu es un assistant juridique. Génère un contrat de location (contrat de bail) clair et professionnel.

Paramètres:
- LOCATAIRE: {p['tenant_name']}
- BAILLEUR: {p['landlord_name']}
- LOYER_MENSUEL: {p['rent']} MAD
- DEPOT_DE_GARANTIE: {p['security_deposit']} MAD
- DUREE_MOIS: {p['duration_months']} mois
- ADRESSE: {p['address']}
- DATE_DEBUT: {p['start_date']}

Exigences de sortie:
- Rédige le contrat COMPLET en français, style formel (1–2 pages).
- Pas de JSON ni de code block. Retourne du TEXTE pur prêt à copier.
- Inclure: identité des parties, objet/adresse du bien, durée/renouvellement, loyer et paiement,
  dépôt de garantie, obligations bailleur/locataire, réparations/charges, résiliation/préavis,
  état des lieux, clause de juridiction/applicable, signatures (placeholders).
""".strip()

def make_docx(title: str, text: str) -> BytesIO:
    buf = BytesIO()
    doc = Document()
    doc.add_heading(title, level=0)
    for para in text.split("\n\n"):
        doc.add_paragraph(para.strip())
    doc.save(buf)
    buf.seek(0)
    return buf

def make_pdf(title: str, text: str) -> BytesIO:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Spacer(1, 0.5*cm)]
    for para in text.split("\n\n"):
        story.append(Paragraph(para.replace("\n", "<br/>"), styles["Normal"]))
        story.append(Spacer(1, 0.3*cm))
    doc.build(story)
    buf.seek(0)
    return buf

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", default_model=DEFAULT_MODEL)

@app.route("/generate", methods=["POST"])
def generate():
    form = request.form
    params = {
        "tenant_name": form.get("tenant_name","").strip(),
        "landlord_name": form.get("landlord_name","").strip(),
        "rent": form.get("rent","").strip(),
        "security_deposit": form.get("security_deposit","").strip(),
        "duration_months": form.get("duration_months","").strip(),
        "address": form.get("address","").strip(),
        "start_date": form.get("start_date","").strip(),
    }
    # validation simple
    missing = [k for k,v in params.items() if not v]
    if missing:
        flash(f"Champs manquants : {', '.join(missing)}", "danger")
        return redirect(url_for("index"))

    model_id = form.get("model_id") or DEFAULT_MODEL
    temperature = float(form.get("temperature", "0.4"))

    prompt = build_prompt(params)
    try:
        contract_text = call_openrouter(model_id, prompt, temperature=temperature)
    except Exception as e:
        flash(str(e), "danger")
        return redirect(url_for("index"))

    return render_template("result.html", contract_text=contract_text, params=params,
                           model_id=model_id, temperature=temperature)

@app.post("/download-docx")
def download_docx_no_db():
    text = request.form.get("contract_text", "")
    if not text.strip():
        flash("Pas de contrat à télécharger.", "danger")
        return redirect(url_for("index"))
    buf = make_docx("Contrat de location", text)
    return send_file(buf,
                     as_attachment=True,
                     download_name="contrat.docx",
                     mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

@app.post("/download-pdf")
def download_pdf_no_db():
    text = request.form.get("contract_text", "")
    if not text.strip():
        flash("Pas de contrat à télécharger.", "danger")
        return redirect(url_for("index"))
    buf = make_pdf("Contrat de location", text)
    return send_file(buf,
                     as_attachment=True,
                     download_name="contrat.pdf",
                     mimetype="application/pdf")

if __name__ == "__main__":
    app.run(debug=True)
