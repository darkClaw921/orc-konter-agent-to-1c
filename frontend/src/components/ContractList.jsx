import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import { listContracts, getContractStatus, deleteContract, retryContract } from '../services/contractService';
import { setContracts, setFilter, updateContract, removeContract } from '../store/slices/contractSlice';
import { addNotification } from '../store/slices/uiSlice';
import LoadingSpinner from './LoadingSpinner';

const ContractList = () => {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const { contracts, filter } = useSelector((state) => state.contracts);
  const [loading, setLoading] = useState(true);

  const statusLabels = {
    uploaded: 'Загружен',
    processing: 'Обработка',
    document_loaded: 'Документ загружен',
    text_extracted: 'Текст извлечен',
    data_extracted: 'Данные извлечены',
    validation_passed: 'Валидация пройдена',
    validation_failed: 'Валидация не пройдена',
    checking_1c: 'Проверка в 1С',
    creating_in_1c: 'Создание в 1С',
    completed: 'Завершен',
    failed: 'Ошибка',
  };

  const getStatusColor = (status) => {
    const colors = {
      uploaded: 'bg-gray-100 text-gray-800',
      processing: 'bg-blue-100 text-blue-800',
      document_loaded: 'bg-blue-100 text-blue-800',
      text_extracted: 'bg-blue-100 text-blue-800',
      data_extracted: 'bg-blue-100 text-blue-800',
      validation_passed: 'bg-green-100 text-green-800',
      validation_failed: 'bg-red-100 text-red-800',
      checking_1c: 'bg-yellow-100 text-yellow-800',
      creating_in_1c: 'bg-yellow-100 text-yellow-800',
      completed: 'bg-green-100 text-green-800',
      failed: 'bg-red-100 text-red-800',
    };
    return colors[status] || 'bg-gray-100 text-gray-800';
  };

  const loadContracts = async () => {
    try {
      setLoading(true);
      const filters = {};
      if (filter !== 'all') {
        filters.status_filter = filter;
      }
      const response = await listContracts(filters);
      dispatch(setContracts(response.contracts));
    } catch (error) {
      dispatch(
        addNotification({
          type: 'error',
          message: 'Ошибка при загрузке списка контрактов',
        })
      );
    } finally {
      setLoading(false);
    }
  };

  const updateContractStatus = async (contractId) => {
    try {
      const status = await getContractStatus(contractId);
      dispatch(updateContract({ id: contractId, ...status }));
    } catch (error) {
      console.error('Failed to update contract status:', error);
    }
  };

  useEffect(() => {
    loadContracts();
  }, [filter]);

  // Автоматическое обновление статуса каждые 5 секунд
  useEffect(() => {
    const interval = setInterval(() => {
      contracts.forEach((contract) => {
        const processingStates = [
          'uploaded',
          'processing',
          'document_loaded',
          'text_extracted',
          'data_extracted',
          'checking_1c',
          'creating_in_1c',
        ];
        if (processingStates.includes(contract.status)) {
          updateContractStatus(contract.id);
        }
      });
    }, 5000);

    return () => clearInterval(interval);
  }, [contracts]);

  const handleRetry = async (contractId, e) => {
    e.stopPropagation();
    
    try {
      await retryContract(contractId);
      dispatch(
        addNotification({
          type: 'success',
          message: 'Обработка контракта перезапущена',
        })
      );
      // Обновляем статус контракта
      await updateContractStatus(contractId);
      // Перезагружаем список контрактов
      await loadContracts();
    } catch (error) {
      dispatch(
        addNotification({
          type: 'error',
          message: 'Ошибка при повторной обработке контракта',
        })
      );
    }
  };

  const handleDelete = async (contractId, e) => {
    e.stopPropagation();
    if (!window.confirm('Вы уверены, что хотите удалить этот контракт?')) {
      return;
    }

    try {
      await deleteContract(contractId);
      dispatch(removeContract(contractId));
      dispatch(
        addNotification({
          type: 'success',
          message: 'Контракт успешно удален',
        })
      );
    } catch (error) {
      dispatch(
        addNotification({
          type: 'error',
          message: 'Ошибка при удалении контракта',
        })
      );
    }
  };

  const filteredContracts = contracts.filter((contract) => {
    if (filter === 'all') return true;
    if (filter === 'processing') {
      return ['uploaded', 'processing', 'document_loaded', 'text_extracted', 'data_extracted', 'checking_1c', 'creating_in_1c'].includes(contract.status);
    }
    if (filter === 'completed') {
      return contract.status === 'completed';
    }
    if (filter === 'failed') {
      return contract.status === 'failed';
    }
    return true;
  });

  if (loading) {
    return (
      <div className="flex justify-center items-center py-12">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Фильтры */}
      <div className="flex items-center space-x-4">
        <span className="text-sm font-medium text-gray-700">Фильтр:</span>
        {['all', 'processing', 'completed', 'failed'].map((filterOption) => (
          <button
            key={filterOption}
            onClick={() => dispatch(setFilter(filterOption))}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              filter === filterOption
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {filterOption === 'all' && 'Все'}
            {filterOption === 'processing' && 'В обработке'}
            {filterOption === 'completed' && 'Завершены'}
            {filterOption === 'failed' && 'Ошибки'}
          </button>
        ))}
      </div>

      {/* Таблица */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Файл
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                ИНН
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Контрагент
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Статус
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Дата создания
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Действия
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {filteredContracts.length === 0 ? (
              <tr>
                <td colSpan="6" className="px-6 py-8 text-center text-gray-500">
                  Контракты не найдены
                </td>
              </tr>
            ) : (
              filteredContracts.map((contract) => (
                <tr
                  key={contract.id}
                  className="hover:bg-gray-50 cursor-pointer"
                  onClick={() => navigate(`/contracts/${contract.id}`)}
                >
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium text-gray-900">
                      {contract.original_filename}
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm text-gray-900">
                      {contract.inn || '—'}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="text-sm text-gray-900">
                      {contract.full_name || '—'}
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span
                      className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getStatusColor(
                        contract.status
                      )}`}
                    >
                      {statusLabels[contract.status] || contract.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {new Date(contract.created_at).toLocaleString('ru-RU')}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <div className="flex justify-end space-x-2">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/contracts/${contract.id}`);
                        }}
                        className="text-blue-600 hover:text-blue-900"
                      >
                        Подробнее
                      </button>
                      {contract.status === 'failed' && (
                        <button
                          onClick={(e) => handleRetry(contract.id, e)}
                          className="text-green-600 hover:text-green-900"
                          title="Повторить обработку"
                        >
                          Повторить
                        </button>
                      )}
                      <button
                        onClick={(e) => handleDelete(contract.id, e)}
                        className="text-red-600 hover:text-red-900"
                      >
                        Удалить
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default ContractList;
