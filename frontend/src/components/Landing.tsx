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
    label: 'Exact Page Links',
    desc: 'Every single rule links directly to the exact page and paragraph in your PDF.',
  },
  {
    value: 'Instant',
    label: 'Rule Change Alerts',
    desc: 'Get notified immediately if a buyer updates or changes any tender requirements.',
  },
  {
    value: 'Zero',
    label: 'No Guesswork',
    desc: 'The AI only uses real facts from your files. It never guesses or makes things up.',
  },
  {
    value: 'You Decide',
    label: 'You Stay in Control',
    desc: 'The AI helps spot issues, but your team makes the final call on every review.',
  },
];

const pipelineStages = [
  {
    id: 'ingest',
    stage: '01',
    name: '1. Read & Find Rules',
    icon: IconFileText,
    subtitle: 'Upload long tender PDFs. The system finds and lists every rule you must follow.',
    features: [
      'Finds all required technical specs and business terms automatically',
      'Shows the exact page number and paragraph for every requirement',
      'Keeps track of the original tender and all newer versions',
      'Sorts rules into simple groups like hardware, warranty, and pricing',
    ],
  },
  {
    id: 'verify',
    stage: '02',
    name: '2. Check Your Proof',
    icon: IconShieldCheck,
    subtitle: 'Upload product sheets and certificates to make sure your items qualify.',
    features: [
      'Compares model names, numbers, and dates against the tender rules',
      'Checks company names and confirms that certificates are not expired',
      'Warns you right away if a product spec falls short or conflicts',
      'Highlights the exact line in your proof document that backs up each claim',
    ],
  },
  {
    id: 'govern',
    stage: '03',
    name: '3. Track Changes & Export',
    icon: IconFileCertificate,
    subtitle: 'Catch late tender updates, record approvals, and download your final bid pack.',
    features: [
      'Flags any rule that changed after an update or addendum was issued',
      'Helps your team track who reviewed what and when',
      'Assigns simple to-do tasks to fix missing or incorrect documents',
      'Exports a clean, organized bid pack ready to send to the buyer',
    ],
  },
];

const audiences = [
  {
    Icon: IconBuilding,
    title: 'IT & Hardware Sellers',
    desc: 'Check product specs, model numbers, and warranty terms before you spend time preparing a bid.',
  },
  {
    Icon: IconSchool,
    title: 'Schools & Universities',
    desc: 'Easily follow public buying rules, scoring guidelines, and strict delivery deadlines.',
  },
  {
    Icon: IconBuildingBank,
    title: 'Buying Teams & Offices',
    desc: 'Keep a clear, documented record of why a bid was approved, with real proof for every decision.',
  },
];

