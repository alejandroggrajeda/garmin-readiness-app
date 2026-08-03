import { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text } from 'react-native';

import * as client from '../api/client';
import { TrendsChart } from '../components/TrendsChart';
import type { HistoryEntry } from '../api/types';

const HISTORY_DAYS = 30;

/**
 * mobile-dashboard spec "Trend Charts": renders historical trend charts
 * from `GET /api/readiness/history`.
 */
export function TrendsScreen() {
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await client.getHistory(HISTORY_DAYS);
        if (!cancelled) {
          setHistory(data);
          setError(null);
        }
      } catch {
        if (!cancelled) {
          setError('Could not load trend history.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>Last {HISTORY_DAYS} days</Text>
      {loading ? <Text>Loading trends…</Text> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {!loading && !error ? <TrendsChart history={history} /> : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 12,
    padding: 16,
  },
  title: {
    fontSize: 18,
    fontWeight: '600',
  },
  error: {
    color: '#b00020',
  },
});
