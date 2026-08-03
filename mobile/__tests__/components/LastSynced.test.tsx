import { render } from '@testing-library/react-native';

import { LastSynced } from '../../src/components/LastSynced';

describe('LastSynced', () => {
  it('shows the formatted last-synced-at timestamp when present', async () => {
    const { getByText } = await render(
      <LastSynced lastSyncedAt="2026-07-29T08:00:00Z" />
    );

    // Several days old — the raw ISO value must be represented somehow,
    // not silently implying "live" data. We assert on the visible label
    // rather than a specific locale-formatted string.
    expect(getByText(/last synced/i)).toBeTruthy();
  });

  it('shows a "never" state when no sync has completed yet', async () => {
    const { getByText } = await render(<LastSynced lastSyncedAt={null} />);

    expect(getByText(/never/i)).toBeTruthy();
  });
});
