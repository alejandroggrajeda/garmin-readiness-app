import { StyleSheet, Text, View } from 'react-native';

import type { ReadinessToday } from '../api/types';

export interface ScoreCardProps {
  data: ReadinessToday | null;
  loading: boolean;
  error: string | null;
}

const BAND_LABEL: Record<string, string> = {
  train_hard: 'Train hard',
  moderate: 'Moderate',
  easy: 'Easy',
  rest: 'Rest',
};

/**
 * Core value proposition of the app (design.md / mobile-dashboard spec
 * "Readiness Card Display"): the score is secondary to the plain-language
 * reason naming the dominant factor(s) — this renders that sentence
 * prominently, not just the raw number.
 */
export function ScoreCard({ data, loading, error }: ScoreCardProps) {
  if (loading && !data) {
    return (
      <View style={styles.card} testID="score-card-loading">
        <Text style={styles.status}>Loading today's readiness…</Text>
      </View>
    );
  }

  if (!data) {
    return (
      <View style={styles.card} testID="score-card-error">
        <Text style={styles.status}>{error ?? 'No readiness data available yet.'}</Text>
      </View>
    );
  }

  if (data.state === 'calibrating') {
    return (
      <View style={styles.card} testID="score-card-calibrating">
        <Text style={styles.status}>
          Calibrating
          {data.days_until_scored != null
            ? ` — ${data.days_until_scored} day${data.days_until_scored === 1 ? '' : 's'} remaining`
            : ''}
        </Text>
        <Text style={styles.reason}>{data.reason}</Text>
      </View>
    );
  }

  if (data.state === 'insufficient') {
    return (
      <View style={styles.card} testID="score-card-insufficient">
        <Text style={styles.status}>Insufficient data to compute readiness.</Text>
        <Text style={styles.reason}>{data.reason}</Text>
      </View>
    );
  }

  return (
    <View style={styles.card} testID="score-card-scored">
      <Text style={styles.score}>{data.score}</Text>
      <Text style={styles.band}>{data.band ? BAND_LABEL[data.band] ?? data.band : ''}</Text>
      <Text style={styles.reason}>{data.reason}</Text>
      {data.data_stale ? (
        <Text style={styles.stale}>Showing the last available data — not from today.</Text>
      ) : null}
      {error ? <Text style={styles.status}>{error}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    alignItems: 'center',
    gap: 6,
    padding: 16,
  },
  score: {
    fontSize: 48,
    fontWeight: '700',
  },
  band: {
    fontSize: 18,
    fontWeight: '600',
    textTransform: 'capitalize',
  },
  reason: {
    fontSize: 15,
    textAlign: 'center',
    color: '#333333',
  },
  status: {
    fontSize: 16,
    textAlign: 'center',
  },
  stale: {
    fontSize: 12,
    color: '#8a6d00',
  },
});
