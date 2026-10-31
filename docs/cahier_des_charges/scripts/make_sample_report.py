"""Génère un rapport PDF FICTIF contenant une section « Matériel et méthodes ».

Usage : python3 make_sample_report.py rapport_exemple.pdf
"""
import sys

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

import os

from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

out = sys.argv[1] if len(sys.argv) > 1 else "rapport_exemple.pdf"
st = getSampleStyleSheet()

# Police TrueType (pour afficher µ et °) ; sinon Helvetica.
FONT, FONTB = "Helvetica", "Helvetica-Bold"
for normal, gras in [("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                      "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
                     ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
                     ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf")]:
    if os.path.exists(normal) and os.path.exists(gras):
        pdfmetrics.registerFont(TTFont("Corps", normal))
        pdfmetrics.registerFont(TTFont("Corps-Bold", gras))
        FONT, FONTB = "Corps", "Corps-Bold"
        break


def entete_pied(canvas, doc):
    canvas.saveState()
    canvas.setFont(FONT, 8)
    canvas.drawString(18 * mm, 285 * mm, "Rapport d'essai interne - Document fictif")
    canvas.drawRightString(192 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                        topMargin=22 * mm, bottomMargin=18 * mm)
P = ParagraphStyle("p", parent=st["Normal"], fontName=FONT)
H1 = ParagraphStyle("h1", parent=st["Heading1"], fontName=FONTB)
H2 = ParagraphStyle("h2", parent=st["Heading2"], fontName=FONTB)
TITRE = ParagraphStyle("t", parent=st["Title"], fontName=FONTB)

story = [
    Paragraph("Prétraitement d'une graisse animale", TITRE),
    Paragraph("Sommaire", H2),
    Paragraph("1. Introduction ........................................ 1", P),
    Paragraph("2. Matériel et méthodes ................................ 1", P),
    Paragraph("3. Résultats ........................................... 2", P),
    Paragraph("4. Conclusion .......................................... 2", P),
    Spacer(1, 6 * mm),
    Paragraph("1. Introduction", H1),
    Paragraph("Cet essai évalue l'effet d'un prétraitement sur l'acidité d'une graisse animale "
              "destinée à la valorisation. Le rapport décrit le protocole puis les résultats "
              "obtenus.", P),
    Spacer(1, 150 * mm),
    Paragraph("2. Matériel et méthodes", H1),
    Paragraph("2.1 Échantillon", H2),
    Paragraph("La graisse animale étudiée (lot 000412) a été fournie par le service R&amp;D. Un "
              "volume de 1 000 mL a été utilisé comme volume de départ, dont 50 mL ont été "
              "prélevés avant traitement (échantillon S0).", P),
    Paragraph("2.2 Matériel et réactifs", H2),
    Paragraph("Le chauffage et l'agitation ont été assurés par une plaque chauffante agitatrice. "
              "La filtration a été réalisée sous vide avec un entonnoir Büchner, une fiole à vide "
              "et une membrane de 5 µm. Une ampoule à décanter de 500 mL et une étuve ont "
              "complété le montage. L'éthanol à 96 % et l'eau distillée ont servi de solvants.", P),
    Paragraph("2.3 Méthodes", H2),
    Paragraph("La graisse a été chauffée à 60 °C pendant 30 min sous agitation (300 tr/min), "
              "puis filtrée sous vide sur membrane de 5 µm. Elle a ensuite été désacidifiée à "
              "l'éthanol 96 % (ratio 1:1 v/v) additionné d'eau distillée (5 % v/v) pendant 15 min à 25 °C dans une ampoule à décanter "
              "de 500 mL. La phase grasse a été décantée pendant 2 h à 40 °C, puis séchée à "
              "l'étuve à 105 °C pendant 1 h.", P),
    Paragraph("3. Résultats", H1),
    Paragraph("Le taux d'acides gras libres passe de 12,40 % avant traitement à 3,12 % après "
              "séchage. La teneur en eau finale est de 0,08 %.", P),
    Paragraph("4. Conclusion", H1),
    Paragraph("Le protocole réduit nettement l'acidité de la graisse.", P),
]
doc.build(story, onFirstPage=entete_pied, onLaterPages=entete_pied)
print("PDF écrit :", out)
