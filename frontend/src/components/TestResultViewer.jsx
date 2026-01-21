import React, { useState, useEffect } from 'react';
import { getContractRawText, getContractData, getLLMInfo } from '../services/contractService';
import LoadingSpinner from './LoadingSpinner';
import DataViewer from './DataViewer';

const TestResultViewer = ({ contractId, contractStatus, onClose }) => {
  const [activeTab, setActiveTab] = useState('text');
  const [rawText, setRawText] = useState(null);
  const [contractData, setContractData] = useState(null);
  const [llmInfo, setLlmInfo] = useState(null);
  const [loadingText, setLoadingText] = useState(false);
  const [loadingData, setLoadingData] = useState(false);
  const [loadingLLMInfo, setLoadingLLMInfo] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (contractId && activeTab === 'text' && !rawText && !loadingText) {
      loadRawText();
    }
    if (contractId && activeTab === 'data' && !contractData && !loadingData) {
      loadContractData();
    }
    if (contractId && activeTab === 'llm' && !llmInfo && !loadingLLMInfo) {
      loadLLMInfo();
    }
  }, [contractId, activeTab]);

  const loadRawText = async () => {
    setLoadingText(true);
    setError(null);
    try {
      const response = await getContractRawText(contractId);
      setRawText(response);
    } catch (err) {
      setError(err.response?.data?.detail || 'Ошибка при загрузке текста документа');
    } finally {
      setLoadingText(false);
    }
  };

  const loadContractData = async () => {
    setLoadingData(true);
    setError(null);
    try {
      const data = await getContractData(contractId);
      setContractData(data);
    } catch (err) {
      if (err.response?.status !== 404) {
        setError(err.response?.data?.detail || 'Ошибка при загрузке данных контракта');
      }
    } finally {
      setLoadingData(false);
    }
  };

  const loadLLMInfo = async () => {
    setLoadingLLMInfo(true);
    setError(null);
    try {
      const info = await getLLMInfo(contractId);
      setLlmInfo(info);
    } catch (err) {
      if (err.response?.status !== 404) {
        setError(err.response?.data?.detail || 'Ошибка при загрузке информации о запросах LLM');
      }
    } finally {
      setLoadingLLMInfo(false);
    }
  };

  const getStatusColor = (status) => {
    const colors = {
      completed: 'bg-green-100 text-green-800',
      failed: 'bg-red-100 text-red-800',
      validation_failed: 'bg-red-100 text-red-800',
      validation_passed: 'bg-green-100 text-green-800',
      processing: 'bg-blue-100 text-blue-800',
      pending: 'bg-yellow-100 text-yellow-800',
    };
    return colors[status] || 'bg-gray-100 text-gray-800';
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-6xl w-full mx-4 max-h-[90vh] overflow-hidden flex flex-col">
        {/* Заголовок */}
        <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
          <div>
            <h3 className="text-xl font-semibold text-gray-900">
              Результаты обработки документа #{contractId}
            </h3>
            {contractStatus && (
              <span
                className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full mt-2 ${getStatusColor(
                  contractStatus.status
                )}`}
              >
                {contractStatus.status}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Вкладки */}
        <div className="border-b border-gray-200">
          <nav className="flex space-x-8 px-6" aria-label="Tabs">
            <button
              onClick={() => setActiveTab('text')}
              className={`py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'text'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Текст документа
            </button>
            <button
              onClick={() => setActiveTab('data')}
              className={`py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'data'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Извлеченные данные
            </button>
            <button
              onClick={() => setActiveTab('llm')}
              className={`py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'llm'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Запросы LLM
            </button>
            <button
              onClick={() => setActiveTab('status')}
              className={`py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'status'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Статус
            </button>
          </nav>
        </div>

        {/* Содержимое */}
        <div className="px-6 py-4 overflow-y-auto flex-1">
          {error && (
            <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-800">{error}</p>
            </div>
          )}

          {activeTab === 'text' && (
            <div>
              {loadingText ? (
                <div className="flex justify-center items-center py-12">
                  <LoadingSpinner size="md" />
                </div>
              ) : rawText ? (
                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <div className="text-sm text-gray-600">
                      Метод извлечения: <span className="font-medium">{rawText.extraction_method || 'document_processor'}</span>
                    </div>
                    <div className="text-sm text-gray-600">
                      Длина текста: <span className="font-medium">{rawText.text_length?.toLocaleString('ru-RU')} символов</span>
                    </div>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                    <div className="text-sm font-medium text-gray-700 mb-2">
                      Полный распознанный текст:
                    </div>
                    <div className="bg-white rounded p-4 text-sm text-gray-800 font-mono whitespace-pre-wrap break-words max-h-[60vh] overflow-y-auto border border-gray-200">
                      <pre className="whitespace-pre-wrap break-words">{rawText.raw_text || 'Текст не найден'}</pre>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-center py-12 text-gray-500">
                  Текст документа недоступен
                </div>
              )}
            </div>
          )}

          {activeTab === 'data' && (
            <div>
              {loadingData ? (
                <div className="flex justify-center items-center py-12">
                  <LoadingSpinner size="md" />
                </div>
              ) : contractData ? (
                <DataViewer data={contractData} title="Извлеченные данные контракта" />
              ) : (
                <div className="text-center py-12 text-gray-500">
                  Данные контракта еще не извлечены
                </div>
              )}
            </div>
          )}

          {activeTab === 'llm' && (
            <div>
              {loadingLLMInfo ? (
                <div className="flex justify-center items-center py-12">
                  <LoadingSpinner size="md" />
                </div>
              ) : llmInfo && llmInfo.requests && llmInfo.requests.length > 0 ? (
                <div className="space-y-6">
                  <div className="text-sm text-gray-600">
                    Всего запросов: {llmInfo.total_requests}
                  </div>
                  {llmInfo.requests.map((request, index) => (
                    <div key={index} className="border border-gray-200 rounded-lg p-4">
                      <div className="flex justify-between items-start mb-3">
                        <div>
                          <h4 className="font-semibold text-gray-900">
                            Запрос #{index + 1}
                            {request.request_type === 'chunk' && (
                              <span className="ml-2 text-sm text-gray-600">
                                (Чанк {request.chunk_index} из {request.total_chunks})
                              </span>
                            )}
                            {request.request_type === 'aggregation' && (
                              <span className="ml-2 text-sm text-gray-600">
                                (Агрегация результатов)
                              </span>
                            )}
                          </h4>
                          <div className="text-sm text-gray-600 mt-1">
                            Статус: <span className={`font-medium ${request.status === 'success' ? 'text-green-600' : 'text-red-600'}`}>
                              {request.status === 'success' ? 'Успешно' : 'Ошибка'}
                            </span>
                          </div>
                          {request.timestamp && (
                            <div className="text-xs text-gray-500 mt-1">
                              Время: {new Date(request.timestamp).toLocaleString('ru-RU')}
                            </div>
                          )}
                        </div>
                      </div>
                      
                      <div className="space-y-3">
                        <div>
                          <div className="text-sm font-medium text-gray-700 mb-1">
                            Полный запрос к LLM:
                          </div>
                          <div className="bg-gray-50 rounded p-3 text-sm text-gray-800 font-mono whitespace-pre-wrap break-words max-h-96 overflow-y-auto border border-gray-200">
                            <pre className="whitespace-pre-wrap break-words">{request.request_text || request.request_text_preview || 'Нет данных'}</pre>
                          </div>
                          <div className="text-xs text-gray-500 mt-1">
                            Размер: {request.request_size?.toLocaleString('ru-RU')} символов
                            {request.request_tokens_estimate && ` (~${request.request_tokens_estimate} токенов)`}
                          </div>
                        </div>
                        
                        {request.status === 'success' && request.response_data && (
                          <div>
                            <div className="text-sm font-medium text-gray-700 mb-1">
                              Ответ LLM:
                            </div>
                            <div className="bg-green-50 rounded p-3 text-sm text-gray-800 max-h-60 overflow-y-auto">
                              <pre className="whitespace-pre-wrap break-words">
                                {JSON.stringify(request.response_data, null, 2)}
                              </pre>
                            </div>
                            {request.response_size && (
                              <div className="text-xs text-gray-500 mt-1">
                                Размер ответа: {request.response_size?.toLocaleString('ru-RU')} символов
                              </div>
                            )}
                          </div>
                        )}
                        
                        {request.status === 'error' && request.error && (
                          <div>
                            <div className="text-sm font-medium text-red-700 mb-1">
                              Ошибка:
                            </div>
                            <div className="bg-red-50 rounded p-3 text-sm text-red-800">
                              {request.error}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-12 text-gray-500">
                  Информация о запросах LLM недоступна
                </div>
              )}
            </div>
          )}

          {activeTab === 'status' && contractStatus && (
            <div className="space-y-4">
              <div className="bg-white rounded-lg border border-gray-200 p-6">
                <h4 className="text-lg font-semibold text-gray-900 mb-4">
                  Информация о статусе обработки
                </h4>
                <div className="space-y-3">
                  <div>
                    <span className="text-sm font-medium text-gray-600">Статус:</span>
                    <span className={`ml-2 inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getStatusColor(
                      contractStatus.status
                    )}`}>
                      {contractStatus.status}
                    </span>
                  </div>
                  {contractStatus.created_at && (
                    <div>
                      <span className="text-sm font-medium text-gray-600">Создан:</span>
                      <span className="ml-2 text-gray-900">
                        {new Date(contractStatus.created_at).toLocaleString('ru-RU')}
                      </span>
                    </div>
                  )}
                  {contractStatus.processing_started_at && (
                    <div>
                      <span className="text-sm font-medium text-gray-600">Начало обработки:</span>
                      <span className="ml-2 text-gray-900">
                        {new Date(contractStatus.processing_started_at).toLocaleString('ru-RU')}
                      </span>
                    </div>
                  )}
                  {contractStatus.processing_completed_at && (
                    <div>
                      <span className="text-sm font-medium text-gray-600">Завершение обработки:</span>
                      <span className="ml-2 text-gray-900">
                        {new Date(contractStatus.processing_completed_at).toLocaleString('ru-RU')}
                      </span>
                    </div>
                  )}
                  {contractStatus.error_message && (
                    <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg">
                      <span className="text-sm font-medium text-red-800">Ошибка:</span>
                      <span className="ml-2 text-red-700">{contractStatus.error_message}</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Футер */}
        <div className="px-6 py-4 border-t border-gray-200 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors"
          >
            Закрыть
          </button>
        </div>
      </div>
    </div>
  );
};

export default TestResultViewer;
