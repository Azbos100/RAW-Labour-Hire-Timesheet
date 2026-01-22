/**
 * Dashboard Screen
 * Main screen with clock in/out status and quick actions
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useFocusEffect } from '@react-navigation/native';
import { RootStackParamList, COLORS } from '../../App';
import { useAuth } from '../context/AuthContext';
import { clockAPI } from '../services/api';

type DashboardScreenProps = {
  navigation: NativeStackNavigationProp<RootStackParamList>;
};

interface ClockStatus {
  is_clocked_in: boolean;
  clock_in_time?: string;
  clock_in_address?: string;
  hours_worked_today: number;
}

export default function DashboardScreen({ navigation }: DashboardScreenProps) {
  const { user } = useAuth();
  const [clockStatus, setClockStatus] = useState<ClockStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchClockStatus = async () => {
    try {
      const response = await clockAPI.getStatus();
      setClockStatus(response.data);
    } catch (error) {
      console.error('Error fetching clock status:', error);
      // Set default status if API fails
      setClockStatus({
        is_clocked_in: false,
        hours_worked_today: 0,
      });
    } finally {
      setIsLoading(false);
      setRefreshing(false);
    }
  };

  // Fetch on screen focus
  useFocusEffect(
    useCallback(() => {
      fetchClockStatus();
    }, [])
  );

  const onRefresh = () => {
    setRefreshing(true);
    fetchClockStatus();
  };

  const formatTime = (isoString?: string) => {
    if (!isoString) return '--:--';
    const date = new Date(isoString);
    return date.toLocaleTimeString('en-AU', {
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatHours = (hours: number) => {
    const h = Math.floor(hours);
    const m = Math.round((hours - h) * 60);
    return `${h}h ${m}m`;
  };

  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good morning';
    if (hour < 18) return 'Good afternoon';
    return 'Good evening';
  };

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={COLORS.primary} />
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
      }
    >
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.greeting}>{getGreeting()},</Text>
        <Text style={styles.userName}>{user?.first_name} {user?.surname}</Text>
        <Text style={styles.date}>
          {new Date().toLocaleDateString('en-AU', {
            weekday: 'long',
            day: 'numeric',
            month: 'long',
            year: 'numeric',
          })}
        </Text>
      </View>

      {/* Clock Status Card */}
      <View style={styles.statusCard}>
        <View style={styles.statusHeader}>
          <View style={[
            styles.statusIndicator,
            clockStatus?.is_clocked_in ? styles.statusActive : styles.statusInactive
          ]} />
          <Text style={styles.statusText}>
            {clockStatus?.is_clocked_in ? 'Clocked In' : 'Clocked Out'}
          </Text>
        </View>

        {clockStatus?.is_clocked_in && (
          <View style={styles.clockDetails}>
            <View style={styles.detailRow}>
              <Ionicons name="time-outline" size={20} color="#9CA3AF" />
              <Text style={styles.detailText}>
                Started at {formatTime(clockStatus.clock_in_time)}
              </Text>
            </View>
            {clockStatus.clock_in_address && (
              <View style={styles.detailRow}>
                <Ionicons name="location-outline" size={20} color="#9CA3AF" />
                <Text style={styles.detailText} numberOfLines={2}>
                  {clockStatus.clock_in_address}
                </Text>
              </View>
            )}
          </View>
        )}

        <View style={styles.hoursBox}>
          <Text style={styles.hoursLabel}>Hours Today</Text>
          <Text style={styles.hoursValue}>
            {formatHours(clockStatus?.hours_worked_today || 0)}
          </Text>
        </View>
      </View>

      {/* Clock Action Button */}
      <TouchableOpacity
        style={[
          styles.clockButton,
          clockStatus?.is_clocked_in ? styles.clockOutButton : styles.clockInButton
        ]}
        onPress={() => navigation.navigate(
          clockStatus?.is_clocked_in ? 'ClockOut' : 'ClockIn'
        )}
      >
        <Ionicons
          name={clockStatus?.is_clocked_in ? 'log-out-outline' : 'log-in-outline'}
          size={32}
          color="#FFFFFF"
        />
        <Text style={styles.clockButtonText}>
          {clockStatus?.is_clocked_in ? 'CLOCK OUT' : 'CLOCK IN'}
        </Text>
      </TouchableOpacity>

      {/* Quick Stats */}
      <View style={styles.statsContainer}>
        <Text style={styles.sectionTitle}>This Week</Text>
        <View style={styles.statsRow}>
          <View style={styles.statBox}>
            <Ionicons name="calendar-outline" size={24} color={COLORS.primary} />
            <Text style={styles.statValue}>0</Text>
            <Text style={styles.statLabel}>Days Worked</Text>
          </View>
          <View style={styles.statBox}>
            <Ionicons name="time-outline" size={24} color={COLORS.primary} />
            <Text style={styles.statValue}>0h</Text>
            <Text style={styles.statLabel}>Total Hours</Text>
          </View>
          <View style={styles.statBox}>
            <Ionicons name="add-circle-outline" size={24} color="#F59E0B" />
            <Text style={styles.statValue}>0h</Text>
            <Text style={styles.statLabel}>Overtime</Text>
          </View>
        </View>
      </View>

      {/* Help Text */}
      <View style={styles.helpBox}>
        <Ionicons name="information-circle-outline" size={20} color="#6B7280" />
        <Text style={styles.helpText}>
          Remember to clock in when you arrive at the job site and clock out when you leave. 
          Your GPS location will be recorded automatically.
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
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#F5F5F5',
  },
  header: {
    backgroundColor: '#E31837',
    padding: 24,
    paddingTop: 16,
    paddingBottom: 32,
  },
  greeting: {
    fontSize: 16,
    color: 'rgba(255, 255, 255, 0.8)',
  },
  userName: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginTop: 4,
  },
  date: {
    fontSize: 14,
    color: 'rgba(255, 255, 255, 0.7)',
    marginTop: 8,
  },
  statusCard: {
    backgroundColor: '#FFFFFF',
    marginHorizontal: 16,
    marginTop: -16,
    borderRadius: 12,
    padding: 20,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 4,
  },
  statusHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  statusIndicator: {
    width: 12,
    height: 12,
    borderRadius: 6,
    marginRight: 8,
  },
  statusActive: {
    backgroundColor: '#10B981',
  },
  statusInactive: {
    backgroundColor: '#6B7280',
  },
  statusText: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1A1A1A',
  },
  clockDetails: {
    marginBottom: 16,
    paddingBottom: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#E5E7EB',
  },
  detailRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 8,
  },
  detailText: {
    fontSize: 14,
    color: '#6B7280',
    marginLeft: 8,
    flex: 1,
  },
  hoursBox: {
    alignItems: 'center',
  },
  hoursLabel: {
    fontSize: 14,
    color: '#6B7280',
    marginBottom: 4,
  },
  hoursValue: {
    fontSize: 36,
    fontWeight: 'bold',
    color: '#1A1A1A',
  },
  clockButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginHorizontal: 16,
    marginTop: 24,
    padding: 20,
    borderRadius: 12,
    gap: 12,
  },
  clockInButton: {
    backgroundColor: '#10B981',
  },
  clockOutButton: {
    backgroundColor: '#E31837',
  },
  clockButtonText: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  statsContainer: {
    marginTop: 32,
    paddingHorizontal: 16,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1A1A1A',
    marginBottom: 16,
  },
  statsRow: {
    flexDirection: 'row',
    gap: 12,
  },
  statBox: {
    flex: 1,
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  statValue: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#1A1A1A',
    marginTop: 8,
  },
  statLabel: {
    fontSize: 12,
    color: '#6B7280',
    marginTop: 4,
  },
  helpBox: {
    flexDirection: 'row',
    backgroundColor: '#F3F4F6',
    marginHorizontal: 16,
    marginTop: 24,
    marginBottom: 32,
    padding: 16,
    borderRadius: 8,
    gap: 12,
  },
  helpText: {
    flex: 1,
    fontSize: 13,
    color: '#6B7280',
    lineHeight: 18,
  },
});
