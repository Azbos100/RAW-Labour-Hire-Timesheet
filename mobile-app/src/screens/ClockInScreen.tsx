/**
 * Clock In Screen
 * GPS-enabled clock in with automatic job site detection
 */

import React, { useState, useEffect, useRef } from 'react';
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
import api, { clockAPI, assignmentAPI } from '../services/api';
import { useAuth } from '../context/AuthContext';

type ClockInScreenProps = {
  navigation: NativeStackNavigationProp<RootStackParamList, 'ClockIn'>;
};

interface JobSite {
  id: number;
  name: string;
  address: string;
  client_name: string;
  latitude?: number;
  longitude?: number;
}

interface AssignedJob {
  job_site_id: number;
  job_site_name: string;
  job_site_address?: string;
  job_site_latitude?: number;
  job_site_longitude?: number;
}

// GPS matching threshold in kilometers
const GPS_MATCH_THRESHOLD_KM = 1;

// Calculate distance between two coordinates using Haversine formula
function calculateDistance(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number
): number {
  const R = 6371; // Earth's radius in kilometers
  const dLat = (lat2 - lat1) * (Math.PI / 180);
  const dLon = (lon2 - lon1) * (Math.PI / 180);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(lat1 * (Math.PI / 180)) *
      Math.cos(lat2 * (Math.PI / 180)) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c; // Distance in kilometers
}

