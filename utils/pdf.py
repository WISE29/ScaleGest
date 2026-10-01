"""
Génération de fiches de paie PDF — identique V1.
"""

import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

MONTHS_FR = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril",
    5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août",
    9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
}

ACCENT = colors.HexColor("#6C63FF")
DARK   = colors.HexColor("#1E1E2E")
LIGHT  = colors.HexColor("#F5F5F5")


def generate_payslip_pdf(payroll_data: dict, chatter_name: str, output_dir: str) -> str:
    month_name = MONTHS_FR.get(payroll_data["month"], str(payroll_data["month"]))
    year       = payroll_data["year"]
    safe_name  = chatter_name.replace(" ", "_").replace("/", "-")
    filename   = f"fiche_paie_{safe_name}_{month_name}_{year}.pdf"
    filepath   = os.path.join(output_dir, filename)
    os.makedirs(output_dir, exist_ok=True)

    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "title", parent=styles["Normal"],
        fontSize=18, textColor=ACCENT, alignment=TA_CENTER,
        spaceAfter=6, fontName="Helvetica-Bold"
    )
    subtitle_style = ParagraphStyle(
        "subtitle", parent=styles["Normal"],
        fontSize=11, textColor=DARK, alignment=TA_CENTER, spaceAfter=4
    )
    label_style = ParagraphStyle(
        "label", parent=styles["Normal"],
        fontSize=10, textColor=DARK, alignment=TA_LEFT
    )
    total_style = ParagraphStyle(
        "total", parent=styles["Normal"],
        fontSize=13, textColor=ACCENT, alignment=TA_RIGHT,
        fontName="Helvetica-Bold"
    )

    elements = []
    elements.append(Paragraph("FICHE DE PAIE", title_style))
    elements.append(Paragraph(f"{month_name} {year}", subtitle_style))
    elements.append(Spacer(1, 0.3*cm))
    elements.append(HRFlowable(width="100%", thickness=2, color=ACCENT))
    elements.append(Spacer(1, 0.5*cm))
    elements.append(Paragraph(f"<b>Chatter :</b> {chatter_name}", label_style))
    elements.append(Paragraph(f"<b>Période :</b> {month_name} {year}", label_style))
    elements.append(Spacer(1, 0.6*cm))

    ca_net       = payroll_data["ca_net"]
    base         = payroll_data["base_commission"]
    bonuses      = payroll_data["total_bonuses"]
    penalties    = payroll_data["total_penalties"]
    final        = payroll_data["final_amount"]

    table_data = [
        ["Élément", "Montant"],
        ["CA net total",                   f"{ca_net:,.2f} €"],
        ["Taux de commission",              "8 %"],
        ["Commission de base (CA × 8 %)",  f"{base:,.2f} €"],
        ["Total primes",                   f"+ {bonuses:,.2f} €"],
        ["Total malus",                    f"- {penalties:,.2f} €"],
    ]
    table = Table(table_data, colWidths=[11*cm, 5*cm])
    table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 10),
        ("ALIGN",         (1, 0), (1, -1), "RIGHT"),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("FONTSIZE",      (0, 1), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 0.4*cm))
    elements.append(HRFlowable(width="100%", thickness=1, color=ACCENT))
    elements.append(Spacer(1, 0.3*cm))
    elements.append(Paragraph(f"Net à payer : <b>{final:,.2f} €</b>", total_style))
    elements.append(Spacer(1, 1*cm))

    footer_style = ParagraphStyle(
        "footer", parent=styles["Normal"],
        fontSize=8, textColor=colors.grey, alignment=TA_CENTER
    )
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    elements.append(Spacer(1, 0.2*cm))
    elements.append(Paragraph("Document généré automatiquement — Scale Gest V2", footer_style))
    doc.build(elements)
    return filepath
