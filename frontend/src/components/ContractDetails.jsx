import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useDispatch } from 'react-redux';
import { getContractData, getContractStatus, retryContract, getLLMInfo, get1CInfo, refreshServices } from '../services/contractService';
import { addNotification } from '../store/slices/uiSlice';
import DataViewer from './DataViewer';
import ValidationResults from './ValidationResults';
import LoadingSpinner from './LoadingSpinner';

const ContractDetails = () => {
  const dispatch = useDispatch();
  const { id } = useParams();
  const navigate = useNavigate();
  const [contractData, setContractData] = useState(null);
  const [contractStatus, setContractStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [validationResults, setValidationResults] = useState(null);
  const [showLLMInfo, setShowLLMInfo] = useState(false);
  const [llmInfo, setLlmInfo] = useState(null);
  const [loadingLLMInfo, setLoadingLLMInfo] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');
  const [onecInfo, setOnecInfo] = useState(null);
  const [loadingOnecInfo, setLoadingOnecInfo] = useState(false);
  const [allServices, setAllServices] = useState(null);
  const [loadingServices, setLoadingServices] = useState(false);

  useEffect(() => {
    const loadContractDetails = async () => {
      try {
        setLoading(true);
        
        // Сначала загружаем статус контракта
        const status = await getContractStatus(id);
        setContractStatus(status);

        // Загружаем данные только если контракт обработан
        // Статусы, при которых данные могут быть доступны:
        const dataAvailableStatuses = [
          'completed',
          'validation_passed',
          'validation_failed',
          'failed'
        ];
        
        if (dataAvailableStatuses.includes(status.status)) {
          try {
            const data = await getContractData(id);
            setContractData(data);
            // Загружаем услуги из данных контракта, если они есть
            if (data && data.all_services && Array.isArray(data.all_services) && data.all_services.length > 0) {
              setAllServices(data.all_services);
            }
          } catch (dataError) {
            // Если данные не найдены (404), это нормально для некоторых статусов
            if (dataError.response?.status === 404) {
              // Данные еще не извлечены или контракт не обработан
              setContractData(null);
            } else {
              // Другая ошибка при загрузке данных
              console.error('Ошибка при загрузке данных контракта:', dataError);
            }
          }
        }

        // Здесь можно загрузить результаты валидации, если есть отдельный endpoint
        // const validation = await getValidationResults(id);
        // setValidationResults(validation);
      } catch (error) {
        if (error.response?.status === 404) {
          dispatch(addNotification({
            type: 'error',
            message: 'Контракт не найден',
          }));
          navigate('/');
        } else {
          dispatch(addNotification({
            type: 'error',
            message: 'Ошибка при загрузке данных контракта',
          }));
        }
      } finally {
        setLoading(false);
      }
    };

    if (id) {
      loadContractDetails();
    }
  }, [id, navigate, dispatch]);

  useEffect(() => {
    const loadOnecInfo = async () => {
      if (activeTab === 'onec' && !onecInfo && !loadingOnecInfo && id) {
        setLoadingOnecInfo(true);
        try {
          const info = await get1CInfo(id);
          setOnecInfo(info);
        } catch (error) {
          console.error('Ошибка при загрузке информации о работе с 1С:', error);
          // Устанавливаем объект с ошибкой для отображения
          setOnecInfo({
            contract_id: parseInt(id),
            error_from_1c: error.response?.data?.detail || error.message || 'Ошибка при загрузке информации о работе с 1С',
            was_found: false,
            was_created: false
          });
          if (error.response?.status !== 404) {
            dispatch(addNotification({
              type: 'error',
              message: 'Ошибка при загрузке информации о работе с 1С',
            }));
          }
        } finally {
          setLoadingOnecInfo(false);
        }
      }
    };

    loadOnecInfo();
  }, [activeTab, id, onecInfo, loadingOnecInfo, dispatch]);

  const handleApprove = () => {
    // TODO: Реализовать утверждение контракта
    dispatch(addNotification({
      type: 'info',
      message: 'Функция утверждения будет реализована позже',
    }));
  };

  const handleSendTo1C = () => {
    // TODO: Реализовать отправку в 1С
    dispatch(addNotification({
      type: 'info',
      message: 'Функция отправки в 1С будет реализована позже',
    }));
  };

  const handleRetry = async () => {
    try {
      await retryContract(id);
      dispatch(addNotification({
        type: 'success',
        message: 'Обработка контракта перезапущена',
      }));
      // Перезагружаем данные контракта
      const status = await getContractStatus(id);
      setContractStatus(status);
    } catch (error) {
      dispatch(addNotification({
        type: 'error',
        message: 'Ошибка при повторной обработке контракта',
      }));
    }
  };

  const handleShowLLMInfo = async () => {
    setShowLLMInfo(true);
    setLoadingLLMInfo(true);
    try {
      const info = await getLLMInfo(id);
      setLlmInfo(info);
    } catch (error) {
      dispatch(addNotification({
        type: 'error',
        message: 'Ошибка при загрузке информации о запросах LLM',
      }));
    } finally {
      setLoadingLLMInfo(false);
    }
  };

  const handleRefreshServices = async () => {
    setLoadingServices(true);
    try {
      const result = await refreshServices(id);
      if (result.success) {
        setAllServices(result.services);
        dispatch(addNotification({
          type: 'success',
          message: `Успешно извлечено ${result.services_count} услуг`,
        }));
        // Переключаемся на вкладку услуг
        setActiveTab('services');
      } else {
        dispatch(addNotification({
          type: 'error',
          message: result.error || 'Ошибка при извлечении услуг',
        }));
      }
    } catch (error) {
      dispatch(addNotification({
        type: 'error',
        message: 'Ошибка при обновлении услуг',
      }));
    } finally {
      setLoadingServices(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center py-12">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (!contractStatus) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500">Контракт не найден</p>
      </div>
    );
  }

  // Показываем сообщение, если данные еще не извлечены
  const isProcessing = ['pending', 'processing'].includes(contractStatus.status);
  const dataNotAvailable = !contractData && !isProcessing;

  const getStatusColor = (status) => {
    const colors = {
      completed: 'bg-green-100 text-green-800',
      failed: 'bg-red-100 text-red-800',
      validation_failed: 'bg-red-100 text-red-800',
      validation_passed: 'bg-green-100 text-green-800',
    };
    return colors[status] || 'bg-gray-100 text-gray-800';
  };

  return (
    <div className="space-y-6">
      {/* Заголовок и действия */}
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">
            Детали контракта #{id}
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            Статус:{' '}
            <span
              className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getStatusColor(
                contractStatus.status
              )}`}
            >
              {contractStatus.status}
            </span>
          </p>
        </div>
        <div className="flex space-x-3">
          <button
            onClick={() => navigate(-1)}
            className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors"
          >
            Назад
          </button>
          <button
            onClick={handleShowLLMInfo}
            className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors"
          >
            Инфо
          </button>
          <button
            onClick={handleRefreshServices}
            disabled={loadingServices}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
          >
            {loadingServices ? (
              <>
                <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Загрузка...
              </>
            ) : (
              'Обновить услуги'
            )}
          </button>
          {contractStatus.status === 'failed' && (
            <button
              onClick={handleRetry}
              className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
            >
              Повторить обработку
            </button>
          )}
          {contractStatus.status === 'validation_passed' && (
            <>
              <button
                onClick={handleApprove}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
              >
                Утвердить
              </button>
              <button
                onClick={handleSendTo1C}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                Отправить в 1С
              </button>
            </>
          )}
        </div>
      </div>

      {/* Вкладки */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200">
        <div className="border-b border-gray-200">
          <nav className="flex space-x-8 px-6" aria-label="Tabs">
            {contractData && (
              <>
                <button
                  onClick={() => setActiveTab('overview')}
                  className={`py-4 px-1 border-b-2 font-medium text-sm ${
                    activeTab === 'overview'
                      ? 'border-blue-500 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
                >
                  Обзор
                </button>
                <button
                  onClick={() => setActiveTab('data')}
                  className={`py-4 px-1 border-b-2 font-medium text-sm ${
                    activeTab === 'data'
                      ? 'border-blue-500 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
                >
                  Данные
                </button>
              </>
            )}
            <button
              onClick={() => setActiveTab('onec')}
              className={`py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'onec'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Работа с 1С
            </button>
            <button
              onClick={() => setActiveTab('services')}
              className={`py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'services'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Услуги
              {allServices && allServices.length > 0 && (
                <span className="ml-2 px-2 py-0.5 text-xs bg-purple-100 text-purple-800 rounded-full">
                  {allServices.length}
                </span>
              )}
            </button>
          </nav>
        </div>
      </div>

      {/* Результаты валидации */}
      {validationResults && (
        <ValidationResults results={validationResults} />
      )}

      {/* Сообщение о процессе обработки */}
      {isProcessing && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
          <div className="flex items-center">
            <LoadingSpinner size="sm" />
            <div className="ml-4">
              <h3 className="text-lg font-semibold text-blue-900">
                Обработка контракта
              </h3>
              <p className="text-sm text-blue-700 mt-1">
                Контракт находится в процессе обработки. Данные будут доступны после завершения.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Сообщение об отсутствии данных */}
      {dataNotAvailable && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-yellow-900">
            Данные контракта недоступны
          </h3>
          <p className="text-sm text-yellow-700 mt-1">
            Данные контракта еще не были извлечены или произошла ошибка при обработке.
          </p>
        </div>
      )}

      {/* Основные данные контракта */}
      {contractData && activeTab === 'overview' && (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">
            Информация о контрагенте
          </h3>
          <div className="space-y-3">
            <div>
              <span className="text-sm font-medium text-gray-600">ИНН:</span>
              <span className="ml-2 text-gray-900">{contractData.inn}</span>
            </div>
            {contractData.kpp && (
              <div>
                <span className="text-sm font-medium text-gray-600">КПП:</span>
                <span className="ml-2 text-gray-900">{contractData.kpp}</span>
              </div>
            )}
            <div>
              <span className="text-sm font-medium text-gray-600">
                Полное наименование:
              </span>
              <span className="ml-2 text-gray-900">
                {contractData.full_name}
              </span>
            </div>
            {contractData.short_name && (
              <div>
                <span className="text-sm font-medium text-gray-600">
                  Краткое наименование:
                </span>
                <span className="ml-2 text-gray-900">
                  {contractData.short_name}
                </span>
              </div>
            )}
            <div>
              <span className="text-sm font-medium text-gray-600">
                Тип юридического лица:
              </span>
              <span className="ml-2 text-gray-900">
                {contractData.legal_entity_type}
              </span>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">
            Информация о договоре
          </h3>
          <div className="space-y-3">
            {contractData.contract_name && (
              <div>
                <span className="text-sm font-medium text-gray-600">
                  Наименование договора:
                </span>
                <span className="ml-2 text-gray-900">
                  {contractData.contract_name}
                </span>
              </div>
            )}
            {contractData.contract_number && (
              <div>
                <span className="text-sm font-medium text-gray-600">
                  Номер договора:
                </span>
                <span className="ml-2 text-gray-900">
                  {contractData.contract_number}
                </span>
              </div>
            )}
            {contractData.contract_date && (
              <div>
                <span className="text-sm font-medium text-gray-600">
                  Дата договора:
                </span>
                <span className="ml-2 text-gray-900">
                  {new Date(contractData.contract_date).toLocaleDateString(
                    'ru-RU'
                  )}
                </span>
              </div>
            )}
            {contractData.contract_price && (
              <div>
                <span className="text-sm font-medium text-gray-600">
                  Сумма договора:
                </span>
                <span className="ml-2 text-gray-900">
                  {contractData.contract_price.toLocaleString('ru-RU')} ₽
                </span>
              </div>
            )}
            {contractData.vat_percent !== null && (
              <div>
                <span className="text-sm font-medium text-gray-600">НДС:</span>
                <span className="ml-2 text-gray-900">
                  {contractData.vat_percent}%
                </span>
              </div>
            )}
          </div>
        </div>
      </div>
      )}

      {/* Дополнительные данные */}
      {contractData && activeTab === 'data' && (
        <DataViewer data={contractData} title="Полные данные контракта" />
      )}

      {/* Информация о работе с 1С */}
      {contractData && activeTab === 'onec' && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">
            Информация о работе с 1С
          </h3>
          {loadingOnecInfo ? (
            <div className="flex justify-center items-center py-12">
              <LoadingSpinner size="md" />
            </div>
          ) : onecInfo ? (
            <div className="space-y-6">
              {/* Информация о поиске */}
              <div className="border border-gray-200 rounded-lg p-4">
                <h4 className="text-md font-semibold text-gray-900 mb-3">
                  Поиск контрагента
                </h4>
                <div className="space-y-2">
                  <div>
                    <span className="text-sm font-medium text-gray-600">ИНН для поиска:</span>
                    <span className="ml-2 text-gray-900 font-mono">
                      {onecInfo.searched_inn || 'Не указан'}
                    </span>
                  </div>
                  <div>
                    <span className="text-sm font-medium text-gray-600">Результат поиска:</span>
                    <span className={`ml-2 font-medium ${
                      onecInfo.was_found ? 'text-green-600' : 
                      onecInfo.was_created ? 'text-blue-600' : 
                      'text-gray-600'
                    }`}>
                      {onecInfo.was_found ? 'Контрагент найден в 1С' : 
                       onecInfo.was_created ? 'Контрагент создан в 1С' : 
                       'Контрагент не найден'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Информация о найденном/созданном контрагенте */}
              {(onecInfo.was_found || onecInfo.was_created) && (
                <div className="border border-gray-200 rounded-lg p-4">
                  <h4 className="text-md font-semibold text-gray-900 mb-3">
                    {onecInfo.was_found ? 'Найденный контрагент' : 'Созданный контрагент'}
                  </h4>
                  <div className="space-y-2">
                    {onecInfo.counterparty_uuid && (
                      <div>
                        <span className="text-sm font-medium text-gray-600">UUID в 1С:</span>
                        <span className="ml-2 text-gray-900 font-mono text-xs">
                          {onecInfo.counterparty_uuid}
                        </span>
                      </div>
                    )}
                    {onecInfo.counterparty_name && (
                      <div>
                        <span className="text-sm font-medium text-gray-600">Наименование:</span>
                        <span className="ml-2 text-gray-900">
                          {onecInfo.counterparty_name}
                        </span>
                      </div>
                    )}
                    {onecInfo.status_1c && (
                      <div>
                        <span className="text-sm font-medium text-gray-600">Статус в 1С:</span>
                        <span className={`ml-2 px-2 py-1 text-xs font-semibold rounded-full ${
                          onecInfo.status_1c === 'CREATED' ? 'bg-green-100 text-green-800' :
                          onecInfo.status_1c === 'UPDATED' ? 'bg-blue-100 text-blue-800' :
                          'bg-red-100 text-red-800'
                        }`}>
                          {onecInfo.status_1c}
                        </span>
                      </div>
                    )}
                    {onecInfo.created_in_1c_at && (
                      <div>
                        <span className="text-sm font-medium text-gray-600">Дата создания в 1С:</span>
                        <span className="ml-2 text-gray-900">
                          {new Date(onecInfo.created_in_1c_at).toLocaleString('ru-RU')}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Данные из 1С */}
              {onecInfo.found_counterparty && (
                <div className="border border-gray-200 rounded-lg p-4">
                  <h4 className="text-md font-semibold text-gray-900 mb-3">
                    Данные контрагента из 1С
                  </h4>
                  <div className="bg-gray-50 rounded p-3 text-sm text-gray-800 max-h-96 overflow-y-auto">
                    <pre className="whitespace-pre-wrap break-words">
                      {JSON.stringify(onecInfo.found_counterparty, null, 2)}
                    </pre>
                  </div>
                </div>
              )}

              {/* Ответ от 1С */}
              {onecInfo.response_from_1c && (
                <div className="border border-gray-200 rounded-lg p-4">
                  <h4 className="text-md font-semibold text-gray-900 mb-3">
                    Ответ от 1С
                  </h4>
                  <div className="bg-green-50 rounded p-3 text-sm text-gray-800 max-h-96 overflow-y-auto">
                    <pre className="whitespace-pre-wrap break-words">
                      {JSON.stringify(onecInfo.response_from_1c, null, 2)}
                    </pre>
                  </div>
                </div>
              )}

              {/* Ошибка от 1С */}
              {onecInfo.error_from_1c && (
                <div className="border border-red-200 rounded-lg p-4 bg-red-50">
                  <h4 className="text-md font-semibold text-red-900 mb-3">
                    Ошибка при работе с 1С
                  </h4>
                  <div className="text-sm text-red-800 whitespace-pre-wrap break-words">
                    {typeof onecInfo.error_from_1c === 'string' 
                      ? onecInfo.error_from_1c 
                      : JSON.stringify(onecInfo.error_from_1c, null, 2)}
                  </div>
                </div>
              )}

              {/* Сообщение, если информации нет */}
              {!onecInfo.was_found && !onecInfo.was_created && !onecInfo.error_from_1c && (
                <div className="text-center py-8 text-gray-500">
                  Информация о работе с 1С недоступна. Возможно, обработка еще не завершена или не выполнялась.
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-12 text-gray-500">
              Информация о работе с 1С недоступна
            </div>
          )}
        </div>
      )}

      {/* Вкладка "Услуги" */}
      {activeTab === 'services' && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-semibold text-gray-900">
              Все услуги по договору
              {allServices && allServices.length > 0 && (
                <span className="ml-2 text-sm font-normal text-gray-500">
                  ({allServices.length} услуг)
                </span>
              )}
            </h3>
            <button
              onClick={handleRefreshServices}
              disabled={loadingServices}
              className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center text-sm"
            >
              {loadingServices ? (
                <>
                  <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Извлечение...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  Обновить
                </>
              )}
            </button>
          </div>

          {loadingServices ? (
            <div className="flex justify-center items-center py-12">
              <LoadingSpinner size="md" />
            </div>
          ) : allServices && allServices.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium text-gray-600 w-12">№</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-600">Наименование</th>
                    <th className="px-4 py-3 text-right font-medium text-gray-600 w-24">Кол-во</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-600 w-24">Ед. изм.</th>
                    <th className="px-4 py-3 text-right font-medium text-gray-600 w-32">Цена за ед.</th>
                    <th className="px-4 py-3 text-right font-medium text-gray-600 w-32">Сумма</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {allServices.map((service, index) => (
                    <tr key={index} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-gray-500">{index + 1}</td>
                      <td className="px-4 py-3 text-gray-900">
                        <div>
                          <div className="font-medium break-words">{service.name}</div>
                          {service.description && (
                            <div className="text-xs text-gray-500 mt-1 break-words">{service.description}</div>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right text-gray-900">
                        {service.quantity != null ? service.quantity : '—'}
                      </td>
                      <td className="px-4 py-3 text-gray-600">
                        {service.unit || '—'}
                      </td>
                      <td className="px-4 py-3 text-right text-gray-900">
                        {service.unit_price != null
                          ? `${parseFloat(service.unit_price).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ₽`
                          : '—'}
                      </td>
                      <td className="px-4 py-3 text-right font-medium text-gray-900">
                        {service.total_price != null
                          ? `${parseFloat(service.total_price).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ₽`
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
                {/* Итого */}
                {allServices.some(s => s.total_price != null) && (
                  <tfoot className="bg-gray-50 border-t-2 border-gray-300">
                    <tr>
                      <td colSpan="5" className="px-4 py-3 text-right font-semibold text-gray-700">
                        Итого:
                      </td>
                      <td className="px-4 py-3 text-right font-bold text-gray-900">
                        {allServices
                          .filter(s => s.total_price != null)
                          .reduce((sum, s) => sum + parseFloat(s.total_price), 0)
                          .toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ₽
                      </td>
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          ) : (
            <div className="text-center py-12">
              <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
              </svg>
              <h3 className="mt-2 text-sm font-medium text-gray-900">Услуги не загружены</h3>
              <p className="mt-1 text-sm text-gray-500">
                Нажмите кнопку "Обновить" для извлечения списка услуг из документа.
              </p>
              <div className="mt-6">
                <button
                  onClick={handleRefreshServices}
                  disabled={loadingServices}
                  className="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-purple-600 hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500 disabled:opacity-50"
                >
                  <svg className="-ml-1 mr-2 h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  Извлечь услуги
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* История обработки */}
      {contractStatus.processing_started_at && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">
            История обработки
          </h3>
          <div className="space-y-2">
            <div>
              <span className="text-sm font-medium text-gray-600">
                Начало обработки:
              </span>
              <span className="ml-2 text-gray-900">
                {new Date(
                  contractStatus.processing_started_at
                ).toLocaleString('ru-RU')}
              </span>
            </div>
            {contractStatus.processing_completed_at && (
              <div>
                <span className="text-sm font-medium text-gray-600">
                  Завершение обработки:
                </span>
                <span className="ml-2 text-gray-900">
                  {new Date(
                    contractStatus.processing_completed_at
                  ).toLocaleString('ru-RU')}
                </span>
              </div>
            )}
            {contractStatus.error_message && (
              <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg">
                <span className="text-sm font-medium text-red-800">
                  Ошибка:
                </span>
                <span className="ml-2 text-red-700">
                  {contractStatus.error_message}
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Модальное окно с информацией о запросах LLM */}
      {showLLMInfo && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full mx-4 max-h-[90vh] overflow-hidden flex flex-col">
            <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
              <h3 className="text-xl font-semibold text-gray-900">
                Информация о запросах LLM
              </h3>
              <button
                onClick={() => setShowLLMInfo(false)}
                className="text-gray-400 hover:text-gray-600 transition-colors"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="px-6 py-4 overflow-y-auto flex-1">
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
            <div className="px-6 py-4 border-t border-gray-200 flex justify-end">
              <button
                onClick={() => setShowLLMInfo(false)}
                className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors"
              >
                Закрыть
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ContractDetails;
