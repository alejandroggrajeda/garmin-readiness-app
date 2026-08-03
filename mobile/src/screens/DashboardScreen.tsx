import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text } from 'react-native';

import * as client from '../api/client';
import { LastSynced } from '../components/LastSynced';
import { ScoreCard } from '../components/ScoreCard';
import { SyncButton, type SyncButtonStatus } from '../components/SyncButton';
import type { RootStackParamList } from '../navigation/RootNavigator';
import type { ReadinessToday } from '../api/types';

const SYNC_POLL_INTERVAL_MS = 3000;

type Props = NativeStackScreenProps<RootStackParamList, 'Dashboard'>;

/**
 * Wires the readiness card, sync control and last-synced indicator together
 * against the live API (mobile-dashboard spec). Replaces the Phase 1
 * placeholder shell — expected per tasks.md's Phase 7 note, not a conflict.
 */
export function DashboardScreen({ navigation }: Props) {
  const [isWaking, setIsWaking] = useState(true);
  const [today, setToday] = useState<ReadinessToday | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [syncStatus, setSyncStatus] = useState<SyncButtonStatus>('idle');
  const [syncError, setSyncError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadToday = useCallback(async () => {
    try {
      const data = await client.getToday();
      setToday(data);
      setLoadError(null);
    } catch {
      const cached = client.getCachedToday();
      setToday(cached);
      setLoadError('Could not reach the server. Showing last known data.');
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      await client.warmUp();
      if (cancelled) return;
      setIsWaking(false);
      await loadToday();
    })();
    return () => {
      cancelled = true;
    };
  }, [loadToday]);

  useEffect(
    () => () => {
      if (pollRef.current) clearInterval(pollRef.current);
    },
    []
  );

  const pollSyncRun = useCallback(
    (runId: string) => {
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        try {
          const run = await client.getSyncRun(runId);
          if (run.status === 'completed') {
            if (pollRef.current) clearInterval(pollRef.current);
            setSyncStatus('idle');
            await loadToday();
          } else if (run.status === 'failed' || run.status === 'abandoned') {
            if (pollRef.current) clearInterval(pollRef.current);
            setSyncStatus('error');
            setSyncError('Sync failed. Your last known score is still shown.');
          }
        } catch {
          // Transient poll error — keep polling until the interval above
          // is cleared by a terminal status or the component unmounts.
        }
      }, SYNC_POLL_INTERVAL_MS);
    },
    [loadToday]
  );

  const handleSync = useCallback(async () => {
    setSyncStatus('in_flight');
    setSyncError(null);
    try {
      const result = await client.triggerSync();
      switch (result.kind) {
        case 'accepted':
          pollSyncRun(result.runId);
          break;
        case 'in_progress':
          if (result.runId) {
            pollSyncRun(result.runId);
          } else {
            setSyncStatus('error');
            setSyncError('A sync is already in progress.');
          }
          break;
        case 'auth_locked':
          setSyncStatus('error');
          setSyncError(
            'Garmin login is locked after a failed sign-in. Manual unlock is required before syncing again.'
          );
          break;
        case 'cooldown': {
          const minutes = Math.ceil(result.retryAfterSeconds / 60);
          setSyncStatus('error');
          setSyncError(`Please wait before syncing again (about ${minutes} min).`);
          break;
        }
      }
    } catch {
      setSyncStatus('error');
      setSyncError('Could not start sync. Please try again.');
    }
  }, [pollSyncRun]);

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>Garmin Readiness</Text>
      <ScoreCard data={today} loading={isWaking && !today} error={loadError} />
      <LastSynced lastSyncedAt={today?.last_synced_at ?? null} />
      <SyncButton
        isWaking={isWaking}
        status={syncStatus}
        errorMessage={syncError}
        onPress={handleSync}
      />
      <Pressable onPress={() => navigation.navigate('Trends')} accessibilityRole="link">
        <Text style={styles.link}>View trends</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    gap: 16,
    padding: 24,
  },
  title: {
    fontSize: 24,
    fontWeight: '600',
  },
  link: {
    color: '#1e6fd9',
    fontSize: 15,
  },
});
