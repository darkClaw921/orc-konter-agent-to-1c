import api from './api';

/**
 * Загрузить контракт
 * @param {File} file - Файл контракта
 * @param {Function} onUploadProgress - Callback для отслеживания прогресса загрузки
 * @returns {Promise} Ответ с данными загруженного контракта
 */
export const uploadContract = async (file, onUploadProgress) => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await api.post('/contracts/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    onUploadProgress: (progressEvent) => {
      if (onUploadProgress && progressEvent.total) {
        const percentCompleted = Math.round(
          (progressEvent.loaded * 100) / progressEvent.total
        );
        onUploadProgress(percentCompleted);
      }
    },
  });

  return response.data;
};

/**
 * Получить статус контракта
 * @param {number} contractId - ID контракта
 * @returns {Promise} Статус контракта
 */
export const getContractStatus = async (contractId) => {
  const response = await api.get(`/contracts/${contractId}/status`);
  return response.data;
};

/**
 * Получить данные контракта
 * @param {number} contractId - ID контракта
 * @returns {Promise} Данные контракта
 */
export const getContractData = async (contractId) => {
  const response = await api.get(`/contracts/${contractId}/data`);
  return response.data;
};

/**
 * Получить список контрактов
 * @param {Object} filters - Фильтры (skip, limit, status_filter)
 * @returns {Promise} Список контрактов
 */
export const listContracts = async (filters = {}) => {
  const params = {
    skip: filters.skip || 0,
    limit: filters.limit || 100,
  };

  if (filters.status_filter) {
    params.status_filter = filters.status_filter;
  }

  const response = await api.get('/contracts/', { params });
  return response.data;
};

/**
 * Повторить обработку контракта
 * @param {number} contractId - ID контракта
 * @returns {Promise} Ответ с данными контракта и task_id
 */
export const retryContract = async (contractId) => {
  const response = await api.post(`/contracts/${contractId}/retry`);
  return response.data;
};

/**
 * Удалить контракт
 * @param {number} contractId - ID контракта
 * @returns {Promise}
 */
export const deleteContract = async (contractId) => {
  await api.delete(`/contracts/${contractId}`);
};

/**
 * Получить информацию о запросах LLM для контракта
 * @param {number} contractId - ID контракта
 * @returns {Promise} Информация о запросах LLM
 */
export const getLLMInfo = async (contractId) => {
  const response = await api.get(`/contracts/${contractId}/llm-info`);
  return response.data;
};

/**
 * Получить полный распознанный текст документа
 * @param {number} contractId - ID контракта
 * @returns {Promise} Полный текст документа
 */
export const getContractRawText = async (contractId) => {
  const response = await api.get(`/contracts/${contractId}/raw-text`);
  return response.data;
};

/**
 * Обработать уже загруженный контракт (для тестов)
 * @param {number} contractId - ID контракта
 * @returns {Promise} Ответ с данными обработки
 */
export const processContractForTests = async (contractId) => {
  const response = await api.post('/testing/process-contract', {
    contract_id: contractId,
  });
  return response.data;
};

/**
 * Проверить работу MCP 1С - получить одного контрагента из 1С
 * @returns {Promise} Ответ с данными контрагента или ошибкой
 */
export const testMCP1C = async () => {
  const response = await api.get('/testing/test-mcp-1c');
  return response.data;
};
