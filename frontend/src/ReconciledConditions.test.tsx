import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { ReconciledConditions } from './ReconciledConditions';

it('preserves anticipated quantity wording and uses the exact condition source', async () => {
  const onSource = vi.fn();
  render(<ReconciledConditions onSource={onSource} quantities={[{ kind: 'anticipated', value_text: 'approximately 80', unit_text: 'laptops', quote: 'The anticipated quantity is approximately 80 laptops.', page: 2, source_document_id: 'original' }]}/>);
  expect(screen.getByText('Expected quantity: approximately 80 laptops')).toBeVisible();
  expect(screen.getByText('This is an expected quantity. It does not promise an order or set a minimum to qualify.')).toBeVisible();
  expect(screen.getByText('The anticipated quantity is approximately 80 laptops.')).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: 'Quantity source · page 2' }));
  expect(onSource).toHaveBeenCalledWith(2, 'original');
});

it('keeps a relative period anchored to its source text without inventing a calendar date', async () => {
  const onSource = vi.fn();
  const condition = { kind: 'delivery_period', relation: 'within', anchor_text: 'receipt of the purchase order', value_text: '30', unit_text: 'days', quote: 'Delivery must be completed within 30 days of receipt of the purchase order.', page: 4, source_document_id: 'original' };
  const { rerender } = render(<ReconciledConditions onSource={onSource} temporal={[condition]} sourceBusy/>);
  expect(screen.getByText('Delivery time · within · 30 days')).toBeVisible();
  expect(screen.getByText('receipt of the purchase order')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Timing source · page 4' })).toBeDisabled();
  rerender(<ReconciledConditions onSource={onSource} temporal={[condition]}/>);
  await userEvent.click(screen.getByRole('button', { name: 'Timing source · page 4' }));
  expect(onSource).toHaveBeenCalledWith(4, 'original');
});

it('does not invent a source link for a condition without a document and page', () => {
  render(<ReconciledConditions onSource={vi.fn()} quantities={[{ kind: 'schedule', value_text: '80', unit_text: 'laptops', quote: '80 laptops' }]}/>);
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
});

it('renders source-backed event and repeating-period shapes without requiring an inferred relation or date', async () => {
  const onSource = vi.fn();
  render(<ReconciledConditions onSource={onSource} temporal={[
    { kind: 'event', event_text: 'at the time of delivery', relation: 'at_event', quote: 'The certificate must be valid at the time of delivery.', page: 6, source_document_id: 'original' },
    { kind: 'repeating_period', period_text: 'during each of the last three years', frequency_text: 'per annum', anchor_date: null, quote: 'Turnover of Rs 5 crore per annum during each of the last three years.', page: 7, source_document_id: 'original' },
  ]}/>);
  expect(screen.getByText('Timing · When this event happens')).toBeVisible();
  expect(screen.getByText('at the time of delivery')).toBeVisible();
  expect(screen.getByText('Each stated period')).toBeVisible();
  expect(screen.getByText('during each of the last three years')).toBeVisible();
  expect(screen.getByText('per annum')).toBeVisible();
  expect(screen.queryByText(/Starting date:/)).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Timing source · page 7' }));
  expect(onSource).toHaveBeenCalledWith(7, 'original');
});
