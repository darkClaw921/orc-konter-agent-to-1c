import React from 'react';
import ContractList from '../components/ContractList';

const DashboardPage = () => {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Главная</h1>
        <p className="text-gray-600 mt-2">
          Управление контрактами и контрагентами
        </p>
      </div>
      <ContractList />
    </div>
  );
};

export default DashboardPage;
