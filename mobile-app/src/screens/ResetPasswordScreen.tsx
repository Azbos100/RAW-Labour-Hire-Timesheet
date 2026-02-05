/**
 * Reset Password Screen
 * Request password reset via SMS
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '../../App';
import { COLORS } from '../constants/colors';
import api from '../services/api';

type ResetPasswordScreenProps = {
  navigation: NativeStackNavigationProp<RootStackParamList, 'ResetPassword'>;
};

export default function ResetPasswordScreen({ navigation }: ResetPasswordScreenProps) {
  const [email, setEmail] = useState('');
  const [resetCode, setResetCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const handleSendCode = async () => {
    if (!email.trim()) {
      Alert.alert('Error', 'Please enter your email');
      return;
    }

    setIsLoading(true);
    try {
      await api.post('/auth/password-reset/request', { email: email.trim() });
      Alert.alert(
        'Reset Code Sent',
        'If an account exists with a phone number, a 6-digit reset code will be sent via SMS. The code expires in 15 minutes.'
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleConfirmReset = async () => {
    if (!resetCode.trim() || !newPassword.trim() || !confirmPassword.trim()) {
      Alert.alert('Error', 'Please fill in all reset fields');
      return;
    }

    if (newPassword.trim() !== confirmPassword.trim()) {
      Alert.alert('Error', 'Passwords do not match');
      return;
    }

    if (newPassword.trim().length < 6) {
      Alert.alert('Error', 'Password must be at least 6 characters');
      return;
    }

    setIsLoading(true);
    try {
      await api.post('/auth/password-reset/confirm', {
        token: resetCode.trim(),
        new_password: newPassword.trim(),
      });
      Alert.alert('Success', 'Your password has been reset');
      navigation.goBack();
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Password reset failed';
      Alert.alert('Reset Failed', message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <View style={styles.content}>
        <Text style={styles.title}>Reset your password</Text>
        <Text style={styles.subtitle}>
          Enter your email and we'll send a 6-digit reset code to your phone via SMS.
        </Text>

        <View style={styles.form}>
          <Text style={styles.label}>Email</Text>
          <TextInput
            style={styles.input}
            placeholder="your.email@example.com"
            placeholderTextColor="#9CA3AF"
            value={email}
            onChangeText={setEmail}
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
          />

          <TouchableOpacity
            style={[styles.resetButton, isLoading && styles.resetButtonDisabled]}
            onPress={handleSendCode}
            disabled={isLoading}
          >
            {isLoading ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <Text style={styles.resetButtonText}>Send Reset Code via SMS</Text>
            )}
          </TouchableOpacity>

          <View style={styles.divider}>
            <View style={styles.dividerLine} />
            <Text style={styles.dividerText}>enter code from SMS</Text>
            <View style={styles.dividerLine} />
          </View>

          <Text style={styles.label}>6-Digit Reset Code</Text>
          <TextInput
            style={styles.input}
            placeholder="Enter 6-digit code from SMS"
            placeholderTextColor="#9CA3AF"
            value={resetCode}
            onChangeText={setResetCode}
            keyboardType="number-pad"
            maxLength={6}
            autoCapitalize="none"
            autoCorrect={false}
          />

          <Text style={styles.label}>New Password</Text>
          <View style={styles.passwordRow}>
            <TextInput
              style={[styles.input, styles.passwordInput]}
              placeholder="Minimum 6 characters"
              placeholderTextColor="#9CA3AF"
              value={newPassword}
              onChangeText={setNewPassword}
              secureTextEntry={!showNewPassword}
            />
            <TouchableOpacity
              style={styles.passwordToggle}
              onPress={() => setShowNewPassword((prev) => !prev)}
            >
              <Text style={styles.passwordToggleText}>
                {showNewPassword ? 'Hide' : 'Show'}
              </Text>
            </TouchableOpacity>
          </View>

          <Text style={styles.label}>Confirm New Password</Text>
          <View style={styles.passwordRow}>
            <TextInput
              style={[styles.input, styles.passwordInput]}
              placeholder="Re-enter password"
              placeholderTextColor="#9CA3AF"
              value={confirmPassword}
              onChangeText={setConfirmPassword}
              secureTextEntry={!showConfirmPassword}
            />
            <TouchableOpacity
              style={styles.passwordToggle}
              onPress={() => setShowConfirmPassword((prev) => !prev)}
            >
              <Text style={styles.passwordToggleText}>
                {showConfirmPassword ? 'Hide' : 'Show'}
              </Text>
            </TouchableOpacity>
          </View>

          <TouchableOpacity
            style={[styles.confirmButton, isLoading && styles.resetButtonDisabled]}
            onPress={handleConfirmReset}
            disabled={isLoading}
          >
            {isLoading ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <Text style={styles.resetButtonText}>Reset Password</Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity style={styles.backLink} onPress={() => navigation.goBack()}>
            <Text style={styles.backLinkText}>Back to login</Text>
          </TouchableOpacity>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#1A1A1A',
  },
  content: {
    flex: 1,
    padding: 24,
    justifyContent: 'center',
  },
  title: {
    fontSize: 26,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: '#9CA3AF',
    marginBottom: 32,
  },
  form: {},
  label: {
    fontSize: 14,
    fontWeight: '600',
    color: '#9CA3AF',
    marginBottom: 8,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  input: {
    backgroundColor: '#2D2D2D',
    borderRadius: 8,
    padding: 16,
    fontSize: 16,
    color: '#FFFFFF',
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#404040',
  },
  resetButton: {
    backgroundColor: COLORS.primary,
    borderRadius: 8,
    padding: 16,
    alignItems: 'center',
    marginTop: 8,
  },
  resetButtonDisabled: {
    opacity: 0.6,
  },
  resetButtonText: {
    color: '#FFFFFF',
    fontSize: 18,
    fontWeight: 'bold',
  },
  divider: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: 20,
  },
  dividerLine: {
    flex: 1,
    height: 1,
    backgroundColor: '#2D2D2D',
  },
  dividerText: {
    color: '#6B7280',
    fontSize: 12,
    textTransform: 'uppercase',
    marginHorizontal: 10,
    letterSpacing: 1,
  },
  passwordRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  passwordInput: {
    flex: 1,
    marginBottom: 0,
  },
  passwordToggle: {
    marginLeft: 12,
    paddingVertical: 8,
    paddingHorizontal: 10,
  },
  passwordToggleText: {
    color: '#9CA3AF',
    fontSize: 14,
    fontWeight: '600',
  },
  confirmButton: {
    backgroundColor: COLORS.primary,
    borderRadius: 8,
    padding: 16,
    alignItems: 'center',
    marginTop: 8,
  },
  backLink: {
    marginTop: 20,
    alignItems: 'center',
  },
  backLinkText: {
    color: '#9CA3AF',
    fontSize: 14,
    fontWeight: '500',
  },
});
