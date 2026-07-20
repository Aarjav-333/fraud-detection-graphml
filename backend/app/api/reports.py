"""Reports & export (workflow Step 15 — final deliverables)."""
import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.alert import Alert
from app.models.case import Case
from app.ml.baseline import load_results
from app.ml.gnn import load_results as load_gnn_results
from app.ml.fraud_ring import load_rings

router = APIRouter(prefix="/api/reports", tags=["reports"], dependencies=[Depends(get_current_user)])


# ----------------------------------------------------------------- CSV exports
EXPORTS = {
    "suspicious_transactions": "Transactions flagged by the rule engine",
    "high_risk_accounts": "Accounts with High risk level or fraud score >= 0.8",
    "alerts": "All fraud alerts with status",
    "cases": "All investigation cases",
}


def _csv_response(header: list, rows: list, filename: str) -> StreamingResponse:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/exports")
def list_exports():
    return [{"name": k, "description": v} for k, v in EXPORTS.items()]


@router.get("/export/{name}")
def export_csv(name: str, db: Session = Depends(get_db)):
    if name == "suspicious_transactions":
        rows = (db.query(Transaction).filter(Transaction.status == "suspicious")
                  .order_by(Transaction.timestamp).all())
        return _csv_response(
            ["txn_uid", "sender_uid", "receiver_uid", "amount", "timestamp", "txn_type", "is_fraud_truth"],
            [[t.txn_uid, t.sender_uid, t.receiver_uid, t.amount,
              t.timestamp.isoformat() if t.timestamp else "", t.txn_type, t.is_fraud] for t in rows],
            "suspicious_transactions.csv",
        )
    if name == "high_risk_accounts":
        rows = (db.query(Account)
                  .filter((Account.risk_level == "High") | (Account.fraud_score >= 0.8))
                  .order_by(Account.fraud_score.desc()).all())
        return _csv_response(
            ["account_uid", "customer_name", "risk_level", "fraud_score", "is_active", "is_fraud_truth"],
            [[a.account_uid, a.customer_name, a.risk_level, a.fraud_score, a.is_active, a.is_fraud] for a in rows],
            "high_risk_accounts.csv",
        )
    if name == "alerts":
        rows = db.query(Alert).order_by(Alert.id).all()
        return _csv_response(
            ["alert_uid", "transaction_uid", "account_uid", "reason", "fraud_score", "risk_level", "status", "created_at"],
            [[a.alert_uid, a.transaction_uid or "", a.account_uid, a.reason, a.fraud_score,
              a.risk_level, a.status, a.created_at.isoformat() if a.created_at else ""] for a in rows],
            "alerts.csv",
        )
    if name == "cases":
        rows = db.query(Case).order_by(Case.id).all()
        return _csv_response(
            ["case_uid", "alert_uid", "account_uid", "assigned_to", "status", "final_decision", "notes", "created_at"],
            [[c.case_uid, c.alert_uid or "", c.account_uid, c.assigned_to or "", c.status,
              c.final_decision or "", (c.notes or "").replace("\n", " "),
              c.created_at.isoformat() if c.created_at else ""] for c in rows],
            "cases.csv",
        )
    raise HTTPException(status_code=404, detail=f"Unknown export '{name}'")


