'use client';

import { useState } from 'react';
import styles from '../settings.module.css';
import CustomSelect from '../../components/CustomSelect';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api';

type FileCategory = 'Academic' | 'Administrative' | 'Educational';

interface FileWithCategory {
  file: File;
  category: FileCategory;
}

export default function UploadSection() {
  const [uploadedFiles, setUploadedFiles] = useState<FileWithCategory[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [defaultCategory, setDefaultCategory] = useState<FileCategory>('Academic');
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<{
    show: boolean;
    success: boolean;
    message: string;
  }>({ show: false, success: false, message: '' });

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    
    const files = Array.from(e.dataTransfer.files);
    handleFiles(files);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const files = Array.from(e.target.files);
      handleFiles(files);
    }
  };

  const handleFiles = (files: File[]) => {
    // Filter for supported file types: .txt, .pdf, .docx
    const allowedExtensions = ['.txt', '.pdf', '.docx'];
    const validFiles = files.filter(file => 
      allowedExtensions.some(ext => file.name.toLowerCase().endsWith(ext))
    );

    // Filter for max size (10MB)
    const maxSize = 10 * 1024 * 1024;
    const sizedFiles = validFiles.filter(file => file.size <= maxSize);

    // Add files with default category
    const filesWithCategory = sizedFiles.map(file => ({
      file,
      category: defaultCategory
    }));

    setUploadedFiles(prev => [...prev, ...filesWithCategory]);
  };

  const removeFile = (index: number) => {
    setUploadedFiles(prev => prev.filter((_, i) => i !== index));
  };

  const updateFileCategory = (index: number, category: FileCategory) => {
    setUploadedFiles(prev => prev.map((item, i) => 
      i === index ? { ...item, category } : item
    ));
  };

  const uploadAllFiles = async () => {
    if (uploadedFiles.length === 0) return;

    setIsUploading(true);
    setUploadStatus({ show: false, success: false, message: '' });

    try {
      const token = localStorage.getItem('token');
      if (!token) {
        throw new Error('Not authenticated');
      }

      let successCount = 0;
      let failCount = 0;
      const errors: string[] = [];

      // Upload files one by one
      for (const { file, category } of uploadedFiles) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('category', category);

        try {
          const response = await fetch(`${API_BASE}/settings/upload`, {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${token}`,
            },
            body: formData,
          });

          if (response.ok) {
            successCount++;
          } else {
            const error = await response.json();
            failCount++;
            errors.push(`${file.name}: ${error.detail || 'Upload failed'}`);
          }
        } catch (error) {
          failCount++;
          errors.push(`${file.name}: Network error`);
        }
      }

      // Show status
      if (successCount > 0 && failCount === 0) {
        setUploadStatus({
          show: true,
          success: true,
          message: `Successfully uploaded ${successCount} file${successCount > 1 ? 's' : ''}!`
        });
        setUploadedFiles([]);
        // Notify KnowledgeBase component to refresh
        window.dispatchEvent(new Event('kb-files-updated'));
      } else if (successCount > 0 && failCount > 0) {
        setUploadStatus({
          show: true,
          success: false,
          message: `Uploaded ${successCount} file(s), but ${failCount} failed: ${errors.join(', ')}`
        });
      } else {
        setUploadStatus({
          show: true,
          success: false,
          message: `Upload failed: ${errors.join(', ')}`
        });
      }

      // Auto-hide success message after 5 seconds
      if (failCount === 0) {
        setTimeout(() => {
          setUploadStatus({ show: false, success: false, message: '' });
        }, 5000);
      }

    } catch (error) {
      setUploadStatus({
        show: true,
        success: false,
        message: error instanceof Error ? error.message : 'Upload failed'
      });
    } finally {
      setIsUploading(false);
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  return (
    <div className={styles.sectionContent}>
      <div className={styles.sectionIntro}>
        <h3>📚 Knowledge Base Enhancement</h3>
        <p>Upload custom documents to expand EduBot's knowledge with your specific content</p>
      </div>

      {/* Upload Status Message */}
      {uploadStatus.show && (
        <div className={`${styles.uploadStatus} ${uploadStatus.success ? styles.uploadStatusSuccess : styles.uploadStatusError}`}>
          {uploadStatus.success ? '✓' : '✗'} {uploadStatus.message}
        </div>
      )}

      {/* Category Selector */}
      <div className={styles.categorySelector}>
        <label htmlFor="defaultCategory">Default Category for New Files:</label>
        <CustomSelect
          id="defaultCategory"
          value={defaultCategory}
          onChange={(value) => setDefaultCategory(value as FileCategory)}
          options={[
            { value: 'Academic', label: '📅 Academic (Calendars, Schedules, Dates)' },
            { value: 'Administrative', label: '🏛️ Administrative (Policies, Procedures, Info)' },
            { value: 'Educational', label: '📖 Educational (Course Materials, Resources)' },
          ]}
        />
      </div>

      <div 
        className={`${styles.uploadBox} ${isDragging ? styles.uploadBoxDragging : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <div className={styles.uploadIcon}>📄</div>
        <p className={styles.uploadText}>Drag & drop files here</p>
        <p className={styles.uploadHint}>or click to browse</p>
        <p className={styles.uploadSupported}>Supports PDF, DOCX, and TXT files (Max 10MB each)</p>
        
        <input
          type="file"
          id="fileInput"
          multiple
          accept=".txt,.pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          onChange={handleFileSelect}
          className={styles.fileInput}
        />
        <label htmlFor="fileInput" className={styles.uploadButton}>
          Choose Files
        </label>
      </div>

      {uploadedFiles.length > 0 && (
        <div className={styles.uploadedFilesList}>
          <h4>Ready to Upload ({uploadedFiles.length})</h4>
          <div className={styles.filesList}>
            {uploadedFiles.map((item, index) => (
              <div key={index} className={styles.fileItem}>
                <div className={styles.fileInfo}>
                  <span className={styles.fileIcon}>📎</span>
                  <div className={styles.fileDetails}>
                    <p className={styles.fileName}>{item.file.name}</p>
                    <p className={styles.fileSize}>{formatFileSize(item.file.size)}</p>
                  </div>
                  <div className={styles.fileCategorySelectWrapper}>
                    <CustomSelect
                      value={item.category}
                      onChange={(value) => updateFileCategory(index, value as FileCategory)}
                      disabled={isUploading}
                      options={[
                        { value: 'Academic', label: '📅 Academic' },
                        { value: 'Administrative', label: '🏛️ Administrative' },
                        { value: 'Educational', label: '📖 Educational' },
                      ]}
                    />
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => removeFile(index)}
                  className={styles.removeButton}
                  title="Remove file"
                  disabled={isUploading}
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
          <button 
            type="button" 
            className={styles.uploadAllButton}
            onClick={uploadAllFiles}
            disabled={isUploading}
          >
            {isUploading ? (
              <>
                <span className={styles.spinner}></span>
                Uploading...
              </>
            ) : (
              'Upload All Files'
            )}
          </button>
        </div>
      )}

      <div className={styles.uploadInfo}>
        <h4>ℹ️ Upload Guidelines</h4>
        <ul>
          <li><strong>Academic:</strong> Calendars, schedules, holidays, deadlines, events</li>
          <li><strong>Administrative:</strong> Policies, procedures, contact information, fees</li>
          <li><strong>Educational:</strong> Course materials, syllabi, study guides, resources</li>
          <li>Supports <strong>PDF</strong>, <strong>DOCX</strong>, and <strong>TXT</strong> files</li>
          <li>PDF and DOCX files are automatically converted to text for the knowledge base</li>
          <li>Scanned PDFs need selectable text to be indexed correctly</li>
          <li>Maximum file size: 10MB per file</li>
          <li>Content will be available for all users in your organization</li>
        </ul>
      </div>
    </div>
  );
}

