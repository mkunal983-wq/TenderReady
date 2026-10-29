import {
  IconArrowRight,
  IconBolt,
  IconShieldCheck,
  IconRefresh,
  IconFileText,
  IconBuilding,
  IconSchool,
  IconBuildingBank,
  IconFiles,
  IconListCheck,
  IconCheck,
} from '@tabler/icons-react';
import './landing.css';

const capabilities = [
  {
    Icon: IconBolt,
    label: 'AI Requirement Extraction',
    detail: 'Clause-by-clause indexing with page citations',
  },
  {
    Icon: IconShieldCheck,
    label: 'Evidence Verification',
    detail: 'Model, entity, dates & threshold checks',
  },
  {
    Icon: IconRefresh,
    label: 'Amendment Tracking',
    detail: 'Instant delta analysis on tender addenda',
  },
  {
    Icon: IconFileText,
    label: 'Exportable Evidence Pack',
    detail: 'Source-linked compliance dossier for submission',
  },
];

const audiences = [
  {
    Icon: IconBuilding,
    title: 'IT Hardware Suppliers',
    desc: 'Verify OEM specifications, part numbers, and warranty thresholds against tender mandates before committing.',
  },
  {
    Icon: IconSchool,
    title: 'Education & Research',
    desc: 'Comply with institutional procurement guidelines, scoring criteria, and strict delivery commitments.',
  },
  {
    Icon: IconBuildingBank,
    title: 'Institutional Procurement',
    desc: 'Ensure rigorous auditability with complete provenance tracking and human sign-off on every clause.',
  },
];

const steps = [
  {
    step: '01',
    title: 'Ingest Tender Documents',
    body: 'Upload the original tender PDF. The system extracts mandatory requirements, technical specs, and commercial clauses with exact page references.',
  },
  {
    step: '02',
    title: 'Verify Supplier Evidence',
    body: 'Upload datasheets, certifications, and supplier proofs. The system validates entity names, specs, and dates—flagging ambiguities or conflicts.',
  },
  {
    step: '03',
    title: 'Track Addenda & Export',
    body: 'When amendments arrive, automatically evaluate which requirements changed. Record human review decisions and export an immutable evidence pack.',
  },
];

