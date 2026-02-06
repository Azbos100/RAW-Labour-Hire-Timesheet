/**
 * RAW Labour Hire - Timesheet Mobile App
 * Main entry point with navigation
 */

import React, { useState, useEffect } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { StatusBar } from 'expo-status-bar';
import { Ionicons } from '@expo/vector-icons';
import * as SecureStore from 'expo-secure-store';

// Screens
import LoginScreen from './src/screens/LoginScreen';
import RegisterScreen from './src/screens/RegisterScreen';
import ResetPasswordScreen from './src/screens/ResetPasswordScreen';
import DashboardScreen from './src/screens/DashboardScreen';
import ClockInScreen from './src/screens/ClockInScreen';
import ClockOutScreen from './src/screens/ClockOutScreen';
import SupervisorSignatureScreen from './src/screens/SupervisorSignatureScreen';
import TimesheetsScreen from './src/screens/TimesheetsScreen';
import TimesheetDetailScreen from './src/screens/TimesheetDetailScreen';
import ProfileScreen from './src/screens/ProfileScreen';
import TicketsScreen from './src/screens/TicketsScreen';
import InductionScreen from './src/screens/InductionScreen';

// Context
import { AuthProvider, useAuth } from './src/context/AuthContext';

// Constants
import { COLORS } from './src/constants/colors';

// Types
export type RootStackParamList = {
  Login: undefined;
  Register: undefined;
  ResetPassword: undefined;
  Main: undefined;
  ClockIn: undefined;
  ClockOut: undefined;
  SupervisorSignature: { 
    entryId: number; 
    hoursWorked: string; 
    docketNumber: string;
  };
  TimesheetDetail: { timesheetId: number };
};

export type MainTabParamList = {
  Dashboard: undefined;
  Timesheets: undefined;
  Induction: undefined;
  Tickets: undefined;
  Profile: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();
const Tab = createBottomTabNavigator<MainTabParamList>();

function MainTabs() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        tabBarIcon: ({ focused, color, size }) => {
          let iconName: keyof typeof Ionicons.glyphMap;

          if (route.name === 'Dashboard') {
            iconName = focused ? 'home' : 'home-outline';
          } else if (route.name === 'Timesheets') {
            iconName = focused ? 'document-text' : 'document-text-outline';
          } else if (route.name === 'Induction') {
            iconName = focused ? 'shield-checkmark' : 'shield-checkmark-outline';
          } else if (route.name === 'Tickets') {
            iconName = focused ? 'card' : 'card-outline';
          } else if (route.name === 'Profile') {
            iconName = focused ? 'person' : 'person-outline';
          } else {
            iconName = 'ellipse';
          }

          return <Ionicons name={iconName} size={size} color={color} />;
        },
        tabBarActiveTintColor: COLORS.primary,
        tabBarInactiveTintColor: COLORS.gray,
        headerStyle: {
          backgroundColor: COLORS.primary,
        },
        headerTintColor: COLORS.white,
        headerTitleStyle: {
          fontWeight: 'bold',
        },
      })}
    >
      <Tab.Screen 
        name="Dashboard" 
        component={DashboardScreen}
        options={{ title: 'RAW Timesheet' }}
      />
      <Tab.Screen 
        name="Timesheets" 
        component={TimesheetsScreen}
        options={{ title: 'My Timesheets' }}
      />
      <Tab.Screen 
        name="Induction" 
        component={InductionScreen}
        options={{ title: 'Induction' }}
      />
      <Tab.Screen 
        name="Tickets" 
        component={TicketsScreen}
        options={{ title: 'My Tickets' }}
      />
      <Tab.Screen 
        name="Profile" 
        component={ProfileScreen}
        options={{ title: 'Profile' }}
      />
    </Tab.Navigator>
  );
}

function AppNavigator() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return null; // Or a loading screen
  }

  return (
    <Stack.Navigator
      screenOptions={{
        headerStyle: {
          backgroundColor: COLORS.primary,
        },
        headerTintColor: COLORS.white,
        headerTitleStyle: {
          fontWeight: 'bold',
        },
      }}
    >
      {!isAuthenticated ? (
        // Auth screens
        <>
          <Stack.Screen 
            name="Login" 
            component={LoginScreen}
            options={{ headerShown: false }}
          />
          <Stack.Screen 
            name="Register" 
            component={RegisterScreen}
            options={{ title: 'Create Account' }}
          />
          <Stack.Screen 
            name="ResetPassword" 
            component={ResetPasswordScreen}
            options={{ title: 'Reset Password' }}
          />
        </>
      ) : (
        // App screens
        <>
          <Stack.Screen 
            name="Main" 
            component={MainTabs}
            options={{ headerShown: false }}
          />
          <Stack.Screen 
            name="ClockIn" 
            component={ClockInScreen}
            options={{ title: 'Clock In' }}
          />
          <Stack.Screen 
            name="ClockOut" 
            component={ClockOutScreen}
            options={{ title: 'Clock Out' }}
          />
          <Stack.Screen 
            name="SupervisorSignature" 
            component={SupervisorSignatureScreen}
            options={{ 
              title: 'Supervisor Sign-Off',
              headerBackVisible: false, // Prevent going back without signing
            }}
          />
          <Stack.Screen 
            name="TimesheetDetail" 
            component={TimesheetDetailScreen}
            options={{ title: 'Timesheet Details' }}
          />
        </>
      )}
    </Stack.Navigator>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <NavigationContainer>
        <StatusBar style="light" />
        <AppNavigator />
      </NavigationContainer>
    </AuthProvider>
  );
}

export { COLORS };
