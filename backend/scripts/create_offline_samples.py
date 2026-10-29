"""Regenerate clearly marked, text-based fixtures. Requires dev reportlab."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'frontend/public/samples/offline'
RAM = 'Requirement ID: RAM-01\nObligation: mandatory\nModel: Atlas A14\nRAM: at least 16 GB\nEnd requirement'
SSD = 'Requirement ID: SSD-01\nObligation: mandatory\nModel: Atlas A14\nStorage: at least 512 GB\nEnd requirement'
SAMPLES = {
    'original-tender.pdf': [('Original tender - memory', RAM), ('Original tender - storage', SSD)],
    'ram-amendment.pdf': [('RAM amendment - 32 GB minimum', RAM.replace('16 GB', '32 GB'))],
    'datasheet-16gb.pdf': [('Original supplier datasheet', 'Model: Atlas A14\nRAM: 16 GB\nStorage: 512 GB')],
    'replacement-32gb.pdf': [('Replacement supplier datasheet', 'Model: Atlas A14\nRAM: 32 GB\nStorage: 512 GB')],
    'wrong-model.pdf': [('Mismatched supplier datasheet', 'Model: Atlas B20\nRAM: 32 GB\nStorage: 512 GB')],
}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for filename, pages in SAMPLES.items():
        c = canvas.Canvas(str(OUTPUT / filename), pagesize=A4, invariant=1)
        c.setTitle('TenderReady SYNTHETIC SAMPLE - ' + filename)
        for number, (title, body) in enumerate(pages, 1):
            c.setFont('Helvetica-Bold', 11)
            c.drawString(45, 790, 'SYNTHETIC SAMPLE - NOT AN ACTUAL TENDER OR SUPPLIER RECORD')
            c.setFont('Helvetica-Bold', 16)
            c.drawString(45, 750, title)
            c.setFont('Helvetica', 12)
            y = 695
            for line in body.splitlines():
                c.drawString(45, y, line)
                y -= 26
            c.setFont('Helvetica', 9)
            c.drawString(45, 55, f'TenderReady offline workflow test | Page {number} | No AI inference')
            c.showPage()
        c.save()
    print(f'Generated {len(SAMPLES)} synthetic PDFs.')


if __name__ == '__main__':
    main()
