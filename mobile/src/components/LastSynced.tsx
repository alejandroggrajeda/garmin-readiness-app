import { StyleSheet, Text } from 'react-native';

export interface LastSyncedProps {
  lastSyncedAt: string | null;
}

function formatTimestamp(isoTimestamp: string): string {
  const parsed = new Date(isoTimestamp);
  if (Number.isNaN(parsed.getTime())) {
    return isoTimestamp;
  }
  return parsed.toLocaleString();
}

/**
 * mobile-dashboard spec "Last Synced Timestamp Display": always visible so
 * gaps between manual syncs (this app has no scheduled sync) are transparent
 * instead of silently implying live data.
 */
export function LastSynced({ lastSyncedAt }: LastSyncedProps) {
  return (
    <Text style={styles.text}>
      Last synced: {lastSyncedAt ? formatTimestamp(lastSyncedAt) : 'never'}
    </Text>
  );
}

const styles = StyleSheet.create({
  text: {
    fontSize: 13,
    color: '#666666',
  },
});
