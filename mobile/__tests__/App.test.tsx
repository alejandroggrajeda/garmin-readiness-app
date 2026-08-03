import { render, waitFor } from '@testing-library/react-native';

import App from '../App';
import * as client from '../src/api/client';

jest.mock('../src/api/client');

const mockedClient = client as jest.Mocked<typeof client>;

describe('App', () => {
  beforeEach(() => {
    mockedClient.warmUp.mockResolvedValue(undefined);
    mockedClient.getCachedToday.mockReturnValue(null);
    mockedClient.getToday.mockResolvedValue({
      state: 'calibrating',
      score: null,
      band: null,
      factors: [],
      dominant_factor: null,
      reason: 'Still building your baseline.',
      confidence: 0,
      weights_version: 'v1',
      days_until_scored: 9,
      as_of: '2026-08-03',
      data_stale: false,
      last_synced_at: null,
    });
  });

  it('renders the dashboard screen as the initial route', async () => {
    const { getByText } = await render(<App />);

    expect(getByText('Garmin Readiness')).toBeTruthy();
  });

  it('shows the last-synced indicator on the dashboard, defaulting to "never"', async () => {
    const { getByText } = await render(<App />);

    await waitFor(() => {
      expect(getByText(/last synced: never/i)).toBeTruthy();
    });
  });
});
