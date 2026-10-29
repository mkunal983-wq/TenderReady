import { useState } from 'react';
import {
  IconArrowRight,
  IconShieldCheck,
  IconRefresh,
  IconFileText,
  IconBuilding,
  IconSchool,
  IconBuildingBank,
  IconCheck,
  IconAlertTriangle,
  IconFileCertificate,
  IconLock,
  IconSparkles,
  IconChevronDown,
  IconChevronUp,
  IconClock,
  IconTrendingUp,
} from '@tabler/icons-react';
import './landing.css';

type TestCase = 'ssd' | 'ram' | 'warranty';

export function Landing() {
  // Live Verifier Playground State
  const [activeTest, setActiveTest] = useState<TestCase>('ssd');
  const [ramAddendum, setRamAddendum] = useState(true);

  // Live Calculator State
  const [tenderPages, setTenderPages] = useState(120);
  const [docCount, setDocCount] = useState(6);

  // Live FAQ Accordion State
  const [openFaq, setOpenFaq] = useState<number | null>(0);

  // Calculator Math (Simple, realistic estimates)
  const manualHours = Math.round((tenderPages * 0.12) + (docCount * 1.5));
  const tenderReadyMinutes = Math.max(3, Math.round((tenderPages * 0.08) + (docCount * 0.5)));
  const estimatedSavings = manualHours * 65; // $65/hr consultant/reviewer rate

  const faqs = [
    {
      q: 'Do I need any technical or AI skills to use this?',
      a: 'Not at all. You simply upload your tender PDF and product proof documents. TenderReady reads the files, highlights every rule, and shows you if your specs match in simple plain English.',
    },
    {
      q: 'What happens when a buyer releases a last-minute amendment?',
      a: 'Just upload the new amendment PDF. TenderReady automatically compares it with the original rules and flags any requirement that was changed, added, or deleted, so you never submit outdated specs.',
    },
    {
      q: 'Can the AI guess or make up information?',
      a: 'No. TenderReady uses deterministic verification. Every single check must cite the exact page number, clause, and paragraph in your uploaded files. If proof is missing, it plainly warns you instead of guessing.',
    },
    {
      q: 'Can I test out TenderReady right now without an API key?',
      a: 'Yes! Click "Try a sample tender" below. It sets up an instant practice workspace preloaded with real sample PDFs, an amendment test case, and a simulated audit review.',
    },
  ];

  return (
    <div className="tr-landing">
      {/* Background Tech Texture & Aurora Mesh */}
      <div className="tr-background-canvas" aria-hidden="true">
        <div className="tr-orb tr-orb-1" />
        <div className="tr-orb tr-orb-2" />
        <div className="tr-orb tr-orb-3" />
        <div className="tr-bg-grid-major" />
        <div className="tr-bg-grid" />
        <div className="tr-bg-dots" />
      </div>

      {/* Top Navigation Bar */}
      <header className="tr-nav">
        <a className="tr-logo" href="/" aria-label="TenderReady home">
          <span className="tr-mark">T</span>
          <span>
            <strong>TenderReady</strong>
            <small>Tender & Bid Assistant</small>
          </span>
        </a>
        <nav aria-label="Main navigation">
          <a href="#live-demo">Live Demo</a>
          <a href="#how-it-works">How It Works</a>
          <a href="#calculator">Time Calculator</a>
          <a href="#who-uses-it">Who Uses It</a>
          <a href="#faqs">FAQ</a>
        </nav>
        <a className="tr-button tr-primary tr-nav-cta" href="#workspace-start">
          Open Workspaces <IconArrowRight size={15} />
        </a>
      </header>

      {/* Hero Section */}
      <section className="tr-hero" aria-labelledby="tr-headline">
        <div className="tr-hero-inner">
          <div className="tr-eyebrow">
            <span className="tr-eyebrow-dot" aria-hidden="true" />
            <span>AI-POWERED TENDER & BID VERIFICATION</span>
          </div>

          <h1 id="tr-headline">
            Turn long, messy tenders into <span className="tr-brand-accent">clear bids that win</span>.
          </h1>

          <p className="tr-hero-lead">
            TenderReady pulls rules out of complex tender PDFs, checks your product proof documents,
            and catches every rule change so you can submit with total confidence.
          </p>

          <div className="tr-actions">
            <a className="tr-button tr-primary" href="#workspace-start">
              Start a Workspace <IconArrowRight size={17} />
            </a>
            <a className="tr-button tr-secondary" href="#live-demo">
              <IconSparkles size={17} /> Try the Live Checker
            </a>
          </div>

          {/* Quick Stats Pill Strip */}
          <div className="tr-quick-stats">
            <span className="tr-qstat"><IconCheck size={15} /> Exact Page Citations</span>
            <span className="tr-qstat"><IconRefresh size={15} /> Instant Change Alerts</span>
            <span className="tr-qstat"><IconShieldCheck size={15} /> 100% Fact-Checked</span>
            <span className="tr-qstat"><IconLock size={15} /> Complete Team Control</span>
          </div>
        </div>

        {/* ============================================================
            LIVE FEATURE 1: Interactive Clause & Evidence Playground
            ============================================================ */}
        <div className="tr-demo-card" id="live-demo">
          <div className="tr-demo-header">
            <div className="tr-demo-title-group">
              <span className="tr-live-pill">
                <span className="tr-pulse-ring" /> LIVE DEMO
              </span>
              <strong>Interactive Tender Checker</strong>
              <small>Click any example to see how the system cross-checks rules against proof</small>
            </div>

            {/* Test Case Picker */}
            <div className="tr-demo-picker" role="tablist" aria-label="Sample test cases">
              <button
                type="button"
                className={`tr-picker-btn ${activeTest === 'ssd' ? 'active' : ''}`}
                onClick={() => setActiveTest('ssd')}
              >
                <IconCheck size={15} /> Test 1: Storage Match
              </button>
              <button
                type="button"
                className={`tr-picker-btn ${activeTest === 'ram' ? 'active' : ''}`}
                onClick={() => setActiveTest('ram')}
              >
                <IconAlertTriangle size={15} /> Test 2: RAM Update Conflict
              </button>
              <button
                type="button"
                className={`tr-picker-btn ${activeTest === 'warranty' ? 'active' : ''}`}
                onClick={() => setActiveTest('warranty')}
              >
                <IconShieldCheck size={15} /> Test 3: Warranty Verification
              </button>
            </div>
          </div>

          {/* Live Document Cross-Check Display */}
          <div className="tr-demo-body">
            {/* Case 1: Storage SSD (Pass) */}
            {activeTest === 'ssd' && (
              <div className="tr-demo-view">
                <div className="tr-docs-compare">
                  <div className="tr-doc-col tender-col">
                    <div className="tr-col-tag">
                      <span className="tr-tag-label">TENDER REQUIREMENT</span>
                      <span className="tr-tag-source">University_RFP.pdf · Page 14</span>
                    </div>
                    <blockquote className="tr-doc-quote">
                      &ldquo;Clause 4.2: Storage must be a minimum of 512 GB PCIe 4.0 NVMe SSD with hardware encryption support.&rdquo;
                    </blockquote>
                    <div className="tr-col-meta">
                      <span>Requirement: <strong>SSD-01</strong></span>
                      <span>Obligation: <strong>Mandatory</strong></span>
                    </div>
                  </div>

                  <div className="tr-doc-col proof-col">
                    <div className="tr-col-tag">
                      <span className="tr-tag-label">YOUR PRODUCT PROOF</span>
                      <span className="tr-tag-source">Atlas_A14_Datasheet.pdf · Page 3</span>
                    </div>
                    <blockquote className="tr-doc-quote">
                      &ldquo;Internal Drive: 512 GB M.2 2280 PCIe Gen 4x4 NVMe SSD, OPAL 2.0 self-encrypting drive compliant.&rdquo;
                    </blockquote>
                    <div className="tr-col-meta">
                      <span>Model: <strong>Atlas A14</strong></span>
                      <span>Capacity: <strong>512 GB (Threshold Met)</strong></span>
                    </div>
                  </div>
                </div>

                {/* AI Result Box */}
                <div className="tr-ai-result-box pass">
                  <div className="tr-result-header">
                    <span className="tr-result-badge pass">✓ 100% SPEC MATCH CONFIRMED</span>
                    <span className="tr-result-confidence">Nemotron Verification: 99.8% Confidence</span>
                  </div>
                  <p className="tr-result-text">
                    The supplier datasheet directly satisfies Clause 4.2. Model <strong>Atlas A14</strong> provides 512 GB PCIe 4.0 storage with Opal 2.0 encryption. Page citations are saved to your audit trail.
                  </p>
                </div>
              </div>
            )}

            {/* Case 2: RAM Amendment Conflict (Warning with Interactive Toggle) */}
            {activeTest === 'ram' && (
              <div className="tr-demo-view">
                <div className="tr-amendment-banner">
                  <div className="tr-banner-left">
                    <IconAlertTriangle size={19} className="tr-warn-icon" />
                    <div>
                      <strong>Addendum #2 Rule Change Simulation</strong>
                      <small>The buyer changed the memory requirement 48 hours before the deadline.</small>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="tr-toggle-btn"
                    onClick={() => setRamAddendum(v => !v)}
                  >
                    <IconRefresh size={14} />
                    {ramAddendum ? 'Switch to Original Tender (16 GB)' : 'Apply Addendum #2 (32 GB)'}
                  </button>
                </div>

                <div className="tr-docs-compare">
                  <div className={`tr-doc-col tender-col ${ramAddendum ? 'modified' : ''}`}>
                    <div className="tr-col-tag">
                      <span className="tr-tag-label">
                        {ramAddendum ? 'AMENDED TENDER RULE' : 'ORIGINAL TENDER RULE'}
                      </span>
                      <span className="tr-tag-source">
                        {ramAddendum ? 'Addendum_02.pdf · Clause 1.4' : 'Tender_v1.pdf · Page 15'}
                      </span>
                    </div>
                    <blockquote className="tr-doc-quote">
                      {ramAddendum
                        ? '“Clause 4.3 (Amended): Minimum memory requirement is increased to 32 GB DDR5 unified memory.”'
                        : '“Clause 4.3: Memory must be at least 16 GB DDR5 unified memory.”'}
                    </blockquote>
                    <div className="tr-col-meta">
                      <span>Requirement: <strong>RAM-01</strong></span>
                      <span>Target: <strong>{ramAddendum ? '32 GB' : '16 GB'}</strong></span>
                    </div>
                  </div>

                  <div className="tr-doc-col proof-col">
                    <div className="tr-col-tag">
                      <span className="tr-tag-label">YOUR SUBMITTED SPEC SHEET</span>
                      <span className="tr-tag-source">Atlas_A14_Datasheet.pdf · Page 3</span>
                    </div>
                    <blockquote className="tr-doc-quote">
                      &ldquo;Memory: 16 GB soldered LPDDR5 6400MHz high-efficiency dual-channel RAM.&rdquo;
                    </blockquote>
                    <div className="tr-col-meta">
                      <span>Offered Spec: <strong>16 GB RAM</strong></span>
                      <span>Status: <strong>Fixed Soldered Module</strong></span>
                    </div>
                  </div>
                </div>

                {/* Live Dynamic Result */}
                {ramAddendum ? (
                  <div className="tr-ai-result-box warn">
                    <div className="tr-result-header">
                      <span className="tr-result-badge warn">⚠️ DISQUALIFICATION RISK DETECTED</span>
                      <span className="tr-result-confidence">Action Required Before Submission</span>
                    </div>
                    <p className="tr-result-text">
                      <strong>Mismatch Found:</strong> Addendum #2 raised the rule to <strong>32 GB</strong>, but your spec sheet only shows <strong>16 GB</strong>.
                      TenderReady created a high-priority task: <em>Contact OEM representative for 32 GB configuration document.</em>
                    </p>
                  </div>
                ) : (
                  <div className="tr-ai-result-box pass">
                    <div className="tr-result-header">
                      <span className="tr-result-badge pass">✓ ORIGINAL SPECIFICATION PASSED</span>
                      <span className="tr-result-confidence">16 GB Matches Original Rule</span>
                    </div>
                    <p className="tr-result-text">
                      Under the original RFP, 16 GB was compliant. Toggle the button above to see what happens when the buyer issues Addendum #2!
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Case 3: Warranty Verification (Pass) */}
            {activeTest === 'warranty' && (
              <div className="tr-demo-view">
                <div className="tr-docs-compare">
                  <div className="tr-doc-col tender-col">
                    <div className="tr-col-tag">
                      <span className="tr-tag-label">TENDER SLA RULE §6.1</span>
                      <span className="tr-tag-source">University_RFP.pdf · Page 22</span>
                    </div>
                    <blockquote className="tr-doc-quote">
                      &ldquo;Clause 6.1: Supplier must provide a minimum 3-year on-site next-business-day warranty with accidental damage protection.&rdquo;
                    </blockquote>
                    <div className="tr-col-meta">
                      <span>Requirement: <strong>WAR-01</strong></span>
                      <span>Coverage: <strong>3 Years On-Site NBD</strong></span>
                    </div>
                  </div>

                  <div className="tr-doc-col proof-col">
                    <div className="tr-col-tag">
                      <span className="tr-tag-label">MANUFACTURER LETTER</span>
                      <span className="tr-tag-source">OEM_Warranty_Letter.pdf · Page 1</span>
                    </div>
                    <blockquote className="tr-doc-quote">
                      &ldquo;We confirm 36-month Premier Support with on-site technician dispatch by next business day and comprehensive accidental damage coverage.&rdquo;
                    </blockquote>
                    <div className="tr-col-meta">
                      <span>Duration: <strong>36 Months (3 Years)</strong></span>
                      <span>Service Level: <strong>Next Business Day On-Site</strong></span>
                    </div>
                  </div>
                </div>

                <div className="tr-ai-result-box pass">
                  <div className="tr-result-header">
                    <span className="tr-result-badge pass">✓ WARRANTY & SLA CONFIRMED</span>
                    <span className="tr-result-confidence">Nemotron Verification: 100% Match</span>
                  </div>
                  <p className="tr-result-text">
                    All three conditions satisfied: 3-year term, on-site next-business-day response, and accidental damage coverage. Letter is valid and signed.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ============================================================
          LIVE FEATURE 2: Interactive Time & Savings Calculator
          ============================================================ */}
      <section className="tr-calculator-section" id="calculator" aria-labelledby="calc-title">
        <div className="tr-section-heading">
          <span className="tr-eyebrow-mini">INTERACTIVE ESTIMATOR</span>
          <h2 id="calc-title">See How Much Time TenderReady Saves Your Team</h2>
          <p>Drag the sliders to match your typical tender and see the difference immediately.</p>
        </div>

        <div className="tr-calculator-card">
          <div className="tr-calc-inputs">
            {/* Slider 1 */}
            <div className="tr-slider-group">
              <div className="tr-slider-header">
                <label htmlFor="pages-slider">Tender Document Length</label>
                <span className="tr-slider-val">{tenderPages} pages</span>
              </div>
              <input
                id="pages-slider"
                type="range"
                min="20"
                max="400"
                step="10"
                value={tenderPages}
                onChange={e => setTenderPages(Number(e.target.value))}
                className="tr-slider"
              />
              <div className="tr-slider-scale">
                <span>20 pgs (Short RFP)</span>
                <span>200 pgs</span>
                <span>400 pgs (Complex Fleet)</span>
              </div>
            </div>

            {/* Slider 2 */}
            <div className="tr-slider-group">
              <div className="tr-slider-header">
                <label htmlFor="docs-slider">Product Proof Documents to Check</label>
                <span className="tr-slider-val">{docCount} documents</span>
              </div>
              <input
                id="docs-slider"
                type="range"
                min="1"
                max="20"
                step="1"
                value={docCount}
                onChange={e => setDocCount(Number(e.target.value))}
                className="tr-slider"
              />
              <div className="tr-slider-scale">
                <span>1 spec sheet</span>
                <span>10 files</span>
                <span>20 certificates</span>
              </div>
            </div>
          </div>

          {/* Calculator Results Grid */}
          <div className="tr-calc-outputs">
            <div className="tr-output-card highlight">
              <span className="tr-output-label"><IconClock size={16} /> With TenderReady</span>
              <strong className="tr-output-number green">{tenderReadyMinutes} mins</strong>
              <small>Automated clause extraction & cross-check</small>
            </div>

            <div className="tr-output-card">
              <span className="tr-output-label">Manual Spreadsheet Review</span>
              <strong className="tr-output-number">{manualHours} hours</strong>
              <small>Reading PDFs, copying lines, checking numbers</small>
            </div>

            <div className="tr-output-card">
              <span className="tr-output-label"><IconTrendingUp size={16} /> Time Saved</span>
              <strong className="tr-output-number green">{(manualHours - (tenderReadyMinutes / 60)).toFixed(1)} hrs</strong>
              <small>Saved per tender submission cycle</small>
            </div>

            <div className="tr-output-card">
              <span className="tr-output-label">Estimated Cost Saved</span>
              <strong className="tr-output-number">${estimatedSavings.toLocaleString()}</strong>
              <small>Based on standard $65/hr proposal review costs</small>
            </div>
          </div>
        </div>
      </section>

      {/* ============================================================
          SECTION 3: A Simple 3-Step Process
          ============================================================ */}
      <section className="tr-pipeline-section" id="how-it-works" aria-labelledby="how-title">
        <div className="tr-section-heading">
          <span className="tr-eyebrow-mini">THE PROCESS</span>
          <h2 id="how-title">From Messy PDF to Clean Submission in 3 Steps</h2>
          <p>Everything is broken down so your team never misses a required specification.</p>
        </div>

        <div className="tr-steps-grid">
          <div className="tr-step-box">
            <div className="tr-step-num-badge">01</div>
            <div className="tr-step-icon"><IconFileText size={24} /></div>
            <h3>1. Read & Find Rules</h3>
            <p>
              Upload the tender PDF. The system automatically finds every mandatory spec, clause, and commercial rule—recording the exact page number for each one.
            </p>
            <ul className="tr-step-points">
              <li><IconCheck size={14} /> Finds mandatory specs & terms</li>
              <li><IconCheck size={14} /> Direct PDF page & paragraph links</li>
              <li><IconCheck size={14} /> Organizes hardware, warranty & pricing</li>
            </ul>
          </div>

          <div className="tr-step-box active-box">
            <div className="tr-step-num-badge">02</div>
            <div className="tr-step-icon"><IconShieldCheck size={24} /></div>
            <h3>2. Check Your Proof</h3>
            <p>
              Upload product sheets, certificates, and OEM letters. The system compares numbers, model names, and dates—instantly highlighting any mismatches.
            </p>
            <ul className="tr-step-points">
              <li><IconCheck size={14} /> Checks model numbers and specs</li>
              <li><IconCheck size={14} /> Confirms certificates aren't expired</li>
              <li><IconCheck size={14} /> Flags spec shortfalls before submission</li>
            </ul>
          </div>

          <div className="tr-step-box">
            <div className="tr-step-num-badge">03</div>
            <div className="tr-step-icon"><IconFileCertificate size={24} /></div>
            <h3>3. Track Changes & Export</h3>
            <p>
              When the buyer releases late amendments, TenderReady flags what changed. Your team reviews issues, confirms sign-offs, and downloads the complete bid pack.
            </p>
            <ul className="tr-step-points">
              <li><IconCheck size={14} /> Instant addendum change alerts</li>
              <li><IconCheck size={14} /> Assigns corrective to-do tasks</li>
              <li><IconCheck size={14} /> Exports ready-to-submit proof dossier</li>
            </ul>
          </div>
        </div>
      </section>

      {/* ============================================================
          SECTION 4: Who Uses TenderReady
          ============================================================ */}
      <section className="tr-proof" id="who-uses-it" aria-label="Who uses TenderReady">
        <div className="tr-section-heading">
          <span className="tr-eyebrow-mini">WHO IT IS FOR</span>
          <h2>Built for Teams That Cannot Afford to Make Mistakes</h2>
          <p>
            When bidding on big contracts, missing even one small requirement can get your bid thrown out.
          </p>
        </div>

        <div className="tr-audiences-grid">
          <div className="tr-audience-card">
            <div className="tr-audience-icon"><IconBuilding size={24} /></div>
            <h3>IT & Hardware Sellers</h3>
            <p>
              Quickly check product specs, part numbers, and warranty terms before spending time and money bidding.
            </p>
          </div>

          <div className="tr-audience-card">
            <div className="tr-audience-icon"><IconSchool size={24} /></div>
            <h3>Schools & Universities</h3>
            <p>
              Meet strict public purchasing rules, scoring requirements, and delivery commitments with ease.
            </p>
          </div>

          <div className="tr-audience-card">
            <div className="tr-audience-icon"><IconBuildingBank size={24} /></div>
            <h3>Buying Teams & Evaluators</h3>
            <p>
              Keep an organized, documented record of why each bid was approved, backed by real proof documents.
            </p>
          </div>
        </div>
      </section>

      {/* ============================================================
          LIVE FEATURE 3: Interactive FAQ Accordion
          ============================================================ */}
      <section className="tr-faq-section" id="faqs" aria-labelledby="faq-title">
        <div className="tr-section-heading">
          <span className="tr-eyebrow-mini">FREQUENTLY ASKED QUESTIONS</span>
          <h2 id="faq-title">Got Questions? We Have Answers.</h2>
          <p>Everything you need to know about getting started with TenderReady.</p>
        </div>

        <div className="tr-faq-accordion">
          {faqs.map((faq, idx) => {
            const isOpen = openFaq === idx;
            return (
              <div key={idx} className={`tr-faq-item ${isOpen ? 'open' : ''}`}>
                <button
                  type="button"
                  className="tr-faq-question"
                  onClick={() => setOpenFaq(isOpen ? null : idx)}
                  aria-expanded={isOpen}
                >
                  <span>{faq.q}</span>
                  {isOpen ? <IconChevronUp size={18} /> : <IconChevronDown size={18} />}
                </button>
                {isOpen && (
                  <div className="tr-faq-answer">
                    <p>{faq.a}</p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* High-Impact Bottom Callout */}
      <section className="tr-cta-banner">
        <div className="tr-cta-inner">
          <span className="tr-cta-eyebrow">READY TO PREPARE YOUR NEXT BID?</span>
          <h2>Start reviewing your tender documents in minutes</h2>
          <p>Create a workspace now or try out our ready-made sample tender with real documents.</p>
          <div className="tr-cta-buttons">
            <a className="tr-button tr-primary tr-large" href="#workspace-start">
              Open Workspaces <IconArrowRight size={17} />
            </a>
          </div>
        </div>
      </section>
    </div>
  );
}
