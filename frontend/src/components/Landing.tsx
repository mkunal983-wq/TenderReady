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
      {/* Living Ambient Light Flow (Calm, Fluid, Non-Distracting) */}
      <div className="tr-background-canvas" aria-hidden="true">
        <div className="tr-ambient-glow" />
        <div className="tr-orb tr-orb-1" />
        <div className="tr-orb tr-orb-2" />
        <div className="tr-orb tr-orb-3" />
        <div className="tr-orb tr-orb-4" />
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
              <div className="tr-demo-badge-row">
                <span className="tr-live-pill">
                  <span className="tr-pulse-ring" /> LIVE EXAMPLE
                </span>
                <span className="tr-demo-hint">Instant check against your proof documents</span>
              </div>
              <h2 className="tr-demo-title">Interactive Tender Checker</h2>
              <p className="tr-demo-subtitle">Select an example below to see how TenderReady checks if your products meet the buyer's rules:</p>
            </div>

            {/* Scenario Picker Tabs */}
            <div className="tr-demo-picker" role="tablist" aria-label="Sample test cases">
              <button
                type="button"
                className={`tr-picker-btn ${activeTest === 'ssd' ? 'active' : ''}`}
                onClick={() => setActiveTest('ssd')}
              >
                <IconCheck size={16} />
                <span>1. Storage Check</span>
                <span className="tr-tab-status pass">Matches</span>
              </button>
              <button
                type="button"
                className={`tr-picker-btn ${activeTest === 'ram' ? 'active' : ''}`}
                onClick={() => setActiveTest('ram')}
              >
                <IconAlertTriangle size={16} />
                <span>2. Last-Minute Change</span>
                <span className="tr-tab-status warn">Warning</span>
              </button>
              <button
                type="button"
                className={`tr-picker-btn ${activeTest === 'warranty' ? 'active' : ''}`}
                onClick={() => setActiveTest('warranty')}
              >
                <IconShieldCheck size={16} />
                <span>3. Warranty & Repairs</span>
                <span className="tr-tab-status pass">Matches</span>
              </button>
            </div>
          </div>

          <div className="tr-demo-body">
            {/* If RAM Amendment test is active, show clean version switcher */}
            {activeTest === 'ram' && (
              <div className="tr-version-bar">
                <div className="tr-version-info">
                  <IconAlertTriangle size={18} className="tr-warn-icon" />
                  <div>
                    <strong>Simulate a Last-Minute Buyer Change</strong>
                    <span>What happens when the buyer raises the required RAM 48 hours before the deadline?</span>
                  </div>
                </div>
                <div className="tr-version-toggle-group">
                  <span className="tr-version-label">Rule Version:</span>
                  <div className="tr-segmented-control">
                    <button
                      type="button"
                      className={`tr-segment-btn ${!ramAddendum ? 'active' : ''}`}
                      onClick={() => setRamAddendum(false)}
                    >
                      Before Update (16 GB)
                    </button>
                    <button
                      type="button"
                      className={`tr-segment-btn ${ramAddendum ? 'active' : ''}`}
                      onClick={() => setRamAddendum(true)}
                    >
                      After Update (32 GB) ⚠️
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Test 1: Storage */}
            {activeTest === 'ssd' && (
              <div className="tr-comparison-stage">
                <div className="tr-cards-pair">
                  {/* Left: Tender Requirement */}
                  <div className="tr-spec-card tender">
                    <div className="tr-card-topbar">
                      <span className="tr-spec-eyebrow">WHAT THE BUYER ASKS FOR</span>
                      <div className="tr-source-chip">
                        <IconFileText size={13} />
                        <span>University_RFP.pdf · Page 14</span>
                      </div>
                    </div>

                    <div className="tr-spec-value">
                      At least 512 GB Storage (SSD)
                    </div>

                    <p className="tr-quote-snippet">
                      &ldquo;Clause 4.2: Storage must be a minimum of 512 GB high-speed SSD with data encryption.&rdquo;
                    </p>
                  </div>

                  {/* Center Match Badge */}
                  <div className="tr-center-bridge pass">
                    <div className="tr-bridge-icon">✓</div>
                    <span className="tr-bridge-label">MATCH</span>
                  </div>

                  {/* Right: Supplier Proof */}
                  <div className="tr-spec-card proof">
                    <div className="tr-card-topbar">
                      <span className="tr-spec-eyebrow">WHAT YOUR DOCUMENT PROVES</span>
                      <div className="tr-source-chip">
                        <IconFileCertificate size={13} />
                        <span>Atlas_A14_Datasheet.pdf · Page 3</span>
                      </div>
                    </div>

                    <div className="tr-spec-value">
                      512 GB High-Speed NVMe SSD
                    </div>

                    <p className="tr-quote-snippet">
                      &ldquo;Internal Drive: 512 GB PCIe NVMe SSD with built-in hardware security.&rdquo;
                    </p>
                  </div>
                </div>

                {/* Bottom Verdict */}
                <div className="tr-verdict pass">
                  <div className="tr-verdict-icon"><IconShieldCheck size={24} /></div>
                  <div className="tr-verdict-body">
                    <div className="tr-verdict-title">
                      <strong>✓ Perfect Match — Ready to Bid</strong>
                      <span className="tr-verdict-tag">Page Citations Saved</span>
                    </div>
                    <p className="tr-verdict-desc">
                      Your Atlas A14 datasheet meets the 512 GB requirement and encryption rule. The exact page citation is saved to your compliance matrix so reviewers can verify it in seconds.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Test 2: RAM Amendment */}
            {activeTest === 'ram' && (
              <div className="tr-comparison-stage">
                <div className="tr-cards-pair">
                  {/* Left: Tender Requirement */}
                  <div className={`tr-spec-card tender ${ramAddendum ? 'modified' : ''}`}>
                    <div className="tr-card-topbar">
                      <span className="tr-spec-eyebrow">
                        {ramAddendum ? 'BUYER UPDATED THIS RULE' : 'ORIGINAL BUYER RULE'}
                      </span>
                      <div className="tr-source-chip">
                        <IconFileText size={13} />
                        <span>{ramAddendum ? 'Addendum_02.pdf · Page 1' : 'Tender_v1.pdf · Page 15'}</span>
                      </div>
                    </div>

                    <div className={`tr-spec-value ${ramAddendum ? 'conflict-val' : ''}`}>
                      {ramAddendum ? 'Raised to 32 GB RAM' : 'At least 16 GB RAM'}
                    </div>

                    <p className="tr-quote-snippet">
                      {ramAddendum
                        ? '“Clause 4.3 (Update): Minimum memory requirement is increased to 32 GB RAM.”'
                        : '“Clause 4.3: Memory must be at least 16 GB RAM.”'}
                    </p>
                  </div>

                  {/* Center Comparison Bridge */}
                  <div className={`tr-center-bridge ${ramAddendum ? 'fail' : 'pass'}`}>
                    <div className="tr-bridge-icon">{ramAddendum ? '≠' : '✓'}</div>
                    <span className="tr-bridge-label">{ramAddendum ? 'MISMATCH' : 'MATCH'}</span>
                  </div>

                  {/* Right: Supplier Proof */}
                  <div className="tr-spec-card proof">
                    <div className="tr-card-topbar">
                      <span className="tr-spec-eyebrow">WHAT YOUR DOCUMENT PROVES</span>
                      <div className="tr-source-chip">
                        <IconFileCertificate size={13} />
                        <span>Atlas_A14_Datasheet.pdf · Page 3</span>
                      </div>
                    </div>

                    <div className="tr-spec-value">
                      16 GB RAM (Offered Laptop)
                    </div>

                    <p className="tr-quote-snippet">
                      &ldquo;Memory: 16 GB soldered high-efficiency dual-channel RAM.&rdquo;
                    </p>
                  </div>
                </div>

                {/* Bottom Verdict */}
                {ramAddendum ? (
                  <div className="tr-verdict warn">
                    <div className="tr-verdict-icon"><IconAlertTriangle size={24} /></div>
                    <div className="tr-verdict-body">
                      <div className="tr-verdict-title">
                        <strong>⚠️ Warning: Your Offered Spec Falls Short</strong>
                        <span className="tr-verdict-tag red">Action Needed Before Submitting</span>
                      </div>
                      <p className="tr-verdict-desc">
                        The buyer raised the rule from <strong>16 GB to 32 GB</strong>, but your current datasheet only proves <strong>16 GB</strong>. TenderReady flagged this mismatch so you can swap in a 32 GB model datasheet before submitting your bid.
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="tr-verdict pass">
                    <div className="tr-verdict-icon"><IconShieldCheck size={24} /></div>
                    <div className="tr-verdict-body">
                      <div className="tr-verdict-title">
                        <strong>✓ Original Rule Matches</strong>
                        <span className="tr-verdict-tag">16 GB Meets Original Rule</span>
                      </div>
                      <p className="tr-verdict-desc">
                        Under the original tender, 16 GB was compliant. Click <strong>"After Update (32 GB)"</strong> above to see how TenderReady catches the issue when buyers change rules late.
                      </p>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Test 3: Warranty */}
            {activeTest === 'warranty' && (
              <div className="tr-comparison-stage">
                <div className="tr-cards-pair">
                  {/* Left: Tender Requirement */}
                  <div className="tr-spec-card tender">
                    <div className="tr-card-topbar">
                      <span className="tr-spec-eyebrow">WHAT THE BUYER ASKS FOR</span>
                      <div className="tr-source-chip">
                        <IconFileText size={13} />
                        <span>University_RFP.pdf · Page 22</span>
                      </div>
                    </div>

                    <div className="tr-spec-value">
                      3 Years On-Site Support
                    </div>

                    <p className="tr-quote-snippet">
                      &ldquo;Clause 6.1: Supplier must provide a minimum 3-year on-site next-business-day warranty.&rdquo;
                    </p>
                  </div>

                  {/* Center Match Badge */}
                  <div className="tr-center-bridge pass">
                    <div className="tr-bridge-icon">✓</div>
                    <span className="tr-bridge-label">MATCH</span>
                  </div>

                  {/* Right: Supplier Proof */}
                  <div className="tr-spec-card proof">
                    <div className="tr-card-topbar">
                      <span className="tr-spec-eyebrow">WHAT YOUR DOCUMENT PROVES</span>
                      <div className="tr-source-chip">
                        <IconFileCertificate size={13} />
                        <span>OEM_Warranty_Letter.pdf · Page 1</span>
                      </div>
                    </div>

                    <div className="tr-spec-value">
                      36 Months (3 Years) Next-Day Service
                    </div>

                    <p className="tr-quote-snippet">
                      &ldquo;We confirm 36-month Premier Support with on-site technician dispatch by next business day.&rdquo;
                    </p>
                  </div>
                </div>

                {/* Bottom Verdict */}
                <div className="tr-verdict pass">
                  <div className="tr-verdict-icon"><IconShieldCheck size={24} /></div>
                  <div className="tr-verdict-body">
                    <div className="tr-verdict-title">
                      <strong>✓ Support Terms Verified</strong>
                      <span className="tr-verdict-tag">3-Year Service Confirmed</span>
                    </div>
                    <p className="tr-verdict-desc">
                      Your manufacturer letter guarantees 36 months (3 years) of next-business-day on-site repairs, completely satisfying the buyer's requirement.
                    </p>
                  </div>
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
