"""Synthetic fixtures, deliberately simple labelled fields; not real certificates."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
OUTPUT = Path(__file__).resolve().parents[2] / 'samples' / 'verification'
PRODUCT = 'Model: Atlas A14\nRAM: at least 16 GB'
VALIDITY = 'Valid until: 2027-03-31'
PROJECT = 'Project value: at least INR 1500000'
SAMPLES = {
    'tender.pdf': ('Laptop tender requirements', PRODUCT + '\n\n' + VALIDITY + '\n\n' + PROJECT),
    'wrong-model.pdf': ('Product datasheet - wrong model', 'Model: Atlas A15\nRAM: 16 GB\nStorage: 512 GB'),
    'insufficient-ram.pdf': ('Product datasheet - insufficient RAM', 'Model: Atlas A14\nRAM: 8 GB\nStorage: 512 GB'),
    'matching-datasheet.pdf': ('Product datasheet - matching fields', 'Model: Atlas A14\nRAM: 16 GB\nStorage: 512 GB'),
    'expired-certificate.pdf': ('Company certificate - expired', 'Bidder: Demo Supplier Pvt Ltd\nCertificate number: DEMO-001\nValid until: 2025-03-31'),
    'wrong-bidder.pdf': ('Company certificate - wrong legal entity', 'Bidder: Another Supplier Pvt Ltd\nCertificate number: DEMO-002\nValid until: 2027-03-31'),
    'small-project.pdf': ('Previous-project reference - insufficient value', 'Bidder: Demo Supplier Pvt Ltd\nProject reference: DEMO-PROJECT-001\nProject value: INR 1200000'),
}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for filename, (title, text) in SAMPLES.items():
        c = canvas.Canvas(str(OUTPUT / filename), pagesize=A4)
        c.setTitle(title)
        c.setFillColorRGB(.14,.30,.23); c.setFont('Helvetica-Bold',18); c.drawString(48,780,title)
        c.setFillColorRGB(.55,.2,.14); c.setFont('Helvetica-Bold',10)
        c.drawString(48,750,'SYNTHETIC TEST FIXTURE - NOT A REAL PROCUREMENT DOCUMENT')
        c.setFillColorRGB(.1,.1,.1); c.setFont('Helvetica',12)
        y=700
        for line in text.splitlines():
            c.drawString(48,y,line); y-=24
        c.setFont('Helvetica',10)
        c.drawString(48,100,'These sample facts are fictional. No manufacturer or authority has verified them.')
        c.drawString(48,50,'TenderReady deterministic verification fixtures | Page 1')
        c.save()
    print(f'Created {len(SAMPLES)} synthetic PDFs in {OUTPUT}')


if __name__ == '__main__': main()
