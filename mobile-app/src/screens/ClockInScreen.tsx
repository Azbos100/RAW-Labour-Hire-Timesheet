/**
 * Clock In Screen
 * GPS-enabled clock in with job site selection
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
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Location from 'expo-location';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../../App';
import { COLORS } from '../constants/colors';
import api, { clockAPI, clientsAPI } from '../services/api';
import { useAuth } from '../context/AuthContext';

type ClockInScreenProps = {
  navigation: NativeStackNavigationProp<RootStackParamList, 'ClockIn'>;
};

interface JobSite {
  id: number;
  name: string;
  address: string;
  client_name: string;
}

export default function ClockInScreen({ navigation }: ClockInScreenProps) {
  const { user } = useAuth();
  const [location, setLocation] = useState<Location.LocationObject | null>(null);
  const [address, setAddress] = useState<string>('');
  const [manualAddress, setManualAddress] = useState<string>('');
  const [isEditingAddress, setIsEditingAddress] = useState(false);
  const [isLoadingLocation, setIsLoadingLocation] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [jobSites, setJobSites] = useState<JobSite[]>([]);
  const [selectedJobSite, setSelectedJobSite] = useState<JobSite | null>(null);
  const [workedAs, setWorkedAs] = useState('');

  useEffect(() => {
    getLocation();
    fetchJobSites();
  }, []);

  const fetchJobSites = async () => {
    try {
      // Debug: Check what headers are being sent
      const debugResponse = await api.get('/debug/headers');
      console.log('DEBUG HEADERS:', JSON.stringify(debugResponse.data, null, 2));
      
      const response = await clientsAPI.getAllJobSites();
      setJobSites(response.data.job_sites || []);
    } catch (error: any) {
      console.warn('Error fetching job sites:', error);
      const status = error.response?.status;
      const detail = error.response?.data?.detail || error.message || 'Unknown error';
      Alert.alert(
        'Job Sites Unavailable',
        `Unable to load job sites.\n\nError: ${status ? `${status} - ` : ''}${detail}`
      );
    }
  };

  const getLocation = async () => {
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert(
          'Permission Required',
          'Location permission is required to clock in. Please enable it in settings.'
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
      console.warn('Error getting location:', error);
      Alert.alert('Location Error', 'Unable to get your current location. Please try again.');
    } finally {
      setIsLoadingLocation(false);
    }
  };

  const handleClockIn = async () => {
    // Allow clock in with manual address even if GPS failed
    const hasLocation = location !== null;
    const hasManualAddress = isEditingAddress && manualAddress.trim().length > 0;
    
    if (!hasLocation && !hasManualAddress) {
      Alert.alert('Error', 'Please either enable GPS or enter an address manually.');
      return;
    }

    if (!selectedJobSite) {
      Alert.alert('Error', 'Please select a job site');
      return;
    }

    // Use manual address if edited, otherwise use GPS address
    const finalAddress = isEditingAddress ? manualAddress : address;

    setIsSubmitting(true);
    try {
      const response = await clockAPI.clockIn({
        latitude: location?.coords.latitude || 0,
        longitude: location?.coords.longitude || 0,
        address: finalAddress,
        job_site_id: selectedJobSite.id,
        worked_as: workedAs || undefined,
        user_id: user?.id,
      });

      Alert.alert(
        'Clocked In!',
        `You are now clocked in at ${selectedJobSite.name}\n\nDocket #${response.data.docket_number}`,
        [{ text: 'OK', onPress: () => navigation.goBack() }]
      );
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Failed to clock in. Please try again.';
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
              {/* GPS Coordinates - always shown */}
              <View style={styles.gpsRow}>
                <Ionicons name="navigate" size={18} color="#10B981" />
                <Text style={styles.gpsText}>GPS Captured</Text>
                <Text style={styles.locationCoords}>
                  ({location.coords.latitude.toFixed(5)}, {location.coords.longitude.toFixed(5)})
                </Text>
              </View>

              {/* Address Section - Editable */}
              <View style={styles.addressSection}>
                <View style={styles.addressHeader}>
                  <Text style={styles.addressLabel}>Address:</Text>
                  <TouchableOpacity 
                    onPress={() => {
                      setIsEditingAddress(!isEditingAddress);
                      if (!isEditingAddress) {
                        setManualAddress(address);
                      }
                    }}
                  >
                    <Text style={styles.editAddressLink}>
                      {isEditingAddress ? 'Use GPS Address' : 'Edit Address'}
                    </Text>
                  </TouchableOpacity>
                </View>

                {isEditingAddress ? (
                  <TextInput
                    style={styles.addressInput}
                    placeholder="Type your address here..."
                    placeholderTextColor="#9CA3AF"
                    value={manualAddress}
                    onChangeText={setManualAddress}
                    multiline
                    numberOfLines={2}
                  />
                ) : (
                  <Text style={styles.locationAddress}>{address || 'Address detected'}</Text>
                )}
              </View>

              <TouchableOpacity style={styles.refreshButton} onPress={getLocation}>
                <Ionicons name="refresh" size={20} color={COLORS.primary} />
                <Text style={styles.refreshText}>Refresh GPS</Text>
              </TouchableOpacity>
            </>
          ) : (
            <View style={styles.errorLocation}>
              <Ionicons name="warning" size={24} color="#F59E0B" />
              <Text style={styles.errorText}>Unable to get GPS location</Text>
              
              {/* Allow manual address entry even without GPS */}
              <View style={styles.manualEntrySection}>
                <Text style={styles.manualEntryLabel}>Enter address manually:</Text>
                <TextInput
                  style={styles.addressInput}
                  placeholder="Type your work address..."
                  placeholderTextColor="#9CA3AF"
                  value={manualAddress}
                  onChangeText={(text) => {
                    setManualAddress(text);
                    setIsEditingAddress(true);
                  }}
                  multiline
                  numberOfLines={2}
                />
              </View>
              
              <TouchableOpacity style={styles.retryButton} onPress={getLocation}>
                <Text style={styles.retryText}>Try GPS Again</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>
      </View>

      {/* Job Site Selection */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Select Job Site *</Text>
        <View style={styles.jobSiteList}>
          {jobSites.length === 0 ? (
            <Text style={styles.noJobSites}>No job sites available</Text>
          ) : (
            jobSites.map((site) => (
              <TouchableOpacity
                key={site.id}
                style={[
                  styles.jobSiteItem,
                  selectedJobSite?.id === site.id && styles.jobSiteItemSelected,
                ]}
                onPress={() => setSelectedJobSite(site)}
              >
                <View style={styles.jobSiteInfo}>
                  <Text style={styles.jobSiteName}>{site.name}</Text>
                  <Text style={styles.jobSiteClient}>{site.client_name}</Text>
                  <Text style={styles.jobSiteAddress}>{site.address}</Text>
                </View>
                {selectedJobSite?.id === site.id && (
                  <Ionicons name="checkmark-circle" size={24} color={COLORS.primary} />
                )}
              </TouchableOpacity>
            ))
          )}
        </View>
      </View>

      {/* Worked As */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Worked As (Role)</Text>
        <TextInput
          style={styles.input}
          placeholder="e.g. Labourer, Carpenter, Electrician"
          placeholderTextColor="#9CA3AF"
          value={workedAs}
          onChangeText={setWorkedAs}
        />
      </View>

      {/* Clock In Button */}
      <TouchableOpacity
        style={[
          styles.clockInButton,
          ((!location && !manualAddress.trim()) || !selectedJobSite || isSubmitting) && styles.clockInButtonDisabled,
        ]}
        onPress={handleClockIn}
        disabled={(!location && !manualAddress.trim()) || !selectedJobSite || isSubmitting}
      >
        {isSubmitting ? (
          <ActivityIndicator color="#FFFFFF" />
        ) : (
          <>
            <Ionicons name="log-in-outline" size={24} color="#FFFFFF" />
            <Text style={styles.clockInButtonText}>CLOCK IN</Text>
          </>
        )}
      </TouchableOpacity>

      <View style={styles.footer}>
        <Text style={styles.footerText}>
          Your GPS location and time will be recorded for this clock-in.
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
    fontSize: 11,
    color: '#9CA3AF',
    marginLeft: 4,
  },
  gpsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#ECFDF5',
    padding: 10,
    borderRadius: 8,
    marginBottom: 12,
  },
  gpsText: {
    fontSize: 14,
    color: '#10B981',
    fontWeight: '600',
    marginLeft: 6,
    flex: 1,
  },
  addressSection: {
    marginTop: 4,
  },
  addressHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  addressLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: '#374151',
  },
  editAddressLink: {
    fontSize: 14,
    color: COLORS.primary,
    fontWeight: '500',
  },
  addressInput: {
    backgroundColor: '#F9FAFB',
    borderWidth: 1,
    borderColor: '#E5E7EB',
    borderRadius: 8,
    padding: 12,
    fontSize: 16,
    color: '#1A1A1A',
    minHeight: 60,
    textAlignVertical: 'top',
  },
  manualEntrySection: {
    width: '100%',
    marginTop: 16,
  },
  manualEntryLabel: {
    fontSize: 14,
    color: '#374151',
    marginBottom: 8,
    fontWeight: '500',
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
  jobSiteList: {
    gap: 8,
  },
  noJobSites: {
    color: '#6B7280',
    textAlign: 'center',
    padding: 20,
  },
  jobSiteItem: {
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 16,
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: 'transparent',
  },
  jobSiteItemSelected: {
    borderColor: COLORS.primary,
    backgroundColor: '#EFF6FF',
  },
  jobSiteInfo: {
    flex: 1,
  },
  jobSiteName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1A1A1A',
  },
  jobSiteClient: {
    fontSize: 14,
    color: COLORS.primary,
    marginTop: 2,
  },
  jobSiteAddress: {
    fontSize: 13,
    color: '#6B7280',
    marginTop: 4,
  },
  input: {
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 16,
    fontSize: 16,
    color: '#1A1A1A',
  },
  clockInButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#10B981',
    marginHorizontal: 16,
    marginTop: 16,
    padding: 20,
    borderRadius: 12,
    gap: 12,
  },
  clockInButtonDisabled: {
    backgroundColor: '#9CA3AF',
  },
  clockInButtonText: {
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
