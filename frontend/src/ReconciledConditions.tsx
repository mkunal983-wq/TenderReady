import { dateRelationLabel } from './plainLanguage';
/** Source-backed interpretations remain reviewable, not approved compliance checks. */
type ConditionSource = {
  quote: string;
  page?: number | null;
  source_document_id?: string | null;
  source_url?: string | null;
};
export type QuantityCondition = ConditionSource & {
  kind: 'anticipated' | 'schedule';
  value_text: string;
  unit_text: string | null;
};
export type TemporalCondition = ConditionSource & {
  kind: string;
  relation?: string | null;
  anchor_text?: string | null;
  event_text?: string | null;
  period_text?: string | null;
  frequency_text?: string | null;
  anchor_date?: string | null;
  value_text?: string | null;
  unit_text?: string | null;
};

export function ReconciledConditions({ quantities = [], temporal = [], sourceBusy = false, onSource }: {
  quantities?: QuantityCondition[];
  temporal?: TemporalCondition[];
  sourceBusy?: boolean;
  onSource: (page: number, documentId: string) => void;
}) {
  function sourceButton(condition: ConditionSource, label: string) {
    const { page, source_document_id: documentId } = condition;
    return page && documentId ? <button className="source-link" disabled={sourceBusy} onClick={() => onSource(page, documentId)}>{label} · page {page}</button> : null;
  }
  return <>
    {quantities.length > 0 && <div><strong>Quantities</strong><ul>{quantities.map((condition, i) => <li key={i}>
      <span>{condition.kind === 'anticipated' ? 'Expected quantity' : 'Quantity listed in the tender'}: {condition.value_text} {condition.unit_text || ''}</span>
      {condition.kind === 'anticipated' && <p className="muted">This is an expected quantity. It does not promise an order or set a minimum to qualify.</p>}
      <blockquote className="preserve-lines">{condition.quote}</blockquote>{sourceButton(condition, 'Quantity source')}
    </li>)}</ul></div>}
    {temporal.length > 0 && <div><strong>When it is needed</strong><ul>{temporal.map((condition, i) => <li key={i}>
      <span>{({event:'Timing',repeating_period:'Each stated period',delivery_period:'Delivery time'} as Record<string,string>)[condition.kind] || condition.kind.replaceAll('_', ' ')}{condition.relation ? ` · ${dateRelationLabel(condition.relation)}` : ''}{condition.value_text ? ` · ${condition.value_text}${condition.unit_text ? ` ${condition.unit_text}` : ''}` : ''}</span>
      {condition.anchor_text && <p className="preserve-lines">{condition.anchor_text}</p>}
      {condition.event_text && <p className="preserve-lines">{condition.event_text}</p>}
      {condition.period_text && <p className="preserve-lines">{condition.period_text}</p>}
      {condition.frequency_text && <p className="preserve-lines">{condition.frequency_text}</p>}
      {condition.anchor_date && <p className="preserve-lines">Starting date: {condition.anchor_date}</p>}
      <blockquote className="preserve-lines">{condition.quote}</blockquote>{sourceButton(condition, 'Timing source')}
    </li>)}</ul></div>}
  </>;
}
