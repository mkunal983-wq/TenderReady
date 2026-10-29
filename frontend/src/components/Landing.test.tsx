import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it } from 'vitest';
import { Landing } from './Landing';
it('switches illustrative scenarios and links to the existing workspace', async () => {
  render(<Landing/>);
  expect(screen.getByText('Storage threshold matches')).toBeVisible();
  await userEvent.click(screen.getByRole('button',{name:/Last-minute change/}));
  expect(screen.getByText('Earlier evidence needs reassessment')).toBeVisible();
  expect(screen.getByRole('button',{name:/Last-minute change/})).toHaveAttribute('aria-pressed','true');
  await userEvent.click(screen.getByRole('button',{name:/Warranty & repairs/}));
  expect(screen.getByText('Sample warranty terms match')).toBeVisible();
  expect(screen.getByText(/Illustrative sample text/)).toBeVisible();
  expect(screen.getByRole('link',{name:/Open workspaces/})).toHaveAttribute('href','#/workspaces');
});
