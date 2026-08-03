import { StyleSheet, Text, View } from 'react-native';

/**
 * Placeholder shell for the readiness dashboard.
 *
 * The score card, sync-now control, trends chart and a real last-synced
 * timestamp (sourced from `GET /api/readiness/today`) are implemented in
 * the mobile-dashboard capability (Phase 7). This Phase 1 shell only proves
 * the navigation/screen structure and the test harness.
 */
export function DashboardScreen() {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>Garmin Readiness</Text>
      <Text style={styles.placeholder}>Last synced: not yet available</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  title: {
    fontSize: 24,
    fontWeight: '600',
  },
  placeholder: {
    fontSize: 14,
    color: '#666666',
  },
});
