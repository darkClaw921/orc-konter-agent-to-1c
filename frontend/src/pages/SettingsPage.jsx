import React from 'react';

const SettingsPage = () => {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Настройки</h1>
        <p className="text-gray-600 mt-2">
          Настройки приложения будут доступны в будущих версиях
        </p>
      </div>
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <p className="text-gray-500">Раздел в разработке</p>
      </div>
    </div>
  );
};

export default SettingsPage;
