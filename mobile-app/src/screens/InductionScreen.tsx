/**
 * Induction Screen
 * SWMS and onboarding documents with electronic signatures
 */

import React, { useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  RefreshControl,
  ActivityIndicator,
  Modal,
  Alert,
  Dimensions,
  useWindowDimensions,
  Linking,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native';
import SignatureScreen from 'react-native-signature-canvas';
import { COLORS } from '../constants/colors';
import { inductionAPI, API_BASE_URL } from '../services/api';
import { useAuth } from '../context/AuthContext';

interface InductionDocument {
  id: number;
  title: string;
  description: string | null;
  content: string | null;
  document_type: string;
  category: string | null;
  version: string;
  is_required: boolean;
  pdf_filename: string | null;
  pdf_url: string | null;
}

interface DocumentStatus {
  document_id: number;
  document_title: string;
  document_type: string;
  category: string | null;
  is_required: boolean;
  status: string;
  signed_at: string | null;
}

interface InductionStatus {
  total_required: number;
  total_signed: number;
  is_complete: boolean;
  documents: DocumentStatus[];
}

export default function InductionScreen() {
  const { user } = useAuth();
  const { width: screenWidth } = useWindowDimensions();
  
  const [status, setStatus] = useState<InductionStatus | null>(null);
  const [documents, setDocuments] = useState<InductionDocument[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  
  // Document view modal
  const [viewDocument, setViewDocument] = useState<InductionDocument | null>(null);
  const [documentStatus, setDocumentStatus] = useState<DocumentStatus | null>(null);
  
  // Signature modal
  const [showSignature, setShowSignature] = useState(false);
  const [isSigning, setIsSigning] = useState(false);
  const signatureRef = useRef<SignatureScreen>(null);

  const fetchData = async () => {
    try {
      const [statusRes, docsRes] = await Promise.all([
        inductionAPI.getStatus(user?.id),
        inductionAPI.getDocuments(),
      ]);
      setStatus(statusRes.data);
      setDocuments(docsRes.data.documents || []);
    } catch (error) {
      console.warn('Error fetching induction data:', error);
    } finally {
      setIsLoading(false);
      setRefreshing(false);
    }
  };

  useFocusEffect(
    useCallback(() => {
      fetchData();
    }, [user?.id])
  );

  const onRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  const openDocument = (doc: InductionDocument) => {
    const docStatus = status?.documents.find(d => d.document_id === doc.id);
    setDocumentStatus(docStatus || null);
    setViewDocument(doc);
  };

  const handleSign = () => {
    setViewDocument(null);
    setTimeout(() => setShowSignature(true), 300);
  };

  const handleSignature = async (signature: string) => {
    if (!viewDocument && !documentStatus) {
      setShowSignature(false);
      return;
    }
    
    const docId = documentStatus?.document_id;
    if (!docId) {
      setShowSignature(false);
      return;
    }
    
    setIsSigning(true);
    try {
      await inductionAPI.signDocument({
        document_id: docId,
        signature: signature,
      }, user?.id);
      
      setShowSignature(false);
      Alert.alert('Success', 'Document signed successfully');
      fetchData();
    } catch (error: any) {
      console.warn('Error signing document:', error);
      Alert.alert('Error', error.response?.data?.detail || 'Failed to sign document');
    } finally {
      setIsSigning(false);
    }
  };

  const handleClearSignature = () => {
    signatureRef.current?.clearSignature();
  };

  const getStatusIcon = (docStatus: string) => {
    switch (docStatus) {
      case 'signed':
        return { name: 'checkmark-circle', color: '#10B981' };
      case 'pending':
        return { name: 'time', color: '#F59E0B' };
      default:
        return { name: 'document-outline', color: '#6B7280' };
    }
  };

  const getDocTypeIcon = (docType: string) => {
    switch (docType) {
      case 'swms':
        return 'shield-checkmark';
      case 'induction':
        return 'school';
      case 'policy':
        return 'document-text';
      default:
        return 'document';
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-AU', { 
      day: 'numeric', 
      month: 'short', 
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  // Simple HTML to text renderer (basic)
  const renderContent = (html: string) => {
    // Remove HTML tags for simple display
    // In production, you'd want to use a proper HTML renderer
    const text = html
      .replace(/<h2>/g, '\n')
      .replace(/<\/h2>/g, '\n\n')
      .replace(/<h3>/g, '\n')
      .replace(/<\/h3>/g, '\n')
      .replace(/<li>/g, '• ')
      .replace(/<\/li>/g, '\n')
      .replace(/<ul>/g, '')
      .replace(/<\/ul>/g, '\n')
      .replace(/<ol>/g, '')
      .replace(/<\/ol>/g, '\n')
      .replace(/<p>/g, '')
      .replace(/<\/p>/g, '\n\n')
      .replace(/<strong>/g, '')
      .replace(/<\/strong>/g, '')
      .replace(/<br\s*\/?>/g, '\n')
      .replace(/<[^>]*>/g, '')
      .trim();
    return text;
  };

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={COLORS.primary} />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Progress Header */}
      <View style={styles.progressHeader}>
        <View style={styles.progressInfo}>
          <Text style={styles.progressTitle}>Induction Progress</Text>
          <Text style={styles.progressText}>
            {status?.total_signed || 0} of {status?.total_required || 0} documents signed
          </Text>
        </View>
        {status?.is_complete ? (
          <View style={styles.completeBadge}>
            <Ionicons name="checkmark-circle" size={20} color="#10B981" />
            <Text style={styles.completeText}>Complete</Text>
          </View>
        ) : (
          <View style={styles.pendingBadge}>
            <Ionicons name="time" size={20} color="#F59E0B" />
            <Text style={styles.pendingText}>Pending</Text>
          </View>
        )}
      </View>

      {/* Progress Bar */}
      <View style={styles.progressBarContainer}>
        <View 
          style={[
            styles.progressBar, 
            { 
              width: status?.total_required 
                ? `${(status.total_signed / status.total_required) * 100}%` 
                : '0%' 
            }
          ]} 
        />
      </View>

      {/* Documents List */}
      <ScrollView
        style={styles.documentsList}
        contentContainerStyle={styles.documentsContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
        }
      >
        {status?.documents.map((docStatus) => {
          const doc = documents.find(d => d.id === docStatus.document_id);
          if (!doc) return null;
          
          const statusIcon = getStatusIcon(docStatus.status);
          
          return (
            <TouchableOpacity
              key={doc.id}
              style={styles.documentCard}
              onPress={() => openDocument(doc)}
            >
              <View style={[styles.documentIcon, doc.pdf_filename && styles.documentIconPdf]}>
                <Ionicons 
                  name={doc.pdf_filename ? 'document' : getDocTypeIcon(doc.document_type) as any} 
                  size={24} 
                  color={doc.pdf_filename ? '#DC2626' : COLORS.primary} 
                />
              </View>
              <View style={styles.documentInfo}>
                <View style={styles.documentTitleRow}>
                  <Text style={styles.documentTitle}>{doc.title}</Text>
                  {doc.pdf_filename && (
                    <View style={styles.pdfBadge}>
                      <Text style={styles.pdfBadgeText}>PDF</Text>
                    </View>
                  )}
                </View>
                {doc.category && (
                  <Text style={styles.documentCategory}>{doc.category}</Text>
                )}
                {docStatus.status === 'signed' && docStatus.signed_at && (
                  <Text style={styles.signedDate}>
                    Signed: {formatDate(docStatus.signed_at)}
                  </Text>
                )}
              </View>
              <View style={styles.documentStatus}>
                <Ionicons 
                  name={statusIcon.name as any} 
                  size={24} 
                  color={statusIcon.color} 
                />
              </View>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      {/* Document View Modal */}
      <Modal
        visible={!!viewDocument}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setViewDocument(null)}
      >
        <View style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => setViewDocument(null)}>
              <Ionicons name="close" size={24} color="#6B7280" />
            </TouchableOpacity>
            <Text style={styles.modalTitle} numberOfLines={1}>
              {viewDocument?.title}
            </Text>
            <View style={{ width: 24 }} />
          </View>

          {viewDocument && (
            <>
              <ScrollView style={styles.documentContent}>
                {viewDocument.category && (
                  <View style={styles.categoryBadge}>
                    <Text style={styles.categoryText}>{viewDocument.category}</Text>
                  </View>
                )}
                
                {/* PDF Document */}
                {viewDocument.pdf_filename ? (
                  <View style={styles.pdfContainer}>
                    <View style={styles.pdfIcon}>
                      <Ionicons name="document" size={48} color="#DC2626" />
                    </View>
                    <Text style={styles.pdfTitle}>PDF Document</Text>
                    <Text style={styles.pdfDescription}>
                      This document is a PDF file. Tap the button below to view it in your browser.
                    </Text>
                    <TouchableOpacity
                      style={styles.viewPdfButton}
                      onPress={() => {
                        // Get the base URL without /api
                        const baseUrl = API_BASE_URL.replace('/api', '');
                        const pdfUrl = `${baseUrl}/api/induction/pdf/${viewDocument.pdf_filename}`;
                        Linking.openURL(pdfUrl);
                      }}
                    >
                      <Ionicons name="open-outline" size={20} color="#FFFFFF" />
                      <Text style={styles.viewPdfButtonText}>View PDF</Text>
                    </TouchableOpacity>
                  </View>
                ) : (
                  <Text style={styles.contentText}>
                    {renderContent(viewDocument.content || '')}
                  </Text>
                )}
              </ScrollView>

              <View style={styles.modalFooter}>
                {documentStatus?.status === 'signed' ? (
                  <View style={styles.signedBanner}>
                    <Ionicons name="checkmark-circle" size={24} color="#10B981" />
                    <Text style={styles.signedBannerText}>
                      Signed on {formatDate(documentStatus.signed_at)}
                    </Text>
                  </View>
                ) : (
                  <TouchableOpacity
                    style={styles.signButton}
                    onPress={handleSign}
                  >
                    <Ionicons name="create" size={20} color="#FFFFFF" />
                    <Text style={styles.signButtonText}>Sign Document</Text>
                  </TouchableOpacity>
                )}
              </View>
            </>
          )}
        </View>
      </Modal>

      {/* Signature Modal */}
      <Modal
        visible={showSignature}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setShowSignature(false)}
      >
        <View style={styles.signatureContainer}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={() => setShowSignature(false)}>
              <Text style={styles.cancelText}>Cancel</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle}>Sign Document</Text>
            <TouchableOpacity onPress={handleClearSignature}>
              <Text style={styles.clearText}>Clear</Text>
            </TouchableOpacity>
          </View>

          <Text style={styles.signatureInstructions}>
            Please sign in the box below to acknowledge you have read and understood the document.
          </Text>

          <View style={styles.signatureWrapper}>
            <SignatureScreen
              ref={signatureRef}
              onOK={handleSignature}
              onEmpty={() => Alert.alert('Error', 'Please provide a signature')}
              descriptionText=""
              clearText="Clear"
              confirmText="Confirm"
              webStyle={`
                .m-signature-pad {
                  box-shadow: none;
                  border: none;
                  margin: 0;
                }
                .m-signature-pad--body {
                  border: 2px solid #E5E7EB;
                  border-radius: 12px;
                }
                .m-signature-pad--footer {
                  display: none;
                }
              `}
              autoClear={false}
              imageType="image/png"
            />
          </View>

          <View style={styles.signatureFooter}>
            <TouchableOpacity
              style={[styles.confirmButton, isSigning && styles.confirmButtonDisabled]}
              onPress={() => signatureRef.current?.readSignature()}
              disabled={isSigning}
            >
              {isSigning ? (
                <ActivityIndicator color="#FFFFFF" size="small" />
              ) : (
                <>
                  <Ionicons name="checkmark" size={20} color="#FFFFFF" />
                  <Text style={styles.confirmButtonText}>Confirm Signature</Text>
                </>
              )}
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F3F4F6',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#F3F4F6',
  },
  progressHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#E5E7EB',
  },
  progressInfo: {
    flex: 1,
  },
  progressTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1F2937',
  },
  progressText: {
    fontSize: 14,
    color: '#6B7280',
    marginTop: 4,
  },
  completeBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#D1FAE5',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
    gap: 4,
  },
  completeText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#10B981',
  },
  pendingBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FEF3C7',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
    gap: 4,
  },
  pendingText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#F59E0B',
  },
  progressBarContainer: {
    height: 4,
    backgroundColor: '#E5E7EB',
  },
  progressBar: {
    height: '100%',
    backgroundColor: '#10B981',
  },
  documentsList: {
    flex: 1,
  },
  documentsContent: {
    padding: 16,
  },
  documentCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  documentIcon: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: COLORS.primary + '15',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  documentIconPdf: {
    backgroundColor: '#FEE2E2',
  },
  documentInfo: {
    flex: 1,
  },
  documentTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  documentTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1F2937',
    flex: 1,
  },
  pdfBadge: {
    backgroundColor: '#DC2626',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  pdfBadgeText: {
    fontSize: 10,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  documentCategory: {
    fontSize: 13,
    color: '#6B7280',
    marginTop: 2,
  },
  signedDate: {
    fontSize: 12,
    color: '#10B981',
    marginTop: 4,
  },
  documentStatus: {
    marginLeft: 12,
  },
  // Modal styles
  modalContainer: {
    flex: 1,
    backgroundColor: '#FFFFFF',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#E5E7EB',
  },
  modalTitle: {
    fontSize: 17,
    fontWeight: '600',
    color: '#1F2937',
    flex: 1,
    textAlign: 'center',
    marginHorizontal: 8,
  },
  documentContent: {
    flex: 1,
    padding: 16,
  },
  categoryBadge: {
    alignSelf: 'flex-start',
    backgroundColor: COLORS.primary + '15',
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
    marginBottom: 16,
  },
  categoryText: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.primary,
  },
  contentText: {
    fontSize: 15,
    color: '#374151',
    lineHeight: 24,
  },
  // PDF styles
  pdfContainer: {
    alignItems: 'center',
    paddingVertical: 40,
  },
  pdfIcon: {
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: '#FEE2E2',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 20,
  },
  pdfTitle: {
    fontSize: 20,
    fontWeight: '600',
    color: '#1F2937',
    marginBottom: 8,
  },
  pdfDescription: {
    fontSize: 14,
    color: '#6B7280',
    textAlign: 'center',
    paddingHorizontal: 20,
    marginBottom: 24,
    lineHeight: 20,
  },
  viewPdfButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#DC2626',
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 8,
    gap: 8,
  },
  viewPdfButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  modalFooter: {
    padding: 16,
    borderTopWidth: 1,
    borderTopColor: '#E5E7EB',
  },
  signedBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#D1FAE5',
    padding: 14,
    borderRadius: 8,
    gap: 8,
  },
  signedBannerText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#10B981',
  },
  signButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: COLORS.primary,
    padding: 14,
    borderRadius: 8,
    gap: 8,
  },
  signButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  // Signature modal
  signatureContainer: {
    flex: 1,
    backgroundColor: '#FFFFFF',
  },
  cancelText: {
    fontSize: 16,
    color: '#6B7280',
  },
  clearText: {
    fontSize: 16,
    color: COLORS.primary,
  },
  signatureInstructions: {
    fontSize: 14,
    color: '#6B7280',
    textAlign: 'center',
    padding: 16,
    paddingBottom: 8,
  },
  signatureWrapper: {
    flex: 1,
    margin: 16,
    borderRadius: 12,
    overflow: 'hidden',
  },
  signatureFooter: {
    padding: 16,
    borderTopWidth: 1,
    borderTopColor: '#E5E7EB',
  },
  confirmButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#10B981',
    padding: 14,
    borderRadius: 8,
    gap: 8,
  },
  confirmButtonDisabled: {
    opacity: 0.6,
  },
  confirmButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
});
