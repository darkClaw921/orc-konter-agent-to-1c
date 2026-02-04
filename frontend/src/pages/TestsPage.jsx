import React, { useState, useRef, useEffect } from 'react';
import { useDispatch } from 'react-redux';
import { uploadContract, getContractStatus, processContractForTests, testMCP1C } from '../services/contractService';
import { addNotification } from '../store/slices/uiSlice';
import TestFileList from '../components/TestFileList';
import TestResultViewer from '../components/TestResultViewer';
import LoadingSpinner from '../components/LoadingSpinner';

const STORAGE_KEY = 'tests_page_files';

// Статусы, при которых файл считается в обработке
const PROCESSING_STATES = [
  'uploaded',
  'processing',
  'document_loaded',
  'text_extracted',
  'data_extracted',
  'services_extracted',
  'checking_1c',
  'creating_in_1c',
];

const isProcessingState = (status) => PROCESSING_STATES.includes(status);

const TestsPage = () => {
  const dispatch = useDispatch();
  const fileInputRef = useRef(null);
  const [files, setFiles] = useState([]);
  const [isDragging, setIsDragging] = useState(false);
  const [processingFiles, setProcessingFiles] = useState(new Set());
  const [selectedFileIndex, setSelectedFileIndex] = useState(null);
  const [showResults, setShowResults] = useState(false);
  const [contractStatus, setContractStatus] = useState(null);
  const [isLoadingFromStorage, setIsLoadingFromStorage] = useState(true);
  const [isTestingMCP, setIsTestingMCP] = useState(false);
  const [mcpTestResult, setMcpTestResult] = useState(null);

  const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

  // Сохранение файлов в localStorage
  const saveFilesToStorage = (filesToSave) => {
    try {
      const filesData = filesToSave
        .filter((f) => f.contractId !== null) // Сохраняем только файлы с contractId (загруженные на сервер)
        .map((f) => ({
          fileName: f.file?.name || f.fileName,
          fileSize: f.file?.size || f.fileSize,
          contractId: f.contractId,
          status: f.status,
          error: f.error || null,
        }));
      localStorage.setItem(STORAGE_KEY, JSON.stringify(filesData));
    } catch (error) {
      console.error('Ошибка при сохранении файлов в localStorage:', error);
    }
  };

  // Загрузка файлов из localStorage
  const loadFilesFromStorage = async () => {
    try {
      const storedData = localStorage.getItem(STORAGE_KEY);
      if (!storedData) {
        setIsLoadingFromStorage(false);
        return [];
      }

      const filesData = JSON.parse(storedData);
      if (!Array.isArray(filesData) || filesData.length === 0) {
        setIsLoadingFromStorage(false);
        return [];
      }

      // Восстанавливаем файлы и обновляем их статусы через API
      const restoredFiles = await Promise.all(
        filesData.map(async (fileData) => {
          try {
            // Проверяем актуальный статус через API
            const status = await getContractStatus(fileData.contractId);
            const currentStatus = status.status;
            
            return {
              fileName: fileData.fileName,
              fileSize: fileData.fileSize,
              contractId: fileData.contractId,
              status: currentStatus,
              error: status.error_message || fileData.error || null,
              rawText: null,
              contractData: null,
            };
          } catch (error) {
            // Если контракт не найден, помечаем как failed
            return {
              fileName: fileData.fileName,
              fileSize: fileData.fileSize,
              contractId: fileData.contractId,
              status: 'failed',
              error: 'Контракт не найден на сервере',
              rawText: null,
              contractData: null,
            };
          }
        })
      );

      setIsLoadingFromStorage(false);
      return restoredFiles;
    } catch (error) {
      console.error('Ошибка при загрузке файлов из localStorage:', error);
      setIsLoadingFromStorage(false);
      return [];
    }
  };

  // Загрузка файлов при монтировании компонента
  useEffect(() => {
    const loadFiles = async () => {
      const restoredFiles = await loadFilesFromStorage();
      if (restoredFiles.length > 0) {
        setFiles(restoredFiles);
        // Проверяем, есть ли файлы в процессе обработки
        const processingIds = restoredFiles
          .filter((f) => isProcessingState(f.status) || f.status === 'pending')
          .map((f) => f.contractId)
          .filter(Boolean);
        if (processingIds.length > 0) {
          setProcessingFiles(new Set(processingIds));
        }
      }
    };
    loadFiles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Сохранение файлов при изменении списка
  useEffect(() => {
    if (!isLoadingFromStorage) {
      saveFilesToStorage(files);
    }
  }, [files, isLoadingFromStorage]);

  const validateFile = (file) => {
    const validExtensions = ['.docx', '.pdf'];
    const fileExt = '.' + file.name.split('.').pop().toLowerCase();
    
    if (!validExtensions.includes(fileExt)) {
      return { valid: false, error: 'Поддерживаются только файлы формата .docx и .pdf' };
    }
    if (file.size > MAX_FILE_SIZE) {
      return { valid: false, error: 'Размер файла не должен превышать 50MB' };
    }
    return { valid: true };
  };

  const handleFilesAdded = (newFiles) => {
    const validFiles = [];
    const errors = [];

    Array.from(newFiles).forEach((file) => {
      const validation = validateFile(file);
      if (validation.valid) {
        validFiles.push({
          file,
          contractId: null,
          status: 'uploaded',
          rawText: null,
          contractData: null,
          error: null,
        });
      } else {
        errors.push({ file: file.name, error: validation.error });
      }
    });

    if (errors.length > 0) {
      errors.forEach(({ file, error }) => {
        dispatch(
          addNotification({
            type: 'error',
            message: `${file}: ${error}`,
          })
        );
      });
    }

    if (validFiles.length > 0) {
      setFiles((prev) => [...prev, ...validFiles]);
      dispatch(
        addNotification({
          type: 'success',
          message: `Добавлено файлов: ${validFiles.length}`,
        })
      );
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

    const droppedFiles = e.dataTransfer.files;
    if (droppedFiles.length > 0) {
      handleFilesAdded(droppedFiles);
    }
  };

  const handleFileSelect = (e) => {
    const selectedFiles = e.target.files;
    if (selectedFiles.length > 0) {
      handleFilesAdded(selectedFiles);
    }
    // Сброс input для возможности повторного выбора тех же файлов
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const pollContractStatus = async (contractId, fileIndex) => {
    const maxAttempts = 120; // 2 минуты при интервале 1 секунда
    let attempts = 0;

    const poll = async () => {
      try {
        const status = await getContractStatus(contractId);
        
        setFiles((prev) => {
          const updated = [...prev];
          updated[fileIndex] = {
            ...updated[fileIndex],
            status: status.status,
            error: status.error_message || null,
          };
          return updated;
        });

        if (status.status === 'completed' || status.status === 'validation_passed' || status.status === 'validation_failed') {
          setFiles((prev) => {
            const updated = [...prev];
            updated[fileIndex] = {
              ...updated[fileIndex],
              status: status.status === 'validation_passed' || status.status === 'validation_failed' ? status.status : 'completed',
            };
            return updated;
          });
          setProcessingFiles((prev) => {
            const newSet = new Set(prev);
            newSet.delete(contractId);
            return newSet;
          });
          dispatch(
            addNotification({
              type: 'success',
              message: `Обработка файла "${files[fileIndex].file?.name || files[fileIndex].fileName || 'файл'}" завершена`,
            })
          );
          return;
        }

        if (status.status === 'failed') {
          setFiles((prev) => {
            const updated = [...prev];
            updated[fileIndex] = {
              ...updated[fileIndex],
              status: 'failed',
              error: status.error_message || 'Ошибка обработки',
            };
            return updated;
          });
          setProcessingFiles((prev) => {
            const newSet = new Set(prev);
            newSet.delete(contractId);
            return newSet;
          });
          dispatch(
            addNotification({
              type: 'error',
              message: `Ошибка обработки файла "${files[fileIndex].file?.name || files[fileIndex].fileName || 'файл'}"`,
            })
          );
          return;
        }

        attempts++;
        if (attempts < maxAttempts) {
          setTimeout(poll, 1000); // Проверяем каждую секунду
        } else {
          setProcessingFiles((prev) => {
            const newSet = new Set(prev);
            newSet.delete(contractId);
            return newSet;
          });
          dispatch(
            addNotification({
              type: 'warning',
              message: `Превышено время ожидания обработки файла "${files[fileIndex].file?.name || files[fileIndex].fileName || 'файл'}"`,
            })
          );
        }
      } catch (error) {
        setProcessingFiles((prev) => {
          const newSet = new Set(prev);
          newSet.delete(contractId);
          return newSet;
        });
        dispatch(
          addNotification({
            type: 'error',
            message: `Ошибка при проверке статуса: ${error.response?.data?.detail || error.message}`,
          })
        );
      }
    };

    setTimeout(poll, 1000);
  };

  // Возобновление опроса статуса для восстановленных файлов в обработке
  useEffect(() => {
    if (!isLoadingFromStorage && files.length > 0) {
      files.forEach((file, index) => {
        if ((isProcessingState(file.status) || file.status === 'pending') && file.contractId && !processingFiles.has(file.contractId)) {
          setProcessingFiles((prev) => new Set(prev).add(file.contractId));
          setTimeout(() => {
            pollContractStatus(file.contractId, index);
          }, 500);
        }
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoadingFromStorage]);

  const handleProcessFile = async (fileIndex) => {
    const fileItem = files[fileIndex];
    if (!fileItem || fileItem.status === 'processing') {
      return;
    }

    setFiles((prev) => {
      const updated = [...prev];
      updated[fileIndex] = {
        ...updated[fileIndex],
        status: 'processing',
      };
      return updated;
    });

    try {
      const response = await uploadContract(fileItem.file, (progress) => {
        // Можно добавить отображение прогресса загрузки
      });

      setFiles((prev) => {
        const updated = [...prev];
        updated[fileIndex] = {
          ...updated[fileIndex],
          contractId: response.contract_id,
          status: 'processing',
        };
        return updated;
      });

      setProcessingFiles((prev) => new Set(prev).add(response.contract_id));

      dispatch(
        addNotification({
          type: 'success',
          message: `Файл "${fileItem.file?.name || fileItem.fileName || 'файл'}" загружен и поставлен в очередь обработки`,
        })
      );

      // Начинаем опрос статуса
      pollContractStatus(response.contract_id, fileIndex);
    } catch (error) {
      setFiles((prev) => {
        const updated = [...prev];
        updated[fileIndex] = {
          ...updated[fileIndex],
          status: 'failed',
          error: error.response?.data?.detail || 'Ошибка при загрузке файла',
        };
        return updated;
      });
      dispatch(
        addNotification({
          type: 'error',
          message: `Ошибка при загрузке файла "${fileItem.file?.name || fileItem.fileName || 'файл'}": ${error.response?.data?.detail || error.message}`,
        })
      );
    }
  };

  const handleReprocessFile = async (fileIndex) => {
    const fileItem = files[fileIndex];
    if (!fileItem || !fileItem.contractId || fileItem.status === 'processing') {
      return;
    }

    setFiles((prev) => {
      const updated = [...prev];
      updated[fileIndex] = {
        ...updated[fileIndex],
        status: 'processing',
      };
      return updated;
    });

    try {
      const response = await processContractForTests(fileItem.contractId);

      setFiles((prev) => {
        const updated = [...prev];
        updated[fileIndex] = {
          ...updated[fileIndex],
          status: 'processing',
        };
        return updated;
      });

      setProcessingFiles((prev) => new Set(prev).add(fileItem.contractId));

      dispatch(
        addNotification({
          type: 'success',
          message: `Файл "${fileItem.file?.name || fileItem.fileName || 'файл'}" поставлен в очередь повторной обработки`,
        })
      );

      // Начинаем опрос статуса
      pollContractStatus(fileItem.contractId, fileIndex);
    } catch (error) {
      setFiles((prev) => {
        const updated = [...prev];
        updated[fileIndex] = {
          ...updated[fileIndex],
          status: 'failed',
          error: error.response?.data?.detail || 'Ошибка при повторной обработке файла',
        };
        return updated;
      });
      dispatch(
        addNotification({
          type: 'error',
          message: `Ошибка при повторной обработке файла "${fileItem.file?.name || fileItem.fileName || 'файл'}": ${error.response?.data?.detail || error.message}`,
        })
      );
    }
  };

  const handleProcessAll = async () => {
    const filesToProcess = files.filter(
      (f) => {
        // Файлы, которые можно обработать через upload
        const canProcessViaUpload = f.file && (f.status === 'uploaded' || f.status === 'pending' || f.status === 'failed');
        // Файлы, которые можно переобработать через process-contract
        const canReprocess = f.contractId && (f.status === 'completed' || f.status === 'validation_passed' || f.status === 'validation_failed');
        return canProcessViaUpload || canReprocess;
      }
    );

    if (filesToProcess.length === 0) {
      dispatch(
        addNotification({
          type: 'info',
          message: 'Нет файлов для обработки',
        })
      );
      return;
    }

    for (let i = 0; i < files.length; i++) {
      const fileItem = files[i];
      // Обрабатываем через upload для новых файлов
      if (fileItem.file && (fileItem.status === 'uploaded' || fileItem.status === 'pending' || fileItem.status === 'failed')) {
        await handleProcessFile(i);
        // Небольшая задержка между обработкой файлов
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
      // Переобрабатываем через process-contract для завершенных файлов
      else if (fileItem.contractId && (fileItem.status === 'completed' || fileItem.status === 'validation_passed' || fileItem.status === 'validation_failed')) {
        await handleReprocessFile(i);
        // Небольшая задержка между обработкой файлов
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
    }
  };

  const handleViewResults = async (fileIndex) => {
    const fileItem = files[fileIndex];
    if (!fileItem || !fileItem.contractId) {
      return;
    }

    try {
      const status = await getContractStatus(fileItem.contractId);
      setContractStatus(status);
      setSelectedFileIndex(fileIndex);
      setShowResults(true);
    } catch (error) {
      dispatch(
        addNotification({
          type: 'error',
          message: `Ошибка при загрузке статуса: ${error.response?.data?.detail || error.message}`,
        })
      );
    }
  };

  const handleRemoveFile = (fileIndex) => {
    setFiles((prev) => {
      const updated = prev.filter((_, index) => index !== fileIndex);
      return updated;
    });
  };

  const handleClearAll = () => {
    setFiles([]);
    setProcessingFiles(new Set());
    localStorage.removeItem(STORAGE_KEY);
  };

  const handleTestMCP1C = async () => {
    setIsTestingMCP(true);
    setMcpTestResult(null);
    
    try {
      const result = await testMCP1C();
      setMcpTestResult(result);
      
      if (result.success) {
        if (result.counterparty) {
          dispatch(
            addNotification({
              type: 'success',
              message: `MCP 1С работает! Получен контрагент: ${result.counterparty.Наименование || result.counterparty.ПолноеНаименование || 'Без названия'}`,
            })
          );
        } else {
          dispatch(
            addNotification({
              type: 'info',
              message: result.message || 'MCP 1С работает, но контрагенты не найдены',
            })
          );
        }
      } else {
        dispatch(
          addNotification({
            type: 'error',
            message: `Ошибка MCP 1С: ${result.message || result.error || 'Неизвестная ошибка'}`,
          })
        );
      }
    } catch (error) {
      setMcpTestResult({
        success: false,
        error: error.response?.data?.detail || error.message || 'Ошибка при проверке MCP 1С',
      });
      dispatch(
        addNotification({
          type: 'error',
          message: `Ошибка при проверке MCP 1С: ${error.response?.data?.detail || error.message}`,
        })
      );
    } finally {
      setIsTestingMCP(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Тесты</h1>
        <p className="text-gray-600 mt-2">
          Загрузите файлы для тестирования обработки документов и просмотра результатов распознавания
        </p>
        <div className="mt-4">
          <button
            onClick={handleTestMCP1C}
            disabled={isTestingMCP}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center"
          >
            {isTestingMCP ? (
              <>
                <LoadingSpinner size="sm" />
                <span className="ml-2">Проверка MCP 1С...</span>
              </>
            ) : (
              'Проверить работу MCP 1С'
            )}
          </button>
        </div>
        {mcpTestResult && (
          <div className={`mt-4 p-4 rounded-lg border ${
            mcpTestResult.success 
              ? 'bg-green-50 border-green-200' 
              : 'bg-red-50 border-red-200'
          }`}>
            <h3 className={`font-semibold mb-2 ${
              mcpTestResult.success ? 'text-green-800' : 'text-red-800'
            }`}>
              {mcpTestResult.success ? '✓ MCP 1С работает' : '✗ Ошибка MCP 1С'}
            </h3>
            <p className={`text-sm mb-2 ${
              mcpTestResult.success ? 'text-green-700' : 'text-red-700'
            }`}>
              {mcpTestResult.message}
            </p>
            {mcpTestResult.counterparty && (
              <div className="mt-3 p-3 bg-white rounded border border-gray-200">
                <h4 className="font-medium text-gray-900 mb-2">Данные контрагента:</h4>
                <pre className="text-xs overflow-auto max-h-64 bg-gray-50 p-2 rounded">
                  {JSON.stringify(mcpTestResult.counterparty, null, 2)}
                </pre>
              </div>
            )}
            {mcpTestResult.error && (
              <p className="text-sm text-red-600 mt-2">
                Ошибка: {mcpTestResult.error}
              </p>
            )}
          </div>
        )}
      </div>

      {/* Область загрузки файлов */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
          isDragging
            ? 'border-blue-500 bg-blue-50'
            : 'border-gray-300 hover:border-gray-400'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".docx,.pdf"
          onChange={handleFileSelect}
          className="hidden"
        />
        <div className="space-y-4">
          <div className="text-4xl">📄</div>
          <div>
            <p className="text-lg font-medium text-gray-700">
              Перетащите файлы сюда или нажмите для выбора
            </p>
            <p className="text-sm text-gray-500 mt-2">
              Поддерживаются форматы: DOCX, PDF (максимум 50MB)
            </p>
          </div>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            Выбрать файлы
          </button>
        </div>
      </div>

      {/* Индикатор загрузки из хранилища */}
      {isLoadingFromStorage && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <div className="flex items-center">
            <LoadingSpinner size="sm" />
            <span className="ml-3 text-sm text-blue-700">Загрузка сохраненных файлов...</span>
          </div>
        </div>
      )}

      {/* Управление файлами */}
      {files.length > 0 && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-gray-900">
              Загруженные файлы ({files.length})
            </h2>
            <div className="flex space-x-2">
              <button
                onClick={handleProcessAll}
                disabled={files.every((f) => f.status === 'processing')}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:bg-gray-400 disabled:cursor-not-allowed"
              >
                Обработать все
              </button>
              <button
                onClick={handleClearAll}
                disabled={processingFiles.size > 0}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors disabled:bg-gray-400 disabled:cursor-not-allowed"
              >
                Очистить все
              </button>
            </div>
          </div>
          <TestFileList
            files={files}
            onProcessFile={handleProcessFile}
            onViewResults={handleViewResults}
            onReprocessFile={handleReprocessFile}
            processingFiles={processingFiles}
          />
        </div>
      )}

      {/* Модальное окно с результатами */}
      {showResults && selectedFileIndex !== null && files[selectedFileIndex]?.contractId && (
        <TestResultViewer
          contractId={files[selectedFileIndex].contractId}
          contractStatus={contractStatus}
          onClose={() => {
            setShowResults(false);
            setSelectedFileIndex(null);
            setContractStatus(null);
          }}
        />
      )}
    </div>
  );
};

export default TestsPage;
