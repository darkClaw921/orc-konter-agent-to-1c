import React from 'react';
import ContractList from '../components/ContractList';

const HistoryPage = () => {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">История обработки</h1>
        <p className="text-gray-600 mt-2">
          Просмотр истории обработки всех контрактов
        </p>
      </div>
      <ContractList />
    </div>
  );
};

export default HistoryPage;