export function Landing() {
  return (
    <div className="tr-landing">
      {/* Top Navigation */}
      <header className="tr-nav">
        <a className="tr-logo" href="/" aria-label="TenderReady home">
          <span className="tr-mark">T</span>
          <span>
            <strong>TenderReady</strong>
            <small>Procurement Intelligence</small>
          </span>
        </a>
        <nav aria-label="Main navigation">
          <a href="#product-preview">Product</a>
          <a href="#for-suppliers">Target Sectors</a>
          <a href="#how-it-works">How It Works</a>
          <a href="#workspace-start">Workspaces</a>
        </nav>
        <a className="tr-button tr-primary tr-nav-cta" href="#workspace-start">
          Open Workspaces <IconArrowRight size={15} />
        </a>
      </header>

      {/* Hero Section */}
      <section className="tr-hero" aria-labelledby="tr-headline">
        <div className="tr-hero-copy">
          <div className="tr-eyebrow">
            <span className="tr-eyebrow-dot" aria-hidden="true" />
            <span>AI-POWERED PROCUREMENT & COMPLIANCE</span>
          </div>
          <h1 id="tr-headline">
            From complex tenders to{' '}
            <span className="tr-brand-accent">submission-ready, source-linked</span> evidence.
          </h1>
          <p>
            TenderReady equips IT suppliers and procurement teams to systematically extract requirements,
            cross-verify evidence against original PDFs, and track tender amendments with complete auditability.
          </p>
          <div className="tr-actions">
            <a className="tr-button tr-primary" href="#workspace-start">
              Launch Workspace <IconArrowRight size={17} />
            </a>
            <a className="tr-button tr-secondary" href="#how-it-works">
              <IconListCheck size={17} /> Review Methodology
            </a>
          </div>

          <div className="tr-capabilities">
            {capabilities.map(({ Icon, label, detail }) => (
              <div key={label} className="tr-capability-item">
                <span className="tr-capability-icon">
                  <Icon size={18} />
                </span>
                <div>
                  <strong>{label}</strong>
                  <small>{detail}</small>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Product Showcase */}
        <div className="tr-visual" id="product-preview" aria-label="TenderReady product preview">
          <figure className="tr-app-frame">
            <div className="tr-window-chrome">
              <div className="tr-window-controls" aria-hidden="true">
                <span className="tr-dot red" />
                <span className="tr-dot yellow" />
                <span className="tr-dot green" />
              </div>
              <div className="tr-window-address">
                <span className="tr-lock-icon" aria-hidden="true">🔒</span>
                <span>tenderready.internal/workspaces/tender-audit/readiness</span>
              </div>
              <div className="tr-window-status">
                <span className="tr-status-dot" />
                <span>Nemotron-verified</span>
              </div>
            </div>
            <div className="tr-screenshot-wrapper">
              <img
                src="/tenderready-dashboard.png"
                width="1113"
                height="853"
                alt="Actual TenderReady evidence readiness interface, showing requirements review and audit findings."
                fetchPriority="high"
              />
            </div>
            <figcaption className="tr-caption">
              <span>Production Interface</span>
              <span className="tr-sep">·</span>
              <span>Source-linked evidence verification</span>
              <span className="tr-sep">·</span>
              <span>Human sign-off workflow</span>
            </figcaption>
          </figure>

          {/* Clean, docked annotation callouts */}
          <div className="tr-annotation-bar">
            <div className="tr-annotation-card">
              <span className="tr-annotation-icon teal">
                <IconFiles size={19} />
              </span>
              <div>
                <strong>Tender & Amendment Ingestion</strong>
                <small>Multi-revision PDF clause extraction</small>
              </div>
            </div>
            <div className="tr-annotation-card">
              <span className="tr-annotation-icon green">
                <IconShieldCheck size={19} />
              </span>
              <div>
                <strong>Evidence Cross-Validation</strong>
                <small>Direct page citations for every finding</small>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Target Sectors & Trust Section */}
      <section className="tr-proof" id="for-suppliers" aria-label="Who TenderReady is for">
        <div className="tr-proof-heading">
          <span className="tr-eyebrow-mini">ENTERPRISE-GRADE ASSURANCE</span>
          <h2>Built for procurement teams with zero tolerance for non-compliance</h2>
          <p>
            When submitting multi-million dollar tenders, manual oversight can easily miss a single altered clause or missing certificate. TenderReady creates an immutable trail of proof.
          </p>
        </div>

        <div className="tr-audiences-grid">
          {audiences.map(({ Icon, title, desc }) => (
            <div className="tr-audience-card" key={title}>
              <div className="tr-audience-icon">
                <Icon size={24} />
              </div>
              <h3>{title}</h3>
              <p>{desc}</p>
            </div>
          ))}
        </div>

        <div className="tr-pillars-bar">
          <div className="tr-pillar">
            <span className="tr-pillar-check"><IconCheck size={16} /></span>
            <div>
              <strong>Source-Linked Findings</strong>
              <span>Every extracted requirement traces to exact coordinates and original PDF pages.</span>
            </div>
          </div>
          <div className="tr-pillar">
            <span className="tr-pillar-check"><IconCheck size={16} /></span>
            <div>
              <strong>Change-Aware Engine</strong>
              <span>Immediate impact analysis when addenda introduce modified, removed, or added terms.</span>
            </div>
          </div>
          <div className="tr-pillar">
            <span className="tr-pillar-check"><IconCheck size={16} /></span>
            <div>
              <strong>Human-Led Governance</strong>
              <span>AI assists by pinpointing discrepancies; compliance teams maintain final review approval.</span>
            </div>
          </div>
        </div>
      </section>

      {/* How it Works Section */}
      <section className="tr-how" id="how-it-works">
        <div className="tr-how-heading">
          <span className="tr-eyebrow-mini">STRUCTURED PROCESS</span>
          <h2>From tender dossier to <span>submission-ready proof</span></h2>
          <p>A rigorous three-step audit cycle designed to eliminate blind spots.</p>
        </div>
        <div className="tr-steps">
          {steps.map(({ step, title, body }) => (
            <article className="tr-step-card" key={title}>
              <div className="tr-step-top">
                <span className="tr-step-number">{step}</span>
                <span className="tr-step-tag">Phase {step}</span>
              </div>
              <h3>{title}</h3>
              <p>{body}</p>
            </article>
          ))}
        </div>
        <div className="tr-disclaimer-box">
          <IconShieldCheck size={20} className="tr-disclaimer-icon" />
          <p>
            <strong>Evidence Review Notice:</strong> TenderReady aids internal decision-making by cross-referencing supplier documents against tender clauses. It does not replace internal legal counsel, guarantee statutory eligibility, or assure contract award.
          </p>
        </div>
      </section>
    </div>
  );
}
