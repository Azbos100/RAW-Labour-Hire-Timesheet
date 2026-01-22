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
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Location from 'expo-location';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList, COLORS } from '../../App';
import { clockAPI, clientsAPI } from '../services/api';

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
  const [location, setLocation] = useState<Location.LocationObject | null>(null);
  const [address, setAddress] = useState<string>('');
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
      const response = await clientsAPI.getAllJobSites();
      setJobSites(response.data.job_sites || []);
    } catch (error) {
      console.error('Error fetching job sites:', error);
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
      console.error('Error getting location:', error);
      Alert.alert('Location Error', 'Unable to get your current location. Please try again.');
    } finally {
      setIsLoadingLocation(false);
    }
  };

  const handleClockIn = async () => {
    if (!location) {
      Alert.alert('Error', 'Unable to get your location. Please try again.');
      return;
    }

    if (!selectedJobSite) {
      Alert.alert('Error', 'Please select a job site');
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await clockAPI.clockIn({
        latitude: location.coords.latitude,
        longitude: location.coords.longitude,
        job_site_id: selectedJobSite.id,
        worked_as: workedAs || undefined,
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
    <ScrollView style={styles.container}>
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
          (!location || !selectedJobSite || isSubmitting) && styles.clockInButtonDisabled,
        ]}
        onPress={handleClockIn}
        disabled={!location || !selectedJobSite || isSubmitting}
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
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F5F5F5',
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
    backgroundColor: '#FEF2F2',
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
