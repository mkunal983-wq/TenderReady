import { useState } from 'react';
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
  IconAlertTriangle,
  IconFileCertificate,
  IconClock,
  IconLock,
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

type DemoTab = 'matched' | 'amendment' | 'signoff';

export function Landing() {
  const [activeTab, setActiveTab] = useState<DemoTab>('matched');

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

        {/* Live Interactive Procurement Audit Workbench (Replaces static screenshot) */}
        <div className="tr-visual" id="product-preview" aria-label="TenderReady interactive demo">
          <div className="tr-workbench">
            {/* Top Bar with Workspace Context */}
            <div className="tr-workbench-header">
              <div className="tr-workbench-meta">
                <span className="tr-badge-live">LIVE AUDIT WORKSPACE</span>
                <span className="tr-workbench-title">RFP-2026-IT · University Laptop Procurement</span>
              </div>
              <div className="tr-workbench-stats">
                <span className="tr-stat-pill green">
                  <span className="tr-stat-num">22</span> Verified
                </span>
                <span className="tr-stat-pill amber">
                  <span className="tr-stat-num">1</span> Review Flag
                </span>
                <span className="tr-stat-pill blue">
                  <span className="tr-stat-num">1</span> Addendum Delta
                </span>
              </div>
            </div>

            {/* Interactive Tab Switcher */}
            <div className="tr-workbench-tabs" role="tablist" aria-label="Audit findings view">
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'matched'}
                className={`tr-tab-btn ${activeTab === 'matched' ? 'active' : ''}`}
                onClick={() => setActiveTab('matched')}
              >
                <IconCheck size={15} /> Clause SSD-01 (Verified)
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'amendment'}
                className={`tr-tab-btn ${activeTab === 'amendment' ? 'active' : ''}`}
                onClick={() => setActiveTab('amendment')}
              >
                <IconAlertTriangle size={15} /> Clause RAM-01 (Addendum #2)
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'signoff'}
                className={`tr-tab-btn ${activeTab === 'signoff' ? 'active' : ''}`}
                onClick={() => setActiveTab('signoff')}
              >
                <IconFileCertificate size={15} /> Submission Dossier
              </button>
            </div>

            {/* Tab Body */}
            <div className="tr-workbench-body">
              {activeTab === 'matched' && (
                <div className="tr-view-matched">
                  {/* Tender Requirement Side */}
                  <div className="tr-clause-box">
                    <div className="tr-box-header">
                      <span className="tr-box-tag tender">TENDER REQUIREMENT §4.2</span>
                      <span className="tr-box-source">Original_RFP.pdf · Page 14</span>
                    </div>
                    <blockquote className="tr-quote">
                      &ldquo;Primary storage must be at least 512 GB PCIe 4.0 NVMe M.2 Solid State Drive with hardware-level TCG Opal encryption support.&rdquo;
                    </blockquote>
                    <div className="tr-meta-row">
                      <span>Requirement ID: <strong>SSD-01</strong></span>
                      <span>Category: <strong>Storage Hardware</strong></span>
                      <span>Mandatory: <strong>Yes</strong></span>
                    </div>
                  </div>

                  {/* Supplier Proof Match */}
                  <div className="tr-clause-box evidence">
                    <div className="tr-box-header">
                      <span className="tr-box-tag supplier">SUPPLIER EVIDENCE MATCH</span>
                      <span className="tr-box-source">Atlas_A14_Datasheet.pdf · Page 3</span>
                    </div>
                    <blockquote className="tr-quote match">
                      &ldquo;Internal Drive: 512 GB M.2 2280 PCIe Gen 4x4 NVMe SSD, OPAL 2.0 self-encrypting drive compliant.&rdquo;
                    </blockquote>
                    <div className="tr-verification-badge verified">
                      <span className="tr-verified-icon"><IconCheck size={16} /></span>
                      <div>
                        <strong>Supported by Evidence · Model & Spec Confirmed</strong>
                        <small>Nemotron cross-check: 512 GB threshold met · Opal 2.0 supported</small>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'amendment' && (
                <div className="tr-view-amendment">
                  <div className="tr-amendment-alert">
                    <span className="tr-alert-icon"><IconAlertTriangle size={18} /></span>
                    <div>
                      <strong>Addendum #2 Modification Detected</strong>
                      <p>Issued 48 hours prior to tender submission. Minimum memory threshold revised.</p>
                    </div>
                  </div>

                  <div className="tr-comparison-grid">
                    <div className="tr-clause-box original">
                      <div className="tr-box-header">
                        <span className="tr-box-tag">ORIGINAL SPEC (§4.3)</span>
                        <span className="tr-box-source">Tender_v1.pdf</span>
                      </div>
                      <p className="tr-clause-text">&ldquo;RAM: 16 GB DDR5 unified memory.&rdquo;</p>
                      <span className="tr-status-tag passed">Was Verified (16 GB)</span>
                    </div>

                    <div className="tr-clause-box modified">
                      <div className="tr-box-header">
                        <span className="tr-box-tag alert">ADDENDUM #2 REVISION</span>
                        <span className="tr-box-source">Addendum_02.pdf · Clause 1.4</span>
                      </div>
                      <p className="tr-clause-text">&ldquo;RAM requirement is amended to: Minimum 32 GB DDR5.&rdquo;</p>
                      <span className="tr-status-tag failed">Discrepancy: Supplier PDF shows 16 GB</span>
                    </div>
                  </div>

                  <div className="tr-action-footer">
                    <span className="tr-action-hint">
                      <IconClock size={15} /> Corrective Action Assigned: Request 32 GB configuration bulletin from OEM.
                    </span>
                    <span className="tr-action-pill">Needs Human Sign-Off</span>
                  </div>
                </div>
              )}

              {activeTab === 'signoff' && (
                <div className="tr-view-signoff">
                  <div className="tr-dossier-summary">
                    <div className="tr-dossier-stat">
                      <span className="tr-stat-label">Readiness Index</span>
                      <strong className="tr-stat-value">95.8%</strong>
                      <span className="tr-stat-note">23 of 24 Clauses Fully Evidenced</span>
                    </div>
                    <div className="tr-dossier-stat">
                      <span className="tr-stat-label">Audit Integrity</span>
                      <strong className="tr-stat-value verified">SHA-256</strong>
                      <span className="tr-stat-note">Immutable Provenance Log</span>
                    </div>
                    <div className="tr-dossier-stat">
                      <span className="tr-stat-label">Reviewers</span>
                      <strong className="tr-stat-value">2 Officers</strong>
                      <span className="tr-stat-note">Legal & Technical Lead Sign-off</span>
                    </div>
                  </div>

                  <div className="tr-dossier-actions">
                    <div className="tr-dossier-text">
                      <strong>Export Source-Linked Tender Evidence Pack</strong>
                      <p>Generates an annotated PDF compilation linking every tender clause directly to supplier document pages with digital verification signatures.</p>
                    </div>
                    <a href="#workspace-start" className="tr-button tr-primary tr-compact-btn">
                      Generate Dossier <IconArrowRight size={14} />
                    </a>
                  </div>
                </div>
              )}
            </div>

            {/* Workbench Footer Bar */}
            <div className="tr-workbench-footer">
              <span className="tr-footer-item">
                <IconLock size={13} /> End-to-End Coordinate Traceability
              </span>
              <span className="tr-footer-sep">·</span>
              <span className="tr-footer-item">
                <IconFiles size={13} /> Original & Addendum Version Diffing
              </span>
              <span className="tr-footer-sep">·</span>
              <span className="tr-footer-item">
                <IconShieldCheck size={13} /> Human Governance Standard
              </span>
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
