"""Three synthetic PDFs for an actual amendment-reassessment demonstration."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
OUTPUT=Path(__file__).resolve().parents[2]/'samples'/'amendments'
RAM16='Requirement ID: RAM-01\nModel: Atlas A14\nRAM: at least 16 GB'
RAM32=RAM16.replace('16 GB','32 GB')
STORAGE='Requirement ID: SSD-01\nModel: Atlas A14\nStorage: at least 512 GB'
SAMPLES={
 'original-tender.pdf':('Original laptop tender',RAM16+'\n\n'+STORAGE),
 'ram-corrigendum.pdf':('Corrigendum - revised RAM requirement',RAM32),
 'supplier-datasheet.pdf':('Supplier datasheet - Atlas A14','Model: Atlas A14\nRAM: 16 GB\nStorage: 512 GB'),
}


def main():
    OUTPUT.mkdir(exist_ok=True,parents=True)
    for name,(title,body) in SAMPLES.items():
        c=canvas.Canvas(str(OUTPUT/name),pagesize=A4)
        c.setTitle(title);c.setFillColorRGB(.14,.30,.23);c.setFont('Helvetica-Bold',17);c.drawString(48,780,title)
        c.setFillColorRGB(.5,.18,.13);c.setFont('Helvetica-Bold',10);c.drawString(48,750,'SYNTHETIC DEMONSTRATION - NOT AN ACTUAL TENDER')
        c.setFillColorRGB(.1,.1,.1);c.setFont('Helvetica',12);y=700
        if name != 'supplier-datasheet.pdf': body=body.replace('\n\n','\nEnd requirement\n\n')+'\nEnd requirement'
        for line in body.splitlines():c.drawString(48,y,line);y-=24
        c.drawString(48,y,'')
        c.setFont('Helvetica',9);c.drawString(48,50,'TenderReady | Synthetic amendment test | Page 1');c.save()
    print('Created original tender, partial RAM corrigendum, and matching original datasheet.')


if __name__=='__main__': main()
