import { IconArrowRight, IconBolt, IconShieldCheck, IconRefresh, IconFileText, IconBuilding, IconSchool, IconBuildingBank, IconClipboardCheck, IconChevronDown, IconCheck, IconFiles, IconListCheck } from '@tabler/icons-react';
import { FlipWords } from './ui/flip-words';
import './landing.css';

const outcomes = ['submission-ready', 'source-linked', 'review-ready'];
const features = [
  { Icon: IconBolt, label: 'AI requirement', detail: 'extraction', color: 'violet' },
  { Icon: IconShieldCheck, label: 'Evidence', detail: 'verification', color: 'green' },
  { Icon: IconRefresh, label: 'Amendment', detail: 'impact tracking', color: 'orange' },
  { Icon: IconFileText, label: 'Exportable', detail: 'evidence pack', color: 'blue' },
];

export function Landing() {
  return <div className="tr-landing">
    <header className="tr-nav">
      <a className="tr-logo" href="/" aria-label="TenderReady home"><span className="tr-mark">T</span><span><strong>TenderReady</strong><small>Procurement Intelligence</small></span></a>
      <nav aria-label="Main navigation"><a href="#product-preview">Product</a><a href="#how-it-works">Solution <IconChevronDown size={13}/></a><a href="#for-suppliers">For Suppliers <IconChevronDown size={13}/></a><a href="#how-it-works">How it works</a></nav>
      <a className="tr-button tr-primary tr-nav-cta" href="#workspace-start">Get started <IconArrowRight size={17}/></a>
    </header>
    <section className="tr-hero" aria-labelledby="tr-headline">
      <div className="tr-hero-copy">
        <div className="tr-eyebrow">AI-POWERED PROCUREMENT ASSISTANT</div>
        <h1 id="tr-headline"><span className="sr-only">From complex tenders to submission-ready, source-linked evidence.</span><span aria-hidden="true">From complex<br/>tenders to<br/><span className="tr-flip"><FlipWords words={outcomes} className="tr-gradient-word px-0"/></span><br/>evidence.</span></h1>
        <p>TenderReady helps IT suppliers prepare, verify, and manage tender documentation with AI — so every requirement has the right evidence, and every change is accounted for.</p>
        <div className="tr-actions"><a className="tr-button tr-primary" href="#workspace-start">Start your workspace <IconArrowRight size={19}/></a><a className="tr-button tr-secondary" href="#how-it-works"><IconListCheck size={19}/> See how it works</a></div>
        <div className="tr-features">{features.map(({Icon,label,detail,color}) => <div key={label}><span className={`tr-feature-icon ${color}`}><Icon size={21}/></span><span>{label}<br/>{detail}</span></div>)}</div>
      </div>
      <div className="tr-visual" id="product-preview" aria-label="TenderReady product preview">
        <div className="tr-ribbon tr-ribbon-one" aria-hidden="true"/><div className="tr-ribbon tr-ribbon-two" aria-hidden="true"/>
        <div className="tr-doc-chip tr-original"><span className="tr-file-icon pink"><IconFileText size={26}/></span><span>Tender PDF<small>Original document</small></span></div>
        <div className="tr-doc-chip tr-amendment"><span className="tr-file-icon blue"><IconFiles size={26}/></span><span>Amendment<small>Version history</small></span></div>
        <div className="tr-extraction"><span className="tr-ring"/><span>Source-linked requirements<span className="tr-skeleton"/><span className="tr-skeleton short"/></span></div>
        <figure className="tr-dashboard">
          <div className="tr-dashboard-bar"><span className="tr-mini-mark">T</span><b>TenderReady</b><span className="tr-preview-badge">SYNTHETIC AUDIT EXAMPLE</span></div>
          <img src="/tenderready-dashboard.png" width="1113" height="853" alt="Actual TenderReady evidence readiness interface, showing two requirements that need human review." fetchPriority="high"/>
          <figcaption>Actual interface · Example data · Human review required</figcaption>
        </figure>
        <div className="tr-float-card tr-evidence"><span className="tr-file-icon green"><IconShieldCheck size={27}/></span><div><strong>Evidence verification</strong><small>Model, entity, dates & thresholds</small><div className="tr-check-note"><IconCheck size={13}/> Trace every finding to its source</div></div></div>
        <a href="#how-it-works" className="tr-float-card tr-impact"><span className="tr-file-icon orange"><IconRefresh size={26}/></span><div><strong>Amendment impact</strong><small>Reassess affected requirements</small><span className="tr-mini-link">Explore the workflow <IconArrowRight size={13}/></span></div></a>
      </div>
    </section>
    <section className="tr-proof" id="for-suppliers" aria-label="Who TenderReady is for">
      <div className="tr-audiences"><strong>Built for procurement teams</strong><div>{[{Icon:IconBuilding,label:<>IT Hardware<br/>Suppliers</>},{Icon:IconSchool,label:<>Schools &<br/>Universities</>},{Icon:IconBuildingBank,label:<>Institutional<br/>Procurement</>}].map(({Icon,label},i)=><span className="tr-audience" key={i}><Icon size={25}/><span>{label}</span></span>)}</div></div>
      <div className="tr-principles"><div><b>Source-linked</b><span>evidence & findings</span></div><div><b>Change-aware</b><span>requirement review</span></div><div><b>Human-led</b><span>approval decisions</span></div></div>
    </section>
    <section className="tr-how" id="how-it-works">
      <span className="tr-eyebrow">HOW IT WORKS</span><h2>From tender to <span>traceable evidence</span></h2><p>A structured workflow to help you stay compliant and submit with confidence.</p>
      <div className="tr-steps">{[{Icon:IconFileText,title:'Bring your tender',body:'Create a workspace and upload the tender PDF. Review extracted clauses with exact page references.'},{Icon:IconShieldCheck,title:'Check the evidence',body:'Upload supplier documents. Inspect identity, dates and thresholds, then resolve discrepancies.'},{Icon:IconClipboardCheck,title:'Review every change',body:'Upload amendments, reassess affected findings, approve your decisions and export the evidence pack.'}].map(({Icon,title,body},i)=><article key={title}><div><Icon size={23}/><span>0{i+1}</span></div><h3>{title}</h3><p>{body}</p></article>)}</div>
      <p className="tr-disclaimer">Evidence review supports your decisions. It does not guarantee eligibility, document authenticity, or contract award.</p>
    </section>
  </div>;
}
