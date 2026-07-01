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
/**
 * Report why push registration succeeded/failed to the backend so it shows up in
 * server logs. Fire-and-forget; never throws. (Temporary diagnostic aid.)
 */
export async function reportPushDebug(userId: number | undefined, info: Record<string, any>): Promise<void> {
  try {
    await api.post(`/users/${userId ?? 0}/push-debug`, info);
  } catch {
    // ignore — diagnostics must never break the app
  }
}

export async function registerForPushNotificationsAsync(debugUserId?: number): Promise<string | null> {
  let token: string | null = null;

  const diag: Record<string, any> = {
    isDevice: Device.isDevice,
    brand: Device.brand,
    model: Device.modelName,
    os: Device.osName,
    osVersion: Device.osVersion,
    appVersion: Constants.expoConfig?.version,
    runtimeVersion: (Constants as any).expoConfig?.runtimeVersion ?? null,
  };

  // Create the Android channel first so the app shows up in notification
  // settings even before/without permission being granted.
  await ensureAndroidNotificationChannel();

  // Must be a physical device
  if (!Device.isDevice) {
    console.log('Push notifications require a physical device');
    diag.result = 'not_physical_device';
    reportPushDebug(debugUserId, diag);
    return null;
  }

  // Check existing permissions
  const { status: existingStatus } = await Notifications.getPermissionsAsync();
  let finalStatus = existingStatus;
  diag.permExisting = existingStatus;

  // Request permission if not granted
  if (existingStatus !== 'granted') {
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
  }
  diag.permFinal = finalStatus;

  if (finalStatus !== 'granted') {
    console.log('Push notification permission not granted');
    diag.result = 'permission_denied';
    reportPushDebug(debugUserId, diag);
    return null;
  }

  // Get the Expo push token
  try {
    const projectId = Constants.expoConfig?.extra?.eas?.projectId;
    diag.projectId = projectId ?? null;
    const tokenData = await Notifications.getExpoPushTokenAsync({
      projectId: projectId,
    });
    token = tokenData.data;
    console.log('Push token:', token);
    diag.result = 'ok';
    diag.tokenPrefix = token ? token.slice(0, 22) : null;
  } catch (error: any) {
    console.error('Error getting push token:', error);
    diag.result = 'get_token_error';
    diag.error = String(error?.message || error);
    reportPushDebug(debugUserId, diag);
    return null;
  }

  reportPushDebug(debugUserId, diag);
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
