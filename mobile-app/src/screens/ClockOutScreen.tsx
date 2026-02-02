/**
 * Clock Out Screen
 * GPS-enabled clock out with comments and injury report
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Alert,
  ActivityIndicator,
  TextInput,
  Switch,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Location from 'expo-location';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../../App';
import { COLORS } from '../constants/colors';
import { clockAPI } from '../services/api';
import { useAuth } from '../context/AuthContext';

type ClockOutScreenProps = {
  navigation: NativeStackNavigationProp<RootStackParamList, 'ClockOut'>;
};

export default function ClockOutScreen({ navigation }: ClockOutScreenProps) {
  const { user } = useAuth();
  const [location, setLocation] = useState<Location.LocationObject | null>(null);
  const [address, setAddress] = useState<string>('');
  const [isLoadingLocation, setIsLoadingLocation] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [comments, setComments] = useState('');
  const [firstAidInjury, setFirstAidInjury] = useState(false);

  useEffect(() => {
    getLocation();
  }, []);

  const getLocation = async () => {
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert(
          'Permission Required',
          'Location permission is required to clock out. Please enable it in settings.'
        );
        setIsLoadingLocation(false);
        return;
      }

      const location = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.High,
      });
      setLocation(location);

      // Reverse geocode to get address
      const [addressResult] = await Location.reverseGeocodeAsync({
        latitude: location.coords.latitude,
        longitude: location.coords.longitude,
      });

      if (addressResult) {
        const parts = [
          addressResult.streetNumber,
          addressResult.street,
          addressResult.city,
          addressResult.region,
          addressResult.postalCode,
        ].filter(Boolean);
        setAddress(parts.join(', '));
      }
    } catch (error) {
      console.error('Error getting location:', error);
      Alert.alert('Location Error', 'Unable to get your current location. Please try again.');
    } finally {
      setIsLoadingLocation(false);
    }
  };

  const handleClockOut = async () => {
    if (!location) {
      Alert.alert('Error', 'Unable to get your location. Please try again.');
      return;
    }

    // Confirm if injury is reported
    if (firstAidInjury) {
      Alert.alert(
        'Injury Reported',
        'You have indicated a first aid/injury incident. This will be flagged on your timesheet.',
        [
          { text: 'Cancel', style: 'cancel' },
          { text: 'Continue', onPress: () => submitClockOut() },
        ]
      );
    } else {
      submitClockOut();
    }
  };

  const submitClockOut = async () => {
    setIsSubmitting(true);
    try {
      const response = await clockAPI.clockOut({
        latitude: location!.coords.latitude,
        longitude: location!.coords.longitude,
        comments: comments || undefined,
        first_aid_injury: firstAidInjury,
        user_id: user?.id,
      });

      const { ordinary_hours, overtime_hours, total_hours } = response.data;

      Alert.alert(
        'Clocked Out!',
        `Hours Worked:\n• Ordinary: ${ordinary_hours}h\n• Overtime: ${overtime_hours}h\n• Total: ${total_hours}h`,
        [{ text: 'OK', onPress: () => navigation.goBack() }]
      );
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Failed to clock out. Please try again.';
      Alert.alert('Error', message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <KeyboardAvoidingView 
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 100 : 0}
    >
    <ScrollView 
      style={styles.scrollView}
      contentContainerStyle={styles.scrollContent}
      keyboardShouldPersistTaps="handled"
    >
      {/* Location Status */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Your Location</Text>
        <View style={styles.locationCard}>
          {isLoadingLocation ? (
            <View style={styles.loadingLocation}>
              <ActivityIndicator color={COLORS.primary} />
              <Text style={styles.loadingText}>Getting your location...</Text>
            </View>
          ) : location ? (
            <>
              <View style={styles.locationRow}>
                <Ionicons name="location" size={24} color={COLORS.primary} />
                <View style={styles.locationInfo}>
                  <Text style={styles.locationAddress}>{address || 'Address found'}</Text>
                  <Text style={styles.locationCoords}>
                    {location.coords.latitude.toFixed(6)}, {location.coords.longitude.toFixed(6)}
                  </Text>
                </View>
              </View>
              <TouchableOpacity style={styles.refreshButton} onPress={getLocation}>
                <Ionicons name="refresh" size={20} color={COLORS.primary} />
                <Text style={styles.refreshText}>Refresh</Text>
              </TouchableOpacity>
            </>
          ) : (
            <View style={styles.errorLocation}>
              <Ionicons name="warning" size={24} color="#F59E0B" />
              <Text style={styles.errorText}>Unable to get location</Text>
              <TouchableOpacity style={styles.retryButton} onPress={getLocation}>
                <Text style={styles.retryText}>Try Again</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>
      </View>

      {/* First Aid / Injury */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>First Aid / Injury</Text>
        <View style={styles.injuryCard}>
          <View style={styles.injuryRow}>
            <View style={styles.injuryInfo}>
              <Text style={styles.injuryLabel}>Report an injury or first aid incident?</Text>
              <Text style={styles.injuryHint}>
                Toggle on if you or someone was injured on site
              </Text>
            </View>
            <Switch
              value={firstAidInjury}
              onValueChange={setFirstAidInjury}
              trackColor={{ false: '#D1D5DB', true: '#93C5FD' }}
              thumbColor={firstAidInjury ? COLORS.primary : '#F3F4F6'}
            />
          </View>
          {firstAidInjury && (
            <View style={styles.injuryWarning}>
              <Ionicons name="warning" size={20} color="#1E3A8A" />
              <Text style={styles.injuryWarningText}>
                Injury reported - please provide details in comments
              </Text>
            </View>
          )}
        </View>
      </View>

      {/* Comments */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Comments</Text>
        <TextInput
          style={styles.commentsInput}
          placeholder="Add any notes about today's work..."
          placeholderTextColor="#9CA3AF"
          value={comments}
          onChangeText={setComments}
          multiline
          numberOfLines={4}
          textAlignVertical="top"
        />
      </View>

      {/* Clock Out Button */}
      <TouchableOpacity
        style={[
          styles.clockOutButton,
          (!location || isSubmitting) && styles.clockOutButtonDisabled,
        ]}
        onPress={handleClockOut}
        disabled={!location || isSubmitting}
      >
        {isSubmitting ? (
          <ActivityIndicator color="#FFFFFF" />
        ) : (
          <>
            <Ionicons name="log-out-outline" size={24} color="#FFFFFF" />
            <Text style={styles.clockOutButtonText}>CLOCK OUT</Text>
          </>
        )}
      </TouchableOpacity>

      <View style={styles.footer}>
        <Text style={styles.footerText}>
          Your GPS location and time will be recorded for this clock-out.
          Hours will be automatically calculated.
        </Text>
      </View>
    </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F5F5F5',
  },
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
    paddingBottom: 40,
  },
  section: {
    padding: 16,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1A1A1A',
    marginBottom: 12,
  },
  locationCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 16,
  },
  loadingLocation: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 20,
  },
  loadingText: {
    marginLeft: 12,
    color: '#6B7280',
  },
  locationRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  locationInfo: {
    flex: 1,
    marginLeft: 12,
  },
  locationAddress: {
    fontSize: 16,
    color: '#1A1A1A',
    marginBottom: 4,
  },
  locationCoords: {
    fontSize: 12,
    color: '#9CA3AF',
  },
  refreshButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 16,
    paddingVertical: 8,
  },
  refreshText: {
    marginLeft: 4,
    color: COLORS.primary,
    fontWeight: '500',
  },
  errorLocation: {
    alignItems: 'center',
    padding: 20,
  },
  errorText: {
    color: '#6B7280',
    marginTop: 8,
  },
  retryButton: {
    marginTop: 12,
    paddingHorizontal: 20,
    paddingVertical: 8,
    backgroundColor: '#F3F4F6',
    borderRadius: 8,
  },
  retryText: {
    color: COLORS.primary,
    fontWeight: '500',
  },
  injuryCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 16,
  },
  injuryRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  injuryInfo: {
    flex: 1,
    marginRight: 16,
  },
  injuryLabel: {
    fontSize: 15,
    color: '#1A1A1A',
    fontWeight: '500',
  },
  injuryHint: {
    fontSize: 13,
    color: '#6B7280',
    marginTop: 4,
  },
  injuryWarning: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#EFF6FF',
    padding: 12,
    borderRadius: 8,
    marginTop: 16,
  },
  injuryWarningText: {
    flex: 1,
    marginLeft: 8,
    color: '#1E3A8A',
    fontSize: 14,
  },
  commentsInput: {
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 16,
    fontSize: 16,
    color: '#1A1A1A',
    minHeight: 120,
  },
  clockOutButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: COLORS.primary,
    marginHorizontal: 16,
    marginTop: 16,
    padding: 20,
    borderRadius: 12,
    gap: 12,
  },
  clockOutButtonDisabled: {
    backgroundColor: '#9CA3AF',
  },
  clockOutButtonText: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  footer: {
    padding: 16,
    paddingBottom: 32,
  },
  footerText: {
    fontSize: 13,
    color: '#6B7280',
    textAlign: 'center',
  },
});
