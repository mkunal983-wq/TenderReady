import { useState } from 'react';
import {
  IconArrowRight,
  IconShieldCheck,
  IconRefresh,
  IconFileText,
  IconBuilding,
  IconSchool,
  IconBuildingBank,
  IconFiles,
  IconListCheck,
  IconCheck,
  IconFileCertificate,
  IconLock,
  IconScale,
  IconDatabase,
} from '@tabler/icons-react';
import './landing.css';

const metrics = [
  {
    value: '100%',
    label: 'Source-Linked Traceability',
    desc: 'Every requirement and finding links directly to exact PDF page coordinates.',
  },
  {
    value: 'Real-Time',
    label: 'Addendum Delta Diffing',
    desc: 'Immediate impact alerts whenever tender amendments or corrigenda drop.',
  },
  {
    value: 'Zero',
    label: 'Synthetic Hallucination',
    desc: 'Deterministic clause reconciliation against supplier documents.',
  },
  {
    value: 'Human-Led',
    label: 'Governance & Sign-Off',
    desc: 'Compliance officers and legal leads maintain full approval authority.',
  },
];

const pipelineStages = [
  {
    id: 'ingest',
    stage: '01',
    name: 'Ingestion & Clause Intelligence',
    icon: IconFileText,
    subtitle: 'From unstructured multi-hundred page tender dossiers into structured, indexed requirements.',
    features: [
      'Automated extraction of mandatory technical and commercial specifications',
      'Verbatim clause citation with exact page and section coordinates',
      'Document revision indexing across original RFPs and subsequent releases',
      'Categorization by hardware, software, SLA, legal terms, and pricing',
    ],
  },
  {
    id: 'verify',
    stage: '02',
    name: 'Evidence & Specification Reconciliation',
    icon: IconShieldCheck,
    subtitle: 'Cross-verifying supplier datasheets, OEM brochures, and certifications against extracted mandates.',
    features: [
      'Multi-document cross-checks for models, capacities, and technical thresholds',
      'Entity identity, corporate naming, and certificate expiry verification',
      'Automatic detection of spec shortfalls, conflicting claims, and ambiguities',
      'Granular confidence scoring with direct citations into supplier PDFs',
    ],
  },
  {
    id: 'govern',
    stage: '03',
    name: 'Addendum Tracking & Submission Dossier',
    icon: IconFileCertificate,
    subtitle: 'Handling amendment impacts, recording officer reviews, and exporting immutable audit packs.',
    features: [
      'Instant delta alerts highlighting requirements affected by tender addenda',
      'Structured task assignments for review bottlenecks and corrective proof',
      'Immutable audit trail recording reviewer comments and sign-off timestamps',
      'Exportable submission pack with verified compliance matrices and proof links',
    ],
  },
];

const audiences = [
  {
    Icon: IconBuilding,
    title: 'IT Hardware Suppliers',
    desc: 'Verify OEM specifications, part numbers, warranty levels, and delivery commitments against tender mandates before committing bid resources.',
  },
  {
    Icon: IconSchool,
    title: 'Education & Research',
    desc: 'Ensure complete alignment with institutional procurement guidelines, scoring criteria, statutory mandates, and strict tender terms.',
  },
  {
    Icon: IconBuildingBank,
    title: 'Institutional Procurement',
    desc: 'Equip evaluation committees with an unassailable audit trail, verified provenance, and human-in-the-loop sign-off on every clause.',
  },
];

const capabilities = [
  {
    Icon: IconFiles,
    title: 'Multi-Revision PDF Indexing',
    desc: 'Ingest tenders, appendices, and corrigenda with coordinate-level page mapping.',
  },
  {
    Icon: IconScale,
    title: 'Threshold & Constraint Logic',
    desc: 'Enforce numerical limits (RAM, storage, warranty years, SLA response times).',
  },
  {
    Icon: IconRefresh,
    title: 'Automated Addendum Diffs',
    desc: 'Flag modified, added, or removed requirements without re-auditing from scratch.',
  },
  {
    Icon: IconLock,
    title: 'Immutable Evidence Dossier',
    desc: 'Export comprehensive audit packs ready for bid submission and evaluation.',
  },
];

