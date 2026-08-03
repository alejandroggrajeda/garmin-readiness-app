import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';

import { DashboardScreen } from '../screens/DashboardScreen';
import { TrendsScreen } from '../screens/TrendsScreen';

export type RootStackParamList = {
  Dashboard: undefined;
  Trends: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();

export function RootNavigator() {
  return (
    <NavigationContainer>
      <Stack.Navigator initialRouteName="Dashboard">
        <Stack.Screen name="Dashboard" component={DashboardScreen} options={{ title: 'Garmin Readiness' }} />
        <Stack.Screen name="Trends" component={TrendsScreen} options={{ title: 'Trends' }} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
