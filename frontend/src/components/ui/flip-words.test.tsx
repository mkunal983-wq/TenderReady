import { render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { FlipWords } from './flip-words';

const preference = vi.hoisted(() => ({ reduced: false }));
vi.mock('motion/react', async importOriginal => ({
  ...await importOriginal<typeof import('motion/react')>(),
  useReducedMotion: () => preference.reduced,
}));
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); preference.reduced = false; });

it('keeps the first word static without animation timers for reduced motion', () => {
  preference.reduced = true;
  vi.useFakeTimers();
  render(<FlipWords words={['better', 'cute']} />);
  expect(screen.getByText('better')).toBeVisible();
  expect(vi.getTimerCount()).toBe(0);
});

it('cancels the pending word change when unmounted', () => {
  vi.useFakeTimers();
  const schedule = vi.spyOn(globalThis, 'setTimeout');
  const cancel = vi.spyOn(globalThis, 'clearTimeout');
  const { unmount } = render(<FlipWords words={['better', 'cute']} />);
  const timerIndex = schedule.mock.calls.findIndex(call => call[1] === 3000);
  expect(timerIndex).toBeGreaterThanOrEqual(0);
  const timer = schedule.mock.results[timerIndex].value;
  unmount();
  expect(cancel).toHaveBeenCalledWith(timer);
});

it('accepts an empty word list and allows caller utilities to override defaults', () => {
  const { container } = render(<FlipWords words={[]} className="px-4 text-red-500" />);
  expect(container.firstChild).toHaveClass('px-4', 'text-red-500');
  expect(container.firstChild).not.toHaveClass('px-2', 'text-neutral-900');
});
