import { fireEvent, render } from '@testing-library/react-native';
import { Text, View } from 'react-native';

import { SyncButton } from '../../src/components/SyncButton';

describe('SyncButton', () => {
  it('calls onPress when tapped while idle', async () => {
    const onPress = jest.fn();
    const { getByRole } = await render(
      <SyncButton isWaking={false} status="idle" errorMessage={null} onPress={onPress} />
    );

    fireEvent.press(getByRole('button'));

    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it('disables itself and shows a syncing label while in flight', async () => {
    const onPress = jest.fn();
    const { getByRole, getByText } = await render(
      <SyncButton isWaking={false} status="in_flight" errorMessage={null} onPress={onPress} />
    );

    expect(getByText(/syncing/i)).toBeTruthy();
    fireEvent.press(getByRole('button'));
    expect(onPress).not.toHaveBeenCalled();
  });

  it('shows a distinct "waking server" state instead of an error', async () => {
    const { getByText, queryByText } = await render(
      <SyncButton isWaking={true} status="idle" errorMessage={null} onPress={jest.fn()} />
    );

    expect(getByText(/waking server/i)).toBeTruthy();
    expect(queryByText(/error/i)).toBeNull();
  });

  it('surfaces a failure message without hiding sibling content (e.g. the score)', async () => {
    const { getByText } = await render(
      <View>
        <Text>72</Text>
        <SyncButton
          isWaking={false}
          status="error"
          errorMessage="Garmin login is locked. Manual unlock is required."
          onPress={jest.fn()}
        />
      </View>
    );

    expect(getByText('72')).toBeTruthy();
    expect(
      getByText('Garmin login is locked. Manual unlock is required.')
    ).toBeTruthy();
  });
});