export default function ClockInScreen({ navigation }: ClockInScreenProps) {
  const { user } = useAuth();
  const [location, setLocation] = useState<Location.LocationObject | null>(null);
  const [address, setAddress] = useState<string>('');
  const [manualAddress, setManualAddress] = useState<string>('');
  const [isEditingAddress, setIsEditingAddress] = useState(false);
  const [isLoadingLocation, setIsLoadingLocation] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [workedAs, setWorkedAs] = useState('');
  const [manualJobSiteAddress, setManualJobSiteAddress] = useState('');
  
  // Job site detection (hidden from user)
  const [allJobSites, setAllJobSites] = useState<JobSite[]>([]);
  const [assignedJob, setAssignedJob] = useState<AssignedJob | null>(null);
  const [detectedJobSite, setDetectedJobSite] = useState<JobSite | null>(null);
  const [detectionStatus, setDetectionStatus] = useState<'loading' | 'detected' | 'no_match'>('loading');
  
  // Track if we've done initial detection
  const hasDetectedRef = useRef(false);

  useEffect(() => {
    loadData();
  }, []);
  
  // Re-run detection when location changes
  useEffect(() => {
    if (location && allJobSites.length > 0 && !hasDetectedRef.current) {
      detectJobSite();
      hasDetectedRef.current = true;
    }
  }, [location, allJobSites]);

  const loadData = async () => {
    if (!user?.id) return;
    
    // Fetch assignment and all job sites in parallel
    const [assignmentResult, jobSitesResult] = await Promise.all([
      fetchAssignment(),
      fetchAllJobSites(),
    ]);
    
    // Start getting location
    getLocation();
  };
  
  const fetchAssignment = async (): Promise<AssignedJob | null> => {
    try {
      if (!user?.id) return null;
      const response = await assignmentAPI.getAssignment(user.id);
      const assignment = response.data.assignment;
      
      if (assignment && assignment.accepted === true) {
        const job: AssignedJob = {
          job_site_id: assignment.job_site_id,
          job_site_name: assignment.job_site_name,
          job_site_address: assignment.job_site_address || '',
          job_site_latitude: assignment.job_site_latitude,
          job_site_longitude: assignment.job_site_longitude,
        };
        setAssignedJob(job);
        return job;
      }
      return null;
    } catch (error: any) {
      console.warn('Error fetching assignment:', error);
      return null;
    }
  };
  
  const fetchAllJobSites = async (): Promise<JobSite[]> => {
    try {
      const response = await api.get('/clients/job-sites/all');
      const jobSitesData = response.data?.job_sites || response.data || [];
      const sites: JobSite[] = jobSitesData
        .filter((site: any) => site.is_active !== false && site.latitude && site.longitude)
        .map((site: any) => ({
          id: site.id,
          name: site.name,
          address: site.address || '',
          client_name: site.client_name || '',
          latitude: site.latitude,
          longitude: site.longitude,
        }));
      setAllJobSites(sites);
      return sites;
    } catch (error: any) {
      console.warn('Error fetching job sites:', error);
      return [];
    }
  };
  
  const detectJobSite = () => {
    if (!location) {
      setDetectionStatus('no_match');
      return;
    }
    
    const userLat = location.coords.latitude;
    const userLon = location.coords.longitude;
    
    // Priority 1: Check if near assigned job site
    if (assignedJob && assignedJob.job_site_latitude && assignedJob.job_site_longitude) {
      const distToAssigned = calculateDistance(
        userLat, userLon,
        assignedJob.job_site_latitude, assignedJob.job_site_longitude
      );
      
      if (distToAssigned <= GPS_MATCH_THRESHOLD_KM) {
        // Near assigned job - use it
        setDetectedJobSite({
          id: assignedJob.job_site_id,
          name: assignedJob.job_site_name,
          address: assignedJob.job_site_address || '',
          client_name: '',
          latitude: assignedJob.job_site_latitude,
          longitude: assignedJob.job_site_longitude,
        });
        setDetectionStatus('detected');
        return;
      }
    }
    
    // Priority 2: Find nearest job site within threshold
    let nearestSite: JobSite | null = null;
    let nearestDistance = Infinity;
    
    for (const site of allJobSites) {
      if (site.latitude && site.longitude) {
        const dist = calculateDistance(userLat, userLon, site.latitude, site.longitude);
        if (dist <= GPS_MATCH_THRESHOLD_KM && dist < nearestDistance) {
          nearestDistance = dist;
          nearestSite = site;
        }
      }
    }
    
    if (nearestSite) {
      setDetectedJobSite(nearestSite);
      setDetectionStatus('detected');
    } else {
      // No match - but still allow clock in
      setDetectedJobSite(null);
      setDetectionStatus('no_match');
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
        setDetectionStatus('no_match');
        return;
      }

      const loc = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.High,
      });
      setLocation(loc);

      // Reverse geocode to get address
      const [addressResult] = await Location.reverseGeocodeAsync({
        latitude: loc.coords.latitude,
        longitude: loc.coords.longitude,
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
      setDetectionStatus('no_match');
    } finally {
      setIsLoadingLocation(false);
    }
  };
  
  const refreshLocation = async () => {
    setIsLoadingLocation(true);
    hasDetectedRef.current = false;
    setDetectionStatus('loading');
    await getLocation();
    // Detection will re-run via useEffect when location updates
  };

  const handleClockIn = async () => {
    // Allow clock in with manual address even if GPS failed
    const hasLocation = location !== null;
    const hasManualAddress = isEditingAddress && manualAddress.trim().length > 0;
    
    if (!hasLocation && !hasManualAddress) {
      Alert.alert('Error', 'Please either enable GPS or enter an address manually.');
      return;
    }

    // Proceed with clock in - job site is optional
    submitClockIn();
  };

  const submitClockIn = async () => {
    // Use manual address if edited, otherwise use GPS address
    const finalAddress = isEditingAddress ? manualAddress : address;
    
    // Use manual job site address if no job site detected and user entered one
    const jobSiteAddress = !detectedJobSite && manualJobSiteAddress.trim() 
      ? manualJobSiteAddress.trim() 
      : undefined;

    setIsSubmitting(true);
    try {
      const response = await clockAPI.clockIn({
        latitude: location?.coords.latitude || 0,
        longitude: location?.coords.longitude || 0,
        address: finalAddress,
        job_site_id: detectedJobSite?.id || undefined,
        job_site_address: jobSiteAddress,
        worked_as: workedAs || undefined,
        user_id: user?.id,
      });

      const locationName = detectedJobSite 
        ? detectedJobSite.name 
        : (jobSiteAddress || 'your current location');
      Alert.alert(
        'Clocked In!',
        `You are now clocked in at ${locationName}\n\nDocket #${response.data.docket_number}`,
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

              <TouchableOpacity style={styles.refreshButton} onPress={refreshLocation}>
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

      {/* Detected Job Site (Read-only) */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Job Site</Text>
        <View style={styles.detectedSiteCard}>
          {detectionStatus === 'loading' || isLoadingLocation ? (
            <View style={styles.detectingContainer}>
              <ActivityIndicator color={COLORS.primary} size="small" />
              <Text style={styles.detectingText}>Detecting job site from GPS...</Text>
            </View>
          ) : detectionStatus === 'detected' && detectedJobSite ? (
            <View style={styles.detectedContainer}>
              <View style={styles.detectedIconContainer}>
                <Ionicons name="checkmark-circle" size={24} color="#10B981" />
              </View>
              <View style={styles.detectedInfo}>
                <Text style={styles.detectedLabel}>Detected Location:</Text>
                <Text style={styles.detectedName}>{detectedJobSite.name}</Text>
                {detectedJobSite.address ? (
                  <Text style={styles.detectedAddress}>{detectedJobSite.address}</Text>
                ) : null}
              </View>
            </View>
          ) : (
            <View style={styles.noMatchContainer}>
              <View style={styles.noMatchRow}>
                <View style={styles.noMatchIconContainer}>
                  <Ionicons name="location" size={24} color="#F59E0B" />
                </View>
                <View style={styles.noMatchInfo}>
                  <Text style={styles.noMatchLabel}>No Job Site Detected</Text>
                  <Text style={styles.noMatchText}>
                    Your GPS location will be saved.
                  </Text>
                </View>
              </View>
              <View style={styles.manualJobSiteSection}>
                <Text style={styles.manualJobSiteLabel}>Job site address (optional):</Text>
                <TextInput
                  style={styles.manualJobSiteInput}
                  placeholder="Enter job site address if known..."
                  placeholderTextColor="#9CA3AF"
                  value={manualJobSiteAddress}
                  onChangeText={setManualJobSiteAddress}
                  multiline
                  numberOfLines={2}
                />
              </View>
            </View>
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
          ((!location && !manualAddress.trim()) || isSubmitting || isLoadingLocation) && styles.clockInButtonDisabled,
        ]}
        onPress={handleClockIn}
        disabled={(!location && !manualAddress.trim()) || isSubmitting || isLoadingLocation}
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
  // Detected Job Site Styles
  detectedSiteCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 16,
  },
  detectingContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 12,
  },
  detectingText: {
    marginLeft: 12,
    color: '#6B7280',
    fontSize: 14,
  },
  detectedContainer: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  detectedIconContainer: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#ECFDF5',
    alignItems: 'center',
    justifyContent: 'center',
  },
  detectedInfo: {
    flex: 1,
    marginLeft: 12,
  },
  detectedLabel: {
    fontSize: 12,
    color: '#6B7280',
    marginBottom: 2,
  },
  detectedName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1A1A1A',
  },
  detectedAddress: {
    fontSize: 13,
    color: '#6B7280',
    marginTop: 4,
  },
  noMatchContainer: {
    flexDirection: 'column',
  },
  noMatchRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  noMatchIconContainer: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#FEF3C7',
    alignItems: 'center',
    justifyContent: 'center',
  },
  noMatchInfo: {
    flex: 1,
    marginLeft: 12,
  },
  noMatchLabel: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1A1A1A',
  },
  noMatchText: {
    fontSize: 13,
    color: '#6B7280',
    marginTop: 4,
  },
  manualJobSiteSection: {
    marginTop: 16,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: '#E5E7EB',
  },
  manualJobSiteLabel: {
    fontSize: 14,
    fontWeight: '500',
    color: '#374151',
    marginBottom: 8,
  },
  manualJobSiteInput: {
    backgroundColor: '#F9FAFB',
    borderWidth: 1,
    borderColor: '#E5E7EB',
    borderRadius: 8,
    padding: 12,
    fontSize: 15,
    color: '#1A1A1A',
    minHeight: 50,
    textAlignVertical: 'top',
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
