import { StyleSheet, Text, View } from 'react-native';

import type { HistoryEntry } from '../api/types';

export interface TrendsChartProps {
  history: HistoryEntry[];
}

function formatShortDate(isoDate: string): string {
  const parsed = new Date(isoDate);
  if (Number.isNaN(parsed.getTime())) {
    return isoDate;
  }
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/**
 * mobile-dashboard spec "Trend Charts": one point per day from the history
 * endpoint. No charting library is part of the PR1 scaffold, so this renders
 * a minimal bar-per-day view directly with Views/Text rather than adding a
 * new dependency for a single trend view.
 */
export function TrendsChart({ history }: TrendsChartProps) {
  if (history.length === 0) {
    return (
      <View style={styles.empty}>
        <Text>No trend data yet.</Text>
      </View>
    );
  }

  const maxScore = Math.max(...history.map((entry) => entry.score ?? 0), 1);

  return (
    <View
      style={styles.chart}
      accessibilityLabel={`Trend chart with ${history.length} days`}
    >
      {history.map((entry) => {
        const heightPct = entry.score != null ? (entry.score / maxScore) * 100 : 4;
        return (
          <View key={entry.date} testID={`trend-point-${entry.date}`} style={styles.column}>
            <View style={styles.barTrack}>
              <View style={[styles.bar, { height: `${heightPct}%` }]} />
            </View>
            <Text style={styles.label}>{formatShortDate(entry.date)}</Text>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  chart: {
    alignItems: 'flex-end',
    flexDirection: 'row',
    gap: 4,
    height: 120,
  },
  column: {
    alignItems: 'center',
    flex: 1,
    gap: 2,
  },
  barTrack: {
    height: 90,
    justifyContent: 'flex-end',
    width: 8,
  },
  bar: {
    backgroundColor: '#1e6fd9',
    borderRadius: 4,
    width: '100%',
  },
  label: {
    fontSize: 9,
    color: '#666666',
  },
  empty: {
    padding: 16,
  },
});
