import { render } from '@testing-library/react-native';

import { ScoreCard } from '../../src/components/ScoreCard';
import type { ReadinessToday } from '../../src/api/types';

function makeToday(overrides: Partial<ReadinessToday>): ReadinessToday {
  return {
    state: 'scored',
    score: 72,
    band: 'moderate',
    factors: [],
    dominant_factor: 'hrv',
    reason: 'HRV is below your baseline.',
    confidence: 1,
    weights_version: 'v1',
    days_until_scored: null,
    as_of: '2026-08-03',
    data_stale: false,
    last_synced_at: '2026-08-03T08:00:00Z',
    ...overrides,
  };
}

describe('ScoreCard', () => {
  it('shows the score, band and reason when scored', async () => {
    const { getByText } = await render(
      <ScoreCard data={makeToday({})} loading={false} error={null} />
    );

    expect(getByText('72')).toBeTruthy();
    expect(getByText(/moderate/i)).toBeTruthy();
    expect(getByText('HRV is below your baseline.')).toBeTruthy();
  });

  it('shows a calibrating indicator with days remaining and no score', async () => {
    const { getByText, queryByText } = await render(
      <ScoreCard
        data={makeToday({
          state: 'calibrating',
          score: null,
          band: null,
          days_until_scored: 12,
          reason: 'Still building your baseline.',
        })}
        loading={false}
        error={null}
      />
    );

    expect(getByText(/calibrating/i)).toBeTruthy();
    expect(getByText(/12 day/i)).toBeTruthy();
    expect(queryByText('72')).toBeNull();
  });

  it('shows an insufficient-data message when state is insufficient', async () => {
    const { getByText } = await render(
      <ScoreCard
        data={makeToday({ state: 'insufficient', score: null, band: null })}
        loading={false}
        error={null}
      />
    );

    expect(getByText(/insufficient data/i)).toBeTruthy();
  });

  it('shows a loading indicator when loading and no data yet', async () => {
    const { getByText } = await render(
      <ScoreCard data={null} loading={true} error={null} />
    );

    expect(getByText(/loading/i)).toBeTruthy();
  });

  it('shows an error message without any data', async () => {
    const { getByText } = await render(
      <ScoreCard data={null} loading={false} error="Could not reach the server." />
    );

    expect(getByText('Could not reach the server.')).toBeTruthy();
  });
});
