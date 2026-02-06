/**
 * Supervisor Signature Screen
 * Shows after clock out to capture supervisor details and signature
 */

import React, { useState, useRef } from 'react';
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
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RouteProp } from '@react-navigation/native';
import SignatureCanvas from 'react-native-signature-canvas';
import { RootStackParamList } from '../../App';
import { COLORS } from '../constants/colors';
import { timesheetsAPI } from '../services/api';

type SupervisorSignatureScreenProps = {
  navigation: NativeStackNavigationProp<RootStackParamList, 'SupervisorSignature'>;
  route: RouteProp<RootStackParamList, 'SupervisorSignature'>;
};

export default function SupervisorSignatureScreen({ navigation, route }: SupervisorSignatureScreenProps) {
  const { entryId, hoursWorked, docketNumber } = route.params;
  
  const [companyName, setCompanyName] = useState('');
  const [supervisorName, setSupervisorName] = useState('');
  const [supervisorPhone, setSupervisorPhone] = useState('');
  const [signature, setSignature] = useState<string | null>(null);
  const [showSignatureModal, setShowSignatureModal] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  
  const signatureRef = useRef<SignatureCanvas>(null);

  const handleSignature = (sig: string) => {
    setSignature(sig);
    setShowSignatureModal(false);
  };

  const handleClearSignature = () => {
    signatureRef.current?.clearSignature();
  };

  const handleConfirmSignature = () => {
    signatureRef.current?.readSignature();
  };

  const handleSubmit = async () => {
    if (!companyName.trim()) {
      Alert.alert('Required', 'Please enter the company/host name');
      return;
    }
    if (!supervisorName.trim()) {
      Alert.alert('Required', 'Please enter the supervisor name');
      return;
    }
    if (!supervisorPhone.trim()) {
      Alert.alert('Required', 'Please enter the supervisor phone number');
      return;
    }
    if (!signature) {
      Alert.alert('Required', 'Please get the supervisor signature');
      return;
    }

    setIsSubmitting(true);
    try {
      await timesheetsAPI.submitEntry(entryId, {
        company_name: companyName.trim(),
        supervisor_name: supervisorName.trim(),
        supervisor_contact: supervisorPhone.trim(),
        supervisor_signature: signature,
      });

      Alert.alert(
        'Timesheet Submitted!',
        `Docket #${docketNumber}\n\nYour timesheet has been sent to admin for approval.\n\nHours: ${hoursWorked}`,
        [
          {
            text: 'OK',
            onPress: () => {
              // Navigate back to main/dashboard
              navigation.reset({
                index: 0,
                routes: [{ name: 'Main' }],
              });
            },
          },
        ]
      );
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Failed to submit timesheet. Please try again.';
      Alert.alert('Error', message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        {/* Header Info */}
        <View style={styles.headerCard}>
          <View style={styles.headerRow}>
            <Ionicons name="checkmark-circle" size={48} color="#10B981" />
            <View style={styles.headerInfo}>
              <Text style={styles.headerTitle}>Clocked Out!</Text>
              <Text style={styles.headerSubtitle}>Hours Worked: {hoursWorked}</Text>
              <Text style={styles.docketNumber}>Docket #{docketNumber}</Text>
            </View>
          </View>
        </View>

        {/* Instruction */}
        <View style={styles.instructionBox}>
          <Ionicons name="information-circle" size={24} color={COLORS.primary} />
          <Text style={styles.instructionText}>
            Please get your supervisor to verify your work hours and sign below to submit your timesheet.
          </Text>
        </View>

        {/* Form */}
        <View style={styles.formSection}>
          <Text style={styles.sectionTitle}>Supervisor Details</Text>

          <View style={styles.inputGroup}>
            <Text style={styles.inputLabel}>Company / Host Name *</Text>
            <TextInput
              style={styles.input}
              placeholder="Enter company name"
              placeholderTextColor="#9CA3AF"
              value={companyName}
              onChangeText={setCompanyName}
            />
          </View>

          <View style={styles.inputGroup}>
            <Text style={styles.inputLabel}>Supervisor Name *</Text>
            <TextInput
              style={styles.input}
              placeholder="Enter supervisor's full name"
              placeholderTextColor="#9CA3AF"
              value={supervisorName}
              onChangeText={setSupervisorName}
            />
          </View>

          <View style={styles.inputGroup}>
            <Text style={styles.inputLabel}>Supervisor Phone *</Text>
            <TextInput
              style={styles.input}
              placeholder="Enter supervisor's phone number"
              placeholderTextColor="#9CA3AF"
              value={supervisorPhone}
              onChangeText={setSupervisorPhone}
              keyboardType="phone-pad"
            />
          </View>
        </View>

        {/* Signature Section */}
        <View style={styles.signatureSection}>
          <Text style={styles.sectionTitle}>Supervisor Signature *</Text>
          
          {signature ? (
            <View style={styles.signaturePreview}>
              <View style={styles.signatureImageContainer}>
                <Text style={styles.signaturePlaceholder}>Signature Captured ✓</Text>
              </View>
              <TouchableOpacity
                style={styles.clearSignatureButton}
                onPress={() => setSignature(null)}
              >
                <Text style={styles.clearSignatureText}>Clear & Re-sign</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <TouchableOpacity
              style={styles.signatureButton}
              onPress={() => setShowSignatureModal(true)}
            >
              <Ionicons name="create-outline" size={32} color={COLORS.primary} />
              <Text style={styles.signatureButtonText}>Tap to Capture Signature</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Submit Button */}
        <TouchableOpacity
          style={[
            styles.submitButton,
            (!signature || isSubmitting) && styles.submitButtonDisabled,
          ]}
          onPress={handleSubmit}
          disabled={!signature || isSubmitting}
        >
          {isSubmitting ? (
            <ActivityIndicator color="#FFFFFF" />
          ) : (
            <>
              <Ionicons name="send" size={24} color="#FFFFFF" />
              <Text style={styles.submitButtonText}>SUBMIT TIMESHEET</Text>
            </>
          )}
        </TouchableOpacity>

        <Text style={styles.footerText}>
          By submitting, the supervisor confirms the hours worked are accurate.
        </Text>
      </ScrollView>

      {/* Signature Modal */}
      <Modal
        visible={showSignatureModal}
        animationType="slide"
        transparent={false}
      >
        <View style={styles.signatureModalContainer}>
          <View style={styles.signatureModalHeader}>
            <Text style={styles.signatureModalTitle}>Supervisor Signature</Text>
            <TouchableOpacity onPress={() => setShowSignatureModal(false)}>
              <Ionicons name="close" size={28} color="#1A1A1A" />
            </TouchableOpacity>
          </View>
          
          <Text style={styles.signatureInstruction}>
            Please sign in the box below
          </Text>
          
          <View style={styles.signatureCanvasContainer}>
            <SignatureCanvas
              ref={signatureRef}
              onOK={handleSignature}
              onEmpty={() => Alert.alert('Error', 'Please provide a signature')}
              descriptionText=""
              clearText="Clear"
              confirmText="Save"
              webStyle={`
                .m-signature-pad {
                  box-shadow: none;
                  border: none;
                  margin: 0;
                  width: 100%;
                  height: 100%;
                }
                .m-signature-pad--body {
                  border: 2px dashed #E5E7EB;
                  border-radius: 8px;
                }
                .m-signature-pad--footer {
                  display: none;
                }
              `}
              backgroundColor="#FFFFFF"
            />
          </View>
          
          <View style={styles.signatureModalButtons}>
            <TouchableOpacity
              style={styles.clearButton}
              onPress={handleClearSignature}
            >
              <Text style={styles.clearButtonText}>Clear</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.saveButton}
              onPress={handleConfirmSignature}
            >
              <Text style={styles.saveButtonText}>Save Signature</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
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
    padding: 16,
    paddingBottom: 40,
  },
  headerCard: {
    backgroundColor: '#ECFDF5',
    borderRadius: 12,
    padding: 20,
    marginBottom: 16,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  headerInfo: {
    marginLeft: 16,
    flex: 1,
  },
  headerTitle: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#065F46',
  },
  headerSubtitle: {
    fontSize: 16,
    color: '#047857',
    marginTop: 4,
  },
  docketNumber: {
    fontSize: 14,
    color: '#10B981',
    marginTop: 4,
    fontWeight: '600',
  },
  instructionBox: {
    flexDirection: 'row',
    backgroundColor: '#EFF6FF',
    borderRadius: 8,
    padding: 12,
    marginBottom: 20,
    alignItems: 'flex-start',
  },
  instructionText: {
    flex: 1,
    marginLeft: 10,
    fontSize: 14,
    color: '#1E40AF',
    lineHeight: 20,
  },
  formSection: {
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1A1A1A',
    marginBottom: 16,
  },
  inputGroup: {
    marginBottom: 16,
  },
  inputLabel: {
    fontSize: 14,
    fontWeight: '500',
    color: '#374151',
    marginBottom: 8,
  },
  input: {
    backgroundColor: '#F9FAFB',
    borderWidth: 1,
    borderColor: '#E5E7EB',
    borderRadius: 8,
    padding: 14,
    fontSize: 16,
    color: '#1A1A1A',
  },
  signatureSection: {
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 16,
    marginBottom: 20,
  },
  signatureButton: {
    backgroundColor: '#F9FAFB',
    borderWidth: 2,
    borderColor: '#E5E7EB',
    borderStyle: 'dashed',
    borderRadius: 12,
    padding: 32,
    alignItems: 'center',
    justifyContent: 'center',
  },
  signatureButtonText: {
    marginTop: 12,
    fontSize: 16,
    color: COLORS.primary,
    fontWeight: '500',
  },
  signaturePreview: {
    alignItems: 'center',
  },
  signatureImageContainer: {
    backgroundColor: '#ECFDF5',
    borderRadius: 8,
    padding: 24,
    width: '100%',
    alignItems: 'center',
  },
  signaturePlaceholder: {
    fontSize: 18,
    color: '#065F46',
    fontWeight: '600',
  },
  clearSignatureButton: {
    marginTop: 12,
    padding: 8,
  },
  clearSignatureText: {
    color: '#DC2626',
    fontSize: 14,
    fontWeight: '500',
  },
  submitButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: COLORS.primary,
    borderRadius: 12,
    padding: 18,
    gap: 12,
  },
  submitButtonDisabled: {
    backgroundColor: '#9CA3AF',
  },
  submitButtonText: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  footerText: {
    textAlign: 'center',
    fontSize: 13,
    color: '#6B7280',
    marginTop: 16,
    paddingHorizontal: 20,
  },
  // Signature Modal Styles
  signatureModalContainer: {
    flex: 1,
    backgroundColor: '#FFFFFF',
    padding: 16,
  },
  signatureModalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#E5E7EB',
  },
  signatureModalTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#1A1A1A',
  },
  signatureInstruction: {
    textAlign: 'center',
    fontSize: 16,
    color: '#6B7280',
    marginVertical: 16,
  },
  signatureCanvasContainer: {
    flex: 1,
    borderRadius: 8,
    overflow: 'hidden',
    marginBottom: 16,
  },
  signatureModalButtons: {
    flexDirection: 'row',
    gap: 12,
    paddingBottom: 20,
  },
  clearButton: {
    flex: 1,
    backgroundColor: '#F3F4F6',
    borderRadius: 8,
    padding: 16,
    alignItems: 'center',
  },
  clearButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#6B7280',
  },
  saveButton: {
    flex: 2,
    backgroundColor: COLORS.primary,
    borderRadius: 8,
    padding: 16,
    alignItems: 'center',
  },
  saveButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
});
