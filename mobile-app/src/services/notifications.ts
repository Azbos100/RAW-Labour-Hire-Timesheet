/**
 * Push Notifications Service
 * Using Expo Push Notifications
 */

import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import Constants from 'expo-constants';
import { Platform, Linking } from 'react-native';
import api from './api';

// Configure notification handler
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

/**
 * Create the Android notification channel.
 *
 * IMPORTANT: this does NOT require notification permission and should run on app
 * start. On many Android phones (e.g. Samsung) an app only appears under
 * Settings > Notifications once it has registered a channel, so creating it
 * early is what makes "RAW Timesheet" show up and become toggle-able.
 */
export async function ensureAndroidNotificationChannel(): Promise<void> {
  if (Platform.OS !== 'android') return;
  try {
    await Notifications.setNotificationChannelAsync('default', {
      name: 'Job Alerts & Reminders',
      importance: Notifications.AndroidImportance.MAX,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: '#EA580C',
    });
  } catch (error) {
    console.warn('Failed to set notification channel:', error);
  }
}

/**
 * Whether notifications are currently allowed by the OS.
 */
export async function areNotificationsEnabled(): Promise<boolean> {
  const { status } = await Notifications.getPermissionsAsync();
  return status === 'granted';
}

/**
 * Ask the OS for notification permission. Returns the final status.
 */
export async function requestNotificationPermission(): Promise<string> {
  const { status: existing } = await Notifications.getPermissionsAsync();
  if (existing === 'granted') return 'granted';
  const { status } = await Notifications.requestPermissionsAsync();
  return status;
}

/**
 * Open this app's system settings page so the user can enable notifications
 * manually (used when the OS won't show the prompt again).
 */
export async function openAppNotificationSettings(): Promise<void> {
  try {
    await Linking.openSettings();
  } catch (error) {
    console.warn('Failed to open app settings:', error);
  }
}

/**
 * Register for push notifications and get the Expo push token
 */
export async function registerForPushNotificationsAsync(): Promise<string | null> {
  let token: string | null = null;

  // Create the Android channel first so the app shows up in notification
  // settings even before/without permission being granted.
  await ensureAndroidNotificationChannel();

  // Must be a physical device
  if (!Device.isDevice) {
    console.log('Push notifications require a physical device');
    return null;
  }

  // Check existing permissions
  const { status: existingStatus } = await Notifications.getPermissionsAsync();
  let finalStatus = existingStatus;

  // Request permission if not granted
  if (existingStatus !== 'granted') {
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
  }

  if (finalStatus !== 'granted') {
    console.log('Push notification permission not granted');
    return null;
  }

  // Get the Expo push token
  try {
    const projectId = Constants.expoConfig?.extra?.eas?.projectId;
    const tokenData = await Notifications.getExpoPushTokenAsync({
      projectId: projectId,
    });
    token = tokenData.data;
    console.log('Push token:', token);
  } catch (error) {
    console.error('Error getting push token:', error);
    return null;
  }

  return token;
}

/**
 * Save push token to backend for a user
 */
export async function savePushToken(userId: number, token: string): Promise<boolean> {
  try {
    await api.post(`/users/${userId}/push-token`, { push_token: token });
    console.log('Push token saved to backend');
    return true;
  } catch (error) {
    console.error('Error saving push token:', error);
    return false;
  }
}

/**
 * Add notification received listener
 */
export function addNotificationReceivedListener(
  callback: (notification: Notifications.Notification) => void
) {
  return Notifications.addNotificationReceivedListener(callback);
}

/**
 * Add notification response listener (when user taps notification)
 */
export function addNotificationResponseReceivedListener(
  callback: (response: Notifications.NotificationResponse) => void
) {
  return Notifications.addNotificationResponseReceivedListener(callback);
}

/**
 * Remove notification subscription
 */
export function removeNotificationSubscription(subscription: Notifications.Subscription) {
  Notifications.removeNotificationSubscription(subscription);
}