# ----------------------------------------------------------------- PDF report
@router.get("/summary-pdf")
def summary_pdf(db: Session = Depends(get_db)):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    )

    styles = getSampleStyleSheet()
    h1 = styles["Title"]
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], spaceBefore=14)
    body = styles["BodyText"]

    def stat_table(data, col_widths=None):
        t = Table(data, colWidths=col_widths, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4338ca")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return t

    # ---- gather data ----
    total_accounts = db.query(Account).count()
    fraud_accounts = db.query(Account).filter(Account.is_fraud == 1).count()
    high_risk = db.query(Account).filter(Account.risk_level == "High").count()
    total_txns = db.query(Transaction).count()
    sus_txns = db.query(Transaction).filter(Transaction.status == "suspicious").count()
    sus_volume = (db.query(func.coalesce(func.sum(Transaction.amount), 0))
                    .filter(Transaction.status == "suspicious").scalar())
    alert_status = dict(db.query(Alert.status, func.count()).group_by(Alert.status).all())
    case_status = dict(db.query(Case.status, func.count()).group_by(Case.status).all())
    ml = load_results()
    gnn = load_gnn_results() or {}
    rings = load_rings()

    # ---- build document ----
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.6 * cm, bottomMargin=1.6 * cm)
    story = [
        Paragraph("Financial Fraud Detection with Graph ML", h1),
        Paragraph(f"System Summary Report — generated {datetime.now().strftime('%d %b %Y, %H:%M')}",
                  ParagraphStyle("sub", parent=body, textColor=colors.HexColor("#64748b"))),
        Spacer(1, 10),

        Paragraph("1. Data Overview", h2),
        stat_table([
            ["Metric", "Value"],
            ["Total accounts", f"{total_accounts:,}"],
            ["Ground-truth fraud accounts", f"{fraud_accounts:,}"],
            ["High-risk accounts (after detection)", f"{high_risk:,}"],
            ["Total transactions", f"{total_txns:,}"],
            ["Suspicious transactions (rule engine)", f"{sus_txns:,}"],
            ["Suspicious money volume", f"Rs {sus_volume:,.0f}"],
        ], [9 * cm, 6 * cm]),
    ]

    story.append(Paragraph("2. Machine Learning Performance", h2))
    if ml:
        rows = [["Model", "Accuracy", "Precision", "Recall", "F1", "ROC-AUC"]]
        for name, m in ml["results"].items():
            rows.append([name.replace("_", " ").title(),
                         f"{m['accuracy']:.3f}", f"{m['precision']:.3f}",
                         f"{m['recall']:.3f}", f"{m['f1']:.3f}", f"{m.get('roc_auc', 0):.3f}"])
        story.append(stat_table(rows))
        story.append(Paragraph(
            f"Best baseline model: <b>{ml['best_model'].replace('_', ' ').title()}</b>. "
            f"Top features included: {', '.join(f['feature'] for f in ml['top_features'][:5])}.", body))
    else:
        story.append(Paragraph("Baseline models not trained yet.", body))

    if gnn:
        rows = [["Source", "Model", "F1", "ROC-AUC", "Train time (s)"]]
        for key, r in gnn.items():
            rows.append([r["source"], r["model"].upper(),
                         f"{r['metrics']['f1']:.3f}", f"{r['metrics'].get('roc_auc') or 0:.3f}",
                         str(r["train_seconds"])])
        story.append(Spacer(1, 6))
        story.append(Paragraph("Graph Neural Network results:", body))
        story.append(stat_table(rows))

    story.append(Paragraph("3. Fraud Rings", h2))
    if rings:
        story.append(Paragraph(
            f"Detected <b>{rings['rings_found']}</b> rings involving "
            f"<b>{rings['accounts_involved']:,}</b> accounts; total suspicious flow "
            f"Rs {rings['total_flow']:,.0f}. High-risk rings: {rings['high_risk_rings']}.", body))
        top = rings["rings"][:5]
        rows = [["Ring", "Size", "Main account", "Money flow", "Avg score"]]
        for r in top:
            rows.append([r["ring_id"], str(r["size"]), r["main_account"],
                         f"Rs {r['total_flow']:,.0f}", f"{r['avg_fraud_score']:.2f}"])
        story.append(stat_table(rows))
    else:
        story.append(Paragraph("Ring detection not run yet.", body))

    story.append(Paragraph("4. Alerts & Investigations", h2))
    rows = [["Alert status", "Count"]] + [[k, str(v)] for k, v in alert_status.items()]
    story.append(stat_table(rows, [9 * cm, 6 * cm]))
    if case_status:
        story.append(Spacer(1, 6))
        rows = [["Case status", "Count"]] + [[k, str(v)] for k, v in case_status.items()]
        story.append(stat_table(rows, [9 * cm, 6 * cm]))
    else:
        story.append(Paragraph("No investigation cases created yet.", body))

    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "Generated by the Fraud Detection GraphML system — FastAPI, React, NetworkX, "
        "scikit-learn, XGBoost, PyTorch Geometric.", 
        ParagraphStyle("footer", parent=body, fontSize=8, textColor=colors.HexColor("#94a3b8"))))

    doc.build(story)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=fraud_detection_summary.pdf"},
    )
