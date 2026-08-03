import { Pressable, StyleSheet, Text, View } from 'react-native';

export type SyncButtonStatus = 'idle' | 'in_flight' | 'error';

export interface SyncButtonProps {
  isWaking: boolean;
  status: SyncButtonStatus;
  errorMessage: string | null;
  onPress: () => void;
}

/**
 * mobile-dashboard spec "Manual Sync Control": disables itself while in
 * flight, surfaces failure without hiding the last known score (rendered by
 * a sibling ScoreCard — this component never unmounts anything else), and
 * distinguishes the cold-start "waking server" state (design.md) from a
 * real sync error so users aren't alarmed by expected ~30-60s latency.
 */
export function SyncButton({ isWaking, status, errorMessage, onPress }: SyncButtonProps) {
  const disabled = isWaking || status === 'in_flight';

  let label = 'Sync now';
  if (isWaking) {
    label = 'Waking server…';
  } else if (status === 'in_flight') {
    label = 'Syncing…';
  }

  return (
    <View style={styles.container}>
      <Pressable
        accessibilityRole="button"
        disabled={disabled}
        onPress={() => {
          if (!disabled) onPress();
        }}
        style={[styles.button, disabled ? styles.buttonDisabled : null]}
      >
        <Text style={styles.buttonText}>{label}</Text>
      </Pressable>
      {status === 'error' && errorMessage ? (
        <Text style={styles.error}>{errorMessage}</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    gap: 4,
  },
  button: {
    backgroundColor: '#1e6fd9',
    borderRadius: 8,
    paddingHorizontal: 20,
    paddingVertical: 10,
  },
  buttonDisabled: {
    backgroundColor: '#9db8d9',
  },
  buttonText: {
    color: '#ffffff',
    fontWeight: '600',
  },
  error: {
    color: '#b00020',
    fontSize: 13,
    textAlign: 'center',
  },
});
