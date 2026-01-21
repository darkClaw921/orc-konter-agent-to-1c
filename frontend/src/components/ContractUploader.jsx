import React, { useState, useRef } from 'react';
import { useDispatch } from 'react-redux';
import { uploadContract } from '../services/contractService';
import { addContract } from '../store/slices/contractSlice';
import { addNotification } from '../store/slices/uiSlice';
import LoadingSpinner from './LoadingSpinner';

const ContractUploader = () => {
  const dispatch = useDispatch();
  const fileInputRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);

  const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

  const validateFile = (file) => {
    if (!file.name.toLowerCase().endsWith('.docx')) {
      return { valid: false, error: 'Поддерживаются только файлы формата .docx' };
    }
    if (file.size > MAX_FILE_SIZE) {
      return { valid: false, error: 'Размер файла не должен превышать 50MB' };
    }
    return { valid: true };
  };

  const handleFileUpload = async (file) => {
    const validation = validateFile(file);
    if (!validation.valid) {
      dispatch(
        addNotification({
          type: 'error',
          message: validation.error,
        })
      );
      return;
    }

    setIsUploading(true);
    setUploadProgress(0);

    try {
      const response = await uploadContract(file, (progress) => {
        setUploadProgress(progress);
      });

      dispatch(addContract(response));
      dispatch(
        addNotification({
          type: 'success',
          message: `Контракт "${file.name}" успешно загружен`,
        })
      );

      // Сброс состояния
      setUploadProgress(0);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (error) {
      const errorMessage =
        error.response?.data?.detail || 'Ошибка при загрузке файла';
      dispatch(
        addNotification({
          type: 'error',
          message: errorMessage,
        })
      );
    } finally {
      setIsUploading(false);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      handleFileUpload(files[0]);
    }
  };

  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files);
    if (files.length > 0) {
      handleFileUpload(files[0]);
    }
  };

  return (
    <div className="w-full">
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`
          border-2 border-dashed rounded-lg p-12 text-center transition-colors
          ${
            isDragging
              ? 'border-blue-500 bg-blue-50'
              : 'border-gray-300 bg-gray-50 hover:border-gray-400'
          }
          ${isUploading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
        `}
        onClick={() => !isUploading && fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".docx"
          onChange={handleFileSelect}
          className="hidden"
          disabled={isUploading}
        />

        {isUploading ? (
          <div className="space-y-4">
            <LoadingSpinner size="lg" />
            <div className="space-y-2">
              <p className="text-gray-700 font-medium">Загрузка файла...</p>
              <div className="w-full bg-gray-200 rounded-full h-2.5">
                <div
                  className="bg-blue-600 h-2.5 rounded-full transition-all duration-300"
                  style={{ width: `${uploadProgress}%` }}
                ></div>
              </div>
              <p className="text-sm text-gray-600">{uploadProgress}%</p>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex justify-center">
              <svg
                className="w-16 h-16 text-gray-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                />
              </svg>
            </div>
            <div>
              <p className="text-lg font-medium text-gray-700">
                Перетащите файл сюда или нажмите для выбора
              </p>
              <p className="text-sm text-gray-500 mt-2">
                Поддерживаются только файлы .docx (максимум 50MB)
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ContractUploader;
