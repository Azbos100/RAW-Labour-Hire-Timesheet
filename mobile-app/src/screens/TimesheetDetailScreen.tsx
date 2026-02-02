/**
 * Timesheet Detail Screen
 * View and submit individual timesheet
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
  Modal,
  KeyboardAvoidingView,
  Platform,
  Dimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RouteProp } from '@react-navigation/native';
import SignatureCanvas from 'react-native-signature-canvas';
import { RootStackParamList } from '../../App';
import { COLORS } from '../constants/colors';
import { timesheetsAPI } from '../services/api';

type TimesheetDetailScreenProps = {
  navigation: NativeStackNavigationProp<RootStackParamList, 'TimesheetDetail'>;
  route: RouteProp<RootStackParamList, 'TimesheetDetail'>;
};

interface TimesheetEntry {
  id: number;
  day_of_week: string;
  entry_date: string;
  time_start?: string;
  time_finish?: string;
  clock_in_time?: string;
  clock_out_time?: string;
  ordinary_hours: number;
  overtime_hours: number;
  total_hours: number;
  worked_as?: string;
  comments?: string;
  clock_in_address?: string;
  clock_out_address?: string;
  entry_status?: string;
  host_company_name?: string;
  supervisor_name?: string;
}

interface TimesheetData {
  id: number;
  docket_number: string;
  week_starting: string;
  week_ending: string;
  status: string;
  total_ordinary_hours: number;
  total_overtime_hours: number;
  total_hours: number;
  entries: TimesheetEntry[];
}

export default function TimesheetDetailScreen({ navigation, route }: TimesheetDetailScreenProps) {
  const { timesheetId } = route.params;
  const [timesheet, setTimesheet] = useState<TimesheetData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [showSubmitModal, setShowSubmitModal] = useState(false);
  const [showSignatureModal, setShowSignatureModal] = useState(false);
  const [selectedEntry, setSelectedEntry] = useState<TimesheetEntry | null>(null);
  const [companyName, setCompanyName] = useState('');
  const [supervisorName, setSupervisorName] = useState('');
  const [supervisorContact, setSupervisorContact] = useState('');
  const [supervisorSignature, setSupervisorSignature] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const signatureRef = useRef<SignatureCanvas>(null);

  useEffect(() => {
    fetchTimesheet();
  }, [timesheetId]);

  const fetchTimesheet = async () => {
    try {
      const response = await timesheetsAPI.getById(timesheetId);
      setTimesheet(response.data);
    } catch (error) {
      console.error('Error fetching timesheet:', error);
      Alert.alert('Error', 'Unable to load timesheet');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (!companyName || !supervisorName || !supervisorContact) {
      Alert.alert('Error', 'Please fill in all fields');
      return;
    }
    if (!supervisorSignature) {
      Alert.alert('Error', 'Please get supervisor signature');
      return;
    }

    setIsSubmitting(true);
    try {
      if (selectedEntry) {
        // Submit individual entry
        await timesheetsAPI.submitEntry(selectedEntry.id, {
          company_name: companyName,
          supervisor_name: supervisorName,
          supervisor_contact: supervisorContact,
          supervisor_signature: supervisorSignature,
        });
        Alert.alert('Success', `Entry for ${selectedEntry.day_of_week} submitted for approval`);
      } else {
        // Submit entire timesheet
        await timesheetsAPI.submit(timesheetId, {
          company_name: companyName,
          supervisor_name: supervisorName,
          supervisor_contact: supervisorContact,
          supervisor_signature: supervisorSignature,
        });
        Alert.alert('Success', 'Timesheet submitted for approval');
      }
      setShowSubmitModal(false);
      // Reset form
      setSelectedEntry(null);
      setCompanyName('');
      setSupervisorName('');
      setSupervisorContact('');
      setSupervisorSignature(null);
      fetchTimesheet();
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to submit');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSignature = (signature: string) => {
    setSupervisorSignature(signature);
    setShowSignatureModal(false);
    // Re-open submit modal after capturing signature
    setTimeout(() => setShowSubmitModal(true), 300);
  };

  const handleClearSignature = () => {
    signatureRef.current?.clearSignature();
  };

  const handleConfirmSignature = () => {
    signatureRef.current?.readSignature();
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-AU', {
      day: 'numeric',
      month: 'short',
    });
  };

  const formatTime = (timeString?: string) => {
    if (!timeString) return '--:--';
    // Handle both time format (HH:MM:SS) and datetime format
    if (timeString.includes('T')) {
      // ISO datetime format - ensure UTC is properly handled
      let dateString = timeString;
      if (!timeString.endsWith('Z') && !timeString.includes('+') && !timeString.includes('-', 10)) {
        dateString = timeString + 'Z';
      }
      const date = new Date(dateString);
      return date.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', hour12: true });
    }
    // Time only format - take first 5 chars (HH:MM)
    return timeString.substring(0, 5);
  };

  const formatHoursMinutes = (hours: number) => {
    const h = Math.floor(hours);
    const m = Math.round((hours - h) * 60);
    if (h === 0) return `${m}m`;
    return `${h}h ${m}m`;
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'approved':
        return '#10B981';
      case 'submitted':
        return '#F59E0B';
      case 'rejected':
        return '#6B7280';
      default:
        return '#6B7280';
    }
  };

  const getEntryStatusColor = (status?: string) => {
    switch (status) {
      case 'approved':
        return '#10B981';
      case 'submitted':
        return '#F59E0B';
      default:
        return COLORS.primary;
    }
  };

  const openEntrySubmit = (entry: TimesheetEntry) => {
    if (entry.entry_status === 'submitted' || entry.entry_status === 'approved') {
      Alert.alert('Already Submitted', `This entry was submitted to ${entry.host_company_name || 'N/A'}`);
      return;
    }
    setSelectedEntry(entry);
    setShowSubmitModal(true);
  };

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={COLORS.primary} />
      </View>
    );
  }

  if (!timesheet) {
    return (
      <View style={styles.errorContainer}>
        <Text style={styles.errorText}>Timesheet not found</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <ScrollView>
        {/* Header */}
        <View style={styles.header}>
          <View style={styles.headerRow}>
            <View style={styles.docketBadge}>
              <Text style={styles.docketText}>#{timesheet.docket_number}</Text>
            </View>
            <View style={[
              styles.statusBadge,
              { backgroundColor: getStatusColor(timesheet.status) + '20' }
            ]}>
              <Text style={[styles.statusText, { color: getStatusColor(timesheet.status) }]}>
                {timesheet.status.charAt(0).toUpperCase() + timesheet.status.slice(1)}
              </Text>
            </View>
          </View>
          <Text style={styles.weekRange}>
            {formatDate(timesheet.week_starting)} - {formatDate(timesheet.week_ending)}
          </Text>
        </View>

        {/* Summary */}
        <View style={styles.summaryCard}>
          <View style={styles.summaryItem}>
            <Text style={styles.summaryLabel}>Ordinary</Text>
            <Text style={styles.summaryValue}>{timesheet.total_ordinary_hours.toFixed(1)}h</Text>
          </View>
          <View style={styles.summaryDivider} />
          <View style={styles.summaryItem}>
            <Text style={styles.summaryLabel}>Overtime</Text>
            <Text style={styles.summaryValue}>{timesheet.total_overtime_hours.toFixed(1)}h</Text>
          </View>
          <View style={styles.summaryDivider} />
          <View style={styles.summaryItem}>
            <Text style={styles.summaryLabel}>Total</Text>
            <Text style={[styles.summaryValue, styles.summaryTotal]}>
              {timesheet.total_hours.toFixed(1)}h
            </Text>
          </View>
        </View>

        {/* Entries */}
        <View style={styles.entriesSection}>
          <Text style={styles.sectionTitle}>Daily Entries</Text>
          {timesheet.entries.length === 0 ? (
            <View style={styles.noEntries}>
              <Text style={styles.noEntriesText}>No entries yet</Text>
            </View>
          ) : (
            timesheet.entries.map((entry) => (
              <TouchableOpacity 
                key={entry.id} 
                style={styles.entryCard}
                activeOpacity={0.7}
                onPress={() => openEntrySubmit(entry)}
              >
                <View style={styles.entryHeader}>
                  <Text style={styles.entryDay}>{entry.day_of_week}</Text>
                  <View style={styles.entryHeaderRight}>
                    {entry.entry_status === 'submitted' || entry.entry_status === 'approved' ? (
                      <View style={[styles.entryStatusBadge, { backgroundColor: getEntryStatusColor(entry.entry_status) + '20' }]}>
                        <Text style={[styles.entryStatusText, { color: getEntryStatusColor(entry.entry_status) }]}>
                          {entry.entry_status === 'submitted' ? 'Pending' : 'Approved'}
                        </Text>
                      </View>
                    ) : (
                      <View style={styles.submitEntryHint}>
                        <Text style={styles.submitEntryHintText}>Tap to Submit</Text>
                        <Ionicons name="chevron-forward" size={14} color={COLORS.primary} />
                      </View>
                    )}
                    <Text style={styles.entryDate}>{formatDate(entry.entry_date)}</Text>
                  </View>
                </View>
                <View style={styles.entryDetails}>
                  <View style={styles.entryTimeRow}>
                    <Ionicons name="time-outline" size={16} color="#6B7280" />
                    <Text style={styles.entryTime}>
                      {formatTime(entry.clock_in_time || entry.time_start)} - {formatTime(entry.clock_out_time || entry.time_finish)}
                    </Text>
                  </View>
                  <View style={styles.entryHours}>
                    <Text style={styles.entryHoursText}>{formatHoursMinutes(entry.total_hours)}</Text>
                  </View>
                </View>
                {entry.worked_as && (
                  <Text style={styles.entryWorkedAs}>Worked as: {entry.worked_as}</Text>
                )}
                {entry.entry_status === 'submitted' && entry.host_company_name && (
                  <Text style={styles.entryCompany}>Company: {entry.host_company_name}</Text>
                )}
                {entry.clock_in_address && (
                  <View style={styles.entryLocation}>
                    <Ionicons name="location-outline" size={14} color="#9CA3AF" />
                    <Text style={styles.entryLocationText} numberOfLines={1}>
                      {entry.clock_in_address}
                    </Text>
                  </View>
                )}
              </TouchableOpacity>
            ))
          )}
        </View>
      </ScrollView>

      {/* Submit Button (only for draft timesheets) */}
      {timesheet.status === 'draft' && (
        <View style={styles.footer}>
          <TouchableOpacity
            style={styles.submitButton}
            onPress={() => setShowSubmitModal(true)}
          >
            <Ionicons name="send" size={20} color="#FFFFFF" />
            <Text style={styles.submitButtonText}>Submit for Approval</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Submit Modal */}
      <Modal
        visible={showSubmitModal}
        animationType="slide"
        transparent
        onRequestClose={() => setShowSubmitModal(false)}
      >
        <KeyboardAvoidingView 
          style={styles.modalOverlay}
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        >
          <ScrollView style={styles.modalScroll} keyboardShouldPersistTaps="handled">
            <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>
              {selectedEntry ? `Submit ${selectedEntry.day_of_week}` : 'Submit Timesheet'}
            </Text>
            <Text style={styles.modalSubtitle}>
              {selectedEntry 
                ? `Enter supervisor details for ${formatDate(selectedEntry.entry_date)}`
                : 'Enter supervisor details for approval'}
            </Text>

              <Text style={styles.inputLabel}>Company</Text>
              <TextInput
                style={styles.input}
                placeholder="Enter host company name"
                placeholderTextColor="#9CA3AF"
                value={companyName}
                onChangeText={setCompanyName}
              />

              <Text style={styles.inputLabel}>Supervisor Name</Text>
              <TextInput
                style={styles.input}
                placeholder="Enter supervisor's name"
                placeholderTextColor="#9CA3AF"
                value={supervisorName}
                onChangeText={setSupervisorName}
              />

              <Text style={styles.inputLabel}>Contact Number</Text>
              <TextInput
                style={styles.input}
                placeholder="Enter contact number"
                placeholderTextColor="#9CA3AF"
                value={supervisorContact}
                onChangeText={setSupervisorContact}
                keyboardType="phone-pad"
              />

              <Text style={styles.inputLabel}>Supervisor Signature</Text>
              {supervisorSignature ? (
                <View style={styles.signaturePreview}>
                  <Text style={styles.signatureConfirmed}>Signature captured</Text>
                  <TouchableOpacity
                    style={styles.resignButton}
                    onPress={() => {
                      setSupervisorSignature(null);
                      setShowSubmitModal(false);
                      setTimeout(() => setShowSignatureModal(true), 300);
                    }}
                  >
                    <Text style={styles.resignButtonText}>Re-sign</Text>
                  </TouchableOpacity>
                </View>
              ) : (
                <TouchableOpacity
                  style={styles.signatureButton}
                  onPress={() => {
                    setShowSubmitModal(false);
                    setTimeout(() => setShowSignatureModal(true), 300);
                  }}
                >
                  <Ionicons name="create-outline" size={24} color={COLORS.primary} />
                  <Text style={styles.signatureButtonText}>Tap to Sign</Text>
                </TouchableOpacity>
              )}

              <View style={styles.modalButtons}>
                <TouchableOpacity
                  style={styles.cancelButton}
                  onPress={() => setShowSubmitModal(false)}
                >
                  <Text style={styles.cancelButtonText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.confirmButton, isSubmitting && styles.confirmButtonDisabled]}
                  onPress={handleSubmit}
                  disabled={isSubmitting}
                >
                  {isSubmitting ? (
                    <ActivityIndicator color="#FFFFFF" size="small" />
                  ) : (
                    <Text style={styles.confirmButtonText}>Submit</Text>
                  )}
                </TouchableOpacity>
              </View>
            </View>
          </ScrollView>
        </KeyboardAvoidingView>
      </Modal>

      {/* Signature Modal */}
      <Modal
        visible={showSignatureModal}
        animationType="slide"
        onRequestClose={() => setShowSignatureModal(false)}
      >
        <View style={styles.signatureModalContainer}>
          <View style={styles.signatureHeader}>
            <Text style={styles.signatureTitle}>Supervisor Signature</Text>
            <Text style={styles.signatureSubtitle}>Please sign in the box below</Text>
          </View>
          
          <View style={styles.signatureCanvasContainer}>
            <SignatureCanvas
              ref={signatureRef}
              onOK={handleSignature}
              onEmpty={() => Alert.alert('Error', 'Please provide a signature')}
              descriptionText=""
              clearText="Clear"
              confirmText="Confirm"
              webStyle={`
                .m-signature-pad { box-shadow: none; border: none; }
                .m-signature-pad--body { border: 2px solid #E5E7EB; border-radius: 12px; }
                .m-signature-pad--footer { display: none; }
                body, html { background-color: #F5F5F5; }
              `}
              backgroundColor="#FFFFFF"
              penColor="#1A1A1A"
            />
          </View>

          <View style={styles.signatureActions}>
            <TouchableOpacity
              style={styles.signatureClearButton}
              onPress={handleClearSignature}
            >
              <Ionicons name="trash-outline" size={20} color="#6B7280" />
              <Text style={styles.signatureClearText}>Clear</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.signatureConfirmButton}
              onPress={handleConfirmSignature}
            >
              <Ionicons name="checkmark" size={20} color="#FFFFFF" />
              <Text style={styles.signatureConfirmText}>Confirm Signature</Text>
            </TouchableOpacity>
          </View>

          <TouchableOpacity
            style={styles.signatureCancelButton}
            onPress={() => {
              setShowSignatureModal(false);
              setTimeout(() => setShowSubmitModal(true), 300);
            }}
          >
            <Text style={styles.signatureCancelText}>Cancel</Text>
          </TouchableOpacity>
        </View>
      </Modal>
    </View>
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
  },
  errorContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  errorText: {
    color: '#6B7280',
    fontSize: 16,
  },
  header: {
    backgroundColor: '#FFFFFF',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#E5E7EB',
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  docketBadge: {
    backgroundColor: '#1A1A1A',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
  },
  docketText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
  statusBadge: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
  },
  statusText: {
    fontSize: 14,
    fontWeight: '500',
  },
  weekRange: {
    fontSize: 20,
    fontWeight: '600',
    color: '#1A1A1A',
  },
  summaryCard: {
    flexDirection: 'row',
    backgroundColor: '#FFFFFF',
    marginHorizontal: 16,
    marginTop: 16,
    borderRadius: 12,
    padding: 16,
  },
  summaryItem: {
    flex: 1,
    alignItems: 'center',
  },
  summaryDivider: {
    width: 1,
    backgroundColor: '#E5E7EB',
  },
  summaryLabel: {
    fontSize: 12,
    color: '#6B7280',
    marginBottom: 4,
  },
  summaryValue: {
    fontSize: 20,
    fontWeight: '600',
    color: '#1A1A1A',
  },
  summaryTotal: {
    color: COLORS.primary,
  },
  entriesSection: {
    padding: 16,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1A1A1A',
    marginBottom: 12,
  },
  noEntries: {
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 32,
    alignItems: 'center',
  },
  noEntriesText: {
    color: '#6B7280',
  },
  entryCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 16,
    marginBottom: 8,
  },
  entryHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  entryHeaderRight: {
    alignItems: 'flex-end',
  },
  entryDay: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1A1A1A',
  },
  entryDate: {
    fontSize: 14,
    color: '#6B7280',
    marginTop: 4,
  },
  entryStatusBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
  },
  entryStatusText: {
    fontSize: 12,
    fontWeight: '500',
  },
  submitEntryHint: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  submitEntryHintText: {
    fontSize: 12,
    color: COLORS.primary,
    fontWeight: '500',
  },
  entryCompany: {
    fontSize: 13,
    color: '#6B7280',
    marginTop: 4,
  },
  entryDetails: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  entryTimeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  entryTime: {
    fontSize: 14,
    color: '#6B7280',
  },
  entryHours: {
    backgroundColor: '#F3F4F6',
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 6,
  },
  entryHoursText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1A1A1A',
  },
  entryWorkedAs: {
    fontSize: 13,
    color: '#6B7280',
    marginTop: 8,
  },
  entryLocation: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 8,
    gap: 4,
  },
  entryLocationText: {
    fontSize: 12,
    color: '#9CA3AF',
    flex: 1,
  },
  footer: {
    padding: 16,
    backgroundColor: '#FFFFFF',
    borderTopWidth: 1,
    borderTopColor: '#E5E7EB',
  },
  submitButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: COLORS.primary,
    padding: 16,
    borderRadius: 12,
    gap: 8,
  },
  submitButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'flex-end',
  },
  modalScroll: {
    maxHeight: '90%',
  },
  modalContent: {
    backgroundColor: '#FFFFFF',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    padding: 24,
    paddingBottom: 40,
  },
  modalTitle: {
    fontSize: 24,
    fontWeight: '600',
    color: '#1A1A1A',
    marginBottom: 4,
  },
  modalSubtitle: {
    fontSize: 14,
    color: '#6B7280',
    marginBottom: 24,
  },
  inputLabel: {
    fontSize: 14,
    fontWeight: '500',
    color: '#1A1A1A',
    marginBottom: 8,
  },
  input: {
    backgroundColor: '#F3F4F6',
    borderRadius: 12,
    padding: 16,
    fontSize: 16,
    marginBottom: 16,
  },
  modalButtons: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 8,
  },
  cancelButton: {
    flex: 1,
    padding: 16,
    borderRadius: 12,
    backgroundColor: '#F3F4F6',
    alignItems: 'center',
  },
  cancelButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#6B7280',
  },
  confirmButton: {
    flex: 1,
    padding: 16,
    borderRadius: 12,
    backgroundColor: COLORS.primary,
    alignItems: 'center',
  },
  confirmButtonDisabled: {
    backgroundColor: '#93C5FD',
  },
  confirmButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  // Signature styles
  signatureButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#EFF6FF',
    borderRadius: 12,
    padding: 20,
    borderWidth: 2,
    borderColor: COLORS.primary,
    borderStyle: 'dashed',
    gap: 8,
    marginBottom: 16,
  },
  signatureButtonText: {
    fontSize: 16,
    fontWeight: '500',
    color: COLORS.primary,
  },
  signaturePreview: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#F0FDF4',
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
  },
  signatureConfirmed: {
    fontSize: 14,
    fontWeight: '500',
    color: '#10B981',
  },
  resignButton: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: '#FFFFFF',
    borderRadius: 6,
  },
  resignButtonText: {
    fontSize: 14,
    color: COLORS.primary,
    fontWeight: '500',
  },
  signatureModalContainer: {
    flex: 1,
    backgroundColor: '#F5F5F5',
    paddingTop: 60,
  },
  signatureHeader: {
    paddingHorizontal: 24,
    marginBottom: 20,
  },
  signatureTitle: {
    fontSize: 24,
    fontWeight: '600',
    color: '#1A1A1A',
    marginBottom: 4,
  },
  signatureSubtitle: {
    fontSize: 14,
    color: '#6B7280',
  },
  signatureCanvasContainer: {
    flex: 1,
    marginHorizontal: 16,
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    overflow: 'hidden',
  },
  signatureActions: {
    flexDirection: 'row',
    padding: 16,
    gap: 12,
  },
  signatureClearButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    gap: 8,
  },
  signatureClearText: {
    fontSize: 16,
    fontWeight: '500',
    color: '#6B7280',
  },
  signatureConfirmButton: {
    flex: 2,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
    backgroundColor: COLORS.primary,
    borderRadius: 12,
    gap: 8,
  },
  signatureConfirmText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  signatureCancelButton: {
    padding: 16,
    alignItems: 'center',
    marginBottom: 20,
  },
  signatureCancelText: {
    fontSize: 16,
    color: '#6B7280',
  },
});
