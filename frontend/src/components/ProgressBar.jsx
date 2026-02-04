import React, { useEffect, useState, useRef } from 'react';
import { getContractProgress } from '../services/contractService';

const ProgressBar = ({ contractId, initialStatus }) => {
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);

  // Статусы, при которых нужно отслеживать прогресс
  const processingStates = [
    'uploaded',
    'processing',
    'document_loaded',
    'text_extracted',
    'data_extracted',
    'services_extracted',
    'checking_1c',
    'creating_in_1c',
  ];

  const isProcessing = processingStates.includes(initialStatus);

  useEffect(() => {
    if (!isProcessing) {
      return;
    }

    const fetchProgress = async () => {
      try {
        const data = await getContractProgress(contractId);
        setProgress(data);
        setError(null);

        // Если обработка завершена, останавливаем polling
        if (data.stage === 'completed' || data.stage === 'failed') {
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
        }
      } catch (err) {
        console.error('Failed to fetch progress:', err);
        setError('Ошибка загрузки прогресса');
      }
    };

    // Первый запрос сразу
    fetchProgress();

    // Polling каждые 1.5 секунды
    intervalRef.current = setInterval(fetchProgress, 1500);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [contractId, isProcessing]);

  if (!isProcessing) {
    return null;
  }

  if (error) {
    return (
      <div className="text-xs text-red-500">
        {error}
      </div>
    );
  }

  if (!progress) {
    return (
      <div className="flex items-center space-x-2">
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div className="bg-blue-400 h-2 rounded-full animate-pulse" style={{ width: '30%' }} />
        </div>
        <span className="text-xs text-gray-500 whitespace-nowrap">Загрузка...</span>
      </div>
    );
  }

  const { overall_progress, stage_name, stage_message, chunks_processed, chunks_total } = progress;

  // Определяем цвет прогресс-бара в зависимости от стадии
  const getProgressColor = () => {
    if (progress.stage === 'failed') return 'bg-red-500';
    if (progress.stage === 'completed') return 'bg-green-500';
    if (overall_progress < 30) return 'bg-blue-400';
    if (overall_progress < 70) return 'bg-blue-500';
    return 'bg-blue-600';
  };

  // Формируем текст для отображения
  const getDisplayText = () => {
    if (chunks_total && chunks_processed !== null && chunks_processed !== undefined) {
      return `${stage_name}: ${chunks_processed}/${chunks_total}`;
    }
    return stage_message || stage_name;
  };

  return (
    <div className="w-full">
      <div className="flex items-center space-x-2">
        <div className="flex-1 bg-gray-200 rounded-full h-2 overflow-hidden">
          <div
            className={`h-2 rounded-full transition-all duration-300 ease-out ${getProgressColor()}`}
            style={{ width: `${Math.max(overall_progress, 2)}%` }}
          />
        </div>
        <span className="text-xs text-gray-600 font-medium whitespace-nowrap min-w-[3rem] text-right">
          {overall_progress}%
        </span>
      </div>
      <div className="mt-1 text-xs text-gray-500 truncate" title={getDisplayText()}>
        {getDisplayText()}
      </div>
    </div>
  );
};

export default ProgressBar;
