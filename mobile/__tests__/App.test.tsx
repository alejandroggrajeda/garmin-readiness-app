import { render } from '@testing-library/react-native';

import App from '../App';

describe('App', () => {
  it('renders the dashboard screen as the initial route', async () => {
    const { getByText } = await render(<App />);

    expect(getByText('Garmin Readiness')).toBeTruthy();
  });

  it('shows the last-synced placeholder on the dashboard shell', async () => {
    const { getByText } = await render(<App />);

    expect(getByText(/last synced/i)).toBeTruthy();
  });
});