const capabilities = [
  {
    Icon: IconFiles,
    title: 'Full Document Search',
    desc: 'Upload long tender files. Every rule is organized with page numbers and sections.',
  },
  {
    Icon: IconScale,
    title: 'Automatic Number Checks',
    desc: 'Checks storage size, memory, warranty years, and response times to make sure you qualify.',
  },
  {
    Icon: IconRefresh,
    title: 'Instant Update Warnings',
    desc: 'See what got added, changed, or removed without re-reading the whole document.',
  },
  {
    Icon: IconLock,
    title: 'Ready-to-Send Bid Pack',
    desc: 'Download an organized report showing proof for every requirement, ready to submit.',
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
            <small>Tender & Bid Assistant</small>
          </span>
        </a>
        <nav aria-label="Main navigation">
          <a href="#how-it-works">How It Works</a>
          <a href="#features">Features</a>
          <a href="#who-uses-it">Who Uses It</a>
          <a href="#workspace-start">Workspaces</a>
        </nav>
        <a className="tr-button tr-primary tr-nav-cta" href="#workspace-start">
          Open Workspaces <IconArrowRight size={15} />
        </a>
      </header>

      {/* Hero Section - Simple, Clear, Direct Vocab */}
      <section className="tr-hero" aria-labelledby="tr-headline">
        <div className="tr-hero-inner">
          <div className="tr-eyebrow">
            <span className="tr-eyebrow-dot" aria-hidden="true" />
            <span>SMART TENDER & BID ASSISTANT</span>
          </div>

          <h1 id="tr-headline">
            Turn complex tenders into <span className="tr-brand-accent">clear, ready-to-submit bids</span>.
          </h1>

          <p className="tr-hero-lead">
            TenderReady helps suppliers and buyers pull rules out of long tender PDFs, check product specs
            against proof documents, and catch every change before submitting.
          </p>

          <div className="tr-actions">
            <a className="tr-button tr-primary" href="#workspace-start">
              Start a Workspace <IconArrowRight size={17} />
            </a>
            <a className="tr-button tr-secondary" href="#how-it-works">
              <IconListCheck size={17} /> See How It Works
            </a>
          </div>
        </div>

        {/* 4 Simple Metric Cards */}
        <div className="tr-hero-metrics" role="region" aria-label="Key Benefits">
          {metrics.map(({ value, label, desc }) => (
            <div className="tr-metric-card" key={label}>
              <span className="tr-metric-value">{value}</span>
              <strong className="tr-metric-label">{label}</strong>
              <p className="tr-metric-desc">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* 3-Step Process (Simple Language) */}
      <section className="tr-pipeline-section" id="how-it-works" aria-labelledby="how-it-works-title">
        <div className="tr-section-heading">
          <span className="tr-eyebrow-mini">HOW IT WORKS</span>
          <h2 id="how-it-works-title">A Simple 3-Step Process for Every Tender</h2>
          <p>
            Review tender files step by step so your team never misses a required detail.
          </p>
        </div>

        <div className="tr-pipeline-container">
          {/* Stage Navigation Tabs */}
          <div className="tr-stage-nav" role="tablist" aria-label="Process steps">
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
                    <small className="tr-stage-sub">Step {stage.stage}</small>
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
                <span>STEP {pipelineStages[selectedStage].stage}</span>
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
                <IconDatabase size={14} /> Exact PDF Links
              </div>
              <div className="tr-detail-pill">
                <IconLock size={14} /> Full Change History
              </div>
              <div className="tr-detail-pill">
                <IconShieldCheck size={14} /> Checked by Real AI
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Key Features Grid */}
      <section className="tr-capabilities-section" id="features" aria-labelledby="features-title">
        <div className="tr-section-heading">
          <span className="tr-eyebrow-mini">KEY FEATURES</span>
          <h2 id="features-title">Everything You Need to Submit with Confidence</h2>
          <p>Replace slow manual spreadsheets with fast, automatic checks you can rely on.</p>
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
      <section className="tr-proof" id="who-uses-it" aria-label="Who uses TenderReady">
        <div className="tr-section-heading">
          <span className="tr-eyebrow-mini">WHO USES TENDERREADY</span>
          <h2>Built for Teams That Cannot Afford to Make Mistakes</h2>
          <p>
            When bidding on big contracts, missing even one small detail can get your submission rejected.
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
              <strong>Backed by Real Proof</strong>
              <span>Every finding points straight to the exact page in your uploaded files.</span>
            </div>
          </div>
          <div className="tr-pillar">
            <span className="tr-pillar-check"><IconCheck size={16} /></span>
            <div>
              <strong>Catches Every Change</strong>
              <span>Know right away when a buyer changes rules or issues new updates.</span>
            </div>
          </div>
          <div className="tr-pillar">
            <span className="tr-pillar-check"><IconCheck size={16} /></span>
            <div>
              <strong>You Have the Final Say</strong>
              <span>The tool helps you find issues, but your team decides what to approve.</span>
            </div>
          </div>
        </div>

        <div className="tr-disclaimer-box">
          <IconShieldCheck size={20} className="tr-disclaimer-icon" />
          <p>
            <strong>Helpful Note:</strong> TenderReady is a smart assistant that checks documents against tender rules. It helps you prepare your bid, but it does not provide legal advice or guarantee that you will win the contract.
          </p>
        </div>
      </section>
    </div>
  );
}
