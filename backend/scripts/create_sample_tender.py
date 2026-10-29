"""Generate a synthetic two-page PDF for demos/tests; not an actual procurement."""
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak

OUTPUT = Path(__file__).resolve().parents[2] / "samples" / "sample-tender.pdf"
CLAUSES = [
    "The supplier must provide a manufacturer authorization letter naming the bidder and the proposed laptop model.",
    "The bidder must demonstrate one completed IT supply contract with a value of at least INR 1,500,000.",
    "The proposed laptops shall include at least 16 GB of RAM and a 512 GB SSD.",
    "Bids must be received on or before 30 November 2026.",
    "The manufacturer authorization letter must remain valid through 31 March 2027.",
    "The supplier may include an optional onsite training proposal.",
]


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Clause", fontName="Helvetica", fontSize=11, leading=18, spaceAfter=20))
    styles["Title"].textColor = colors.HexColor("#244e3c")
    story = [Paragraph("SYNTHETIC DEMO - NOT A REAL TENDER", styles["Heading3"]),
             Paragraph("University laptop procurement", styles["Title"]),
             Paragraph("TenderReady sample / TR-DEMO-001", styles["Normal"]), Spacer(1, 28),
             Paragraph("1. Supplier and equipment requirements", styles["Heading2"])]
    for clause in CLAUSES[:3]:
        story.append(Paragraph(clause, styles["Clause"]))
    story.extend([PageBreak(), Paragraph("SYNTHETIC DEMO - NOT A REAL TENDER", styles["Heading3"]),
                  Paragraph("2. Submission conditions", styles["Heading2"]), Spacer(1, 12)])
    for clause in CLAUSES[3:]:
        story.append(Paragraph(clause, styles["Clause"]))
    story.append(Paragraph("This sample contains six explicit clauses for testing. It does not establish eligibility or award conditions for any actual procurement.", styles["Normal"]))
    def footer(canvas, doc):
        canvas.setFont("Helvetica", 9)
        canvas.drawString(48, 30, "TenderReady | Synthetic demonstration document")
        canvas.drawRightString(A4[0] - 48, 30, f"Page {doc.page}")
    SimpleDocTemplate(str(OUTPUT), pagesize=A4, leftMargin=48, rightMargin=48, topMargin=48, bottomMargin=54).build(story, onFirstPage=footer, onLaterPages=footer)
    print(OUTPUT)


if __name__ == "__main__":
    main()