export function Landing() {
  const [selectedStage, setSelectedStage] = useState(0);

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
          <a href="#architecture">Architecture</a>
          <a href="#capabilities">Capabilities</a>
          <a href="#for-suppliers">Target Sectors</a>
          <a href="#workspace-start">Workspaces</a>
        </nav>
        <a className="tr-button tr-primary tr-nav-cta" href="#workspace-start">
          Open Workspaces <IconArrowRight size={15} />
        </a>
      </header>

      {/* Hero Section - Executive Centered Layout (No Screenshots) */}
      <section className="tr-hero" aria-labelledby="tr-headline">
        <div className="tr-hero-inner">
          <div className="tr-eyebrow">
            <span className="tr-eyebrow-dot" aria-hidden="true" />
            <span>AI-POWERED PROCUREMENT & COMPLIANCE INFRASTRUCTURE</span>
          </div>

          <h1 id="tr-headline">
            From complex tenders to <span className="tr-brand-accent">submission-ready, source-linked</span> evidence.
          </h1>

          <p className="tr-hero-lead">
            TenderReady equips IT suppliers and procurement teams to systematically extract requirements,
            cross-verify evidence against original PDFs, and track tender amendments with complete auditability.
          </p>

          <div className="tr-actions">
            <a className="tr-button tr-primary" href="#workspace-start">
              Launch Workspace <IconArrowRight size={17} />
            </a>
            <a className="tr-button tr-secondary" href="#architecture">
              <IconListCheck size={17} /> Explore Architecture
            </a>
          </div>
        </div>

        {/* Executive Metrics Strip */}
        <div className="tr-hero-metrics" role="region" aria-label="Key Platform Guarantees">
          {metrics.map(({ value, label, desc }) => (
            <div className="tr-metric-card" key={label}>
              <span className="tr-metric-value">{value}</span>
              <strong className="tr-metric-label">{label}</strong>
              <p className="tr-metric-desc">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* End-to-End Pipeline Architecture (Interactive, Graphic-Free, No Mockups) */}
      <section className="tr-pipeline-section" id="architecture" aria-labelledby="arch-title">
        <div className="tr-section-heading">
          <span className="tr-eyebrow-mini">END-TO-END METHODOLOGY</span>
          <h2 id="arch-title">Procurement Intelligence Architecture</h2>
          <p>
            A rigorous three-tier compliance engine built to handle high-value tenders where a single missed specification can cause disqualification.
          </p>
        </div>

        <div className="tr-pipeline-container">
          {/* Stage Navigation Tabs */}
          <div className="tr-stage-nav" role="tablist" aria-label="Architecture stages">
            {pipelineStages.map((stage, idx) => {
              const Icon = stage.icon;
              const isActive = selectedStage === idx;
              return (
                <button
                  key={stage.id}
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  className={`tr-stage-tab ${isActive ? 'active' : ''}`}
                  onClick={() => setSelectedStage(idx)}
                >
                  <span className="tr-stage-num">{stage.stage}</span>
                  <div className="tr-stage-tab-text">
                    <span className="tr-stage-name">{stage.name}</span>
                    <small className="tr-stage-sub">Phase {stage.stage}</small>
                  </div>
                  <Icon size={18} className="tr-stage-icon" />
                </button>
              );
            })}
          </div>

          {/* Active Stage Detailed Panel */}
          <div className="tr-stage-detail" role="tabpanel">
            <div className="tr-stage-detail-header">
              <div className="tr-stage-badge">
                <span>PHASE {pipelineStages[selectedStage].stage}</span>
              </div>
              <h3>{pipelineStages[selectedStage].name}</h3>
              <p>{pipelineStages[selectedStage].subtitle}</p>
            </div>

            <div className="tr-stage-features-grid">
              {pipelineStages[selectedStage].features.map((feature, i) => (
                <div className="tr-feature-point" key={i}>
                  <span className="tr-point-check">
                    <IconCheck size={16} />
                  </span>
                  <span>{feature}</span>
                </div>
              ))}
            </div>

            <div className="tr-stage-detail-footer">
              <div className="tr-detail-pill">
                <IconDatabase size={14} /> Deterministic Extraction
              </div>
              <div className="tr-detail-pill">
                <IconLock size={14} /> Immutable Audit Provenance
              </div>
              <div className="tr-detail-pill">
                <IconShieldCheck size={14} /> Nemotron LLM Verified
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Core Platform Capabilities Grid */}
      <section className="tr-capabilities-section" id="capabilities" aria-labelledby="cap-title">
        <div className="tr-section-heading">
          <span className="tr-eyebrow-mini">CORE CAPABILITIES</span>
          <h2 id="cap-title">Built for Audit Integrity & Compliance Rigor</h2>
          <p>Every feature is designed to replace manual spreadsheet cross-referencing with verifiable proof.</p>
        </div>

        <div className="tr-capabilities-grid">
          {capabilities.map(({ Icon, title, desc }) => (
            <div className="tr-capability-card" key={title}>
              <div className="tr-capability-card-icon">
                <Icon size={22} />
              </div>
              <h3>{title}</h3>
              <p>{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Target Sectors & Trust Section */}
      <section className="tr-proof" id="for-suppliers" aria-label="Who TenderReady is for">
        <div className="tr-section-heading">
          <span className="tr-eyebrow-mini">TARGET SECTORS</span>
          <h2>Built for Teams with Zero Tolerance for Non-Compliance</h2>
          <p>
            When preparing multi-million dollar submissions, manual oversight easily misses a single altered clause or missing certificate.
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
