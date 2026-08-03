import { render } from '@testing-library/react-native';

import { TrendsChart } from '../../src/components/TrendsChart';
import type { HistoryEntry } from '../../src/api/types';

describe('TrendsChart', () => {
  it('renders one point per day of history', async () => {
    const history: HistoryEntry[] = [
      { date: '2026-08-01', score: 60, band: 'moderate', state: 'scored' },
      { date: '2026-08-02', score: 65, band: 'moderate', state: 'scored' },
      { date: '2026-08-03', score: 70, band: 'easy', state: 'scored' },
    ];

    const { getAllByTestId } = await render(<TrendsChart history={history} />);

    expect(getAllByTestId(/^trend-point-/)).toHaveLength(3);
  });

  it('shows an empty-state message when there is no history yet', async () => {
    const { getByText } = await render(<TrendsChart history={[]} />);

    expect(getByText(/no trend data/i)).toBeTruthy();
  });
});
