import React from 'react';
import LoadingSpinner from './LoadingSpinner';

const TestFileList = ({ files, onProcessFile, onViewResults, onReprocessFile, processingFiles }) => {
  const getStatusColor = (status) => {
    const colors = {
      uploaded: 'bg-blue-100 text-blue-800',
      processing: 'bg-yellow-100 text-yellow-800',
      completed: 'bg-green-100 text-green-800',
      failed: 'bg-red-100 text-red-800',
      pending: 'bg-gray-100 text-gray-800',
    };
    return colors[status] || 'bg-gray-100 text-gray-800';
  };

  const getStatusLabel = (status) => {
    const labels = {
      uploaded: 'Загружен',
      processing: 'Обрабатывается',
      completed: 'Завершен',
      failed: 'Ошибка',
      pending: 'Ожидает',
    };
    return labels[status] || status;
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  if (files.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500">
        <p>Нет загруженных файлов</p>
        <p className="text-sm mt-2">Загрузите файлы для тестирования</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {files.map((fileItem, index) => {
        const isProcessing = processingFiles.has(fileItem.contractId || index);
        // Для восстановленных файлов без объекта File нельзя обработать заново
        const hasFileObject = fileItem.file !== undefined;
        // Можно обработать через upload для новых файлов
        const canProcess = hasFileObject && !fileItem.contractId && (fileItem.status === 'uploaded' || fileItem.status === 'pending' || fileItem.status === 'failed');
        // Можно переобработать через process-contract для уже обработанных файлов
        const canReprocess = fileItem.contractId && !isProcessing && (fileItem.status === 'completed' || fileItem.status === 'validation_passed' || fileItem.status === 'validation_failed' || fileItem.status === 'failed');
        // Можно просмотреть результаты для завершенных файлов
        const canView = (fileItem.status === 'completed' || fileItem.status === 'validation_passed' || fileItem.status === 'validation_failed') && fileItem.contractId && !isProcessing;

        return (
          <div
            key={index}
            className="bg-white rounded-lg border border-gray-200 p-4 hover:shadow-md transition-shadow"
          >
            <div className="flex items-center justify-between">
              <div className="flex-1">
                <div className="flex items-center space-x-3">
                  <div className="flex-shrink-0">
                    <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                      <span className="text-blue-600 text-lg">
                        {(fileItem.file?.name || fileItem.fileName || '').endsWith('.docx') ? '📄' : '📄'}
                      </span>
                    </div>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {fileItem.file?.name || fileItem.fileName || 'Неизвестный файл'}
                    </p>
                    <div className="flex items-center space-x-4 mt-1">
                      <span className="text-xs text-gray-500">
                        {formatFileSize(fileItem.file?.size || fileItem.fileSize || 0)}
                      </span>
                      <span
                        className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getStatusColor(
                          fileItem.status
                        )}`}
                      >
                        {getStatusLabel(fileItem.status)}
                      </span>
                      {fileItem.contractId && (
                        <span className="text-xs text-gray-500">
                          ID: {fileItem.contractId}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
              <div className="flex items-center space-x-2 ml-4">
                {isProcessing && (
                  <div className="flex items-center space-x-2">
                    <LoadingSpinner size="sm" />
                    <span className="text-sm text-gray-600">Обработка...</span>
                  </div>
                )}
                {!isProcessing && canProcess && (
                  <button
                    onClick={() => onProcessFile(index)}
                    className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors"
                  >
                    Обработать
                  </button>
                )}
                {!isProcessing && canReprocess && (
                  <button
                    onClick={() => onReprocessFile(index)}
                    className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors"
                  >
                    Переобработать
                  </button>
                )}
                {!isProcessing && canView && (
                  <button
                    onClick={() => onViewResults(index)}
                    className="px-4 py-2 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 transition-colors"
                  >
                    Просмотреть результаты
                  </button>
                )}
                {fileItem.status === 'failed' && fileItem.error && (
                  <div className="text-xs text-red-600 max-w-xs truncate" title={fileItem.error}>
                    {fileItem.error}
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default TestFileList;
