import React from 'react';
import ContractUploader from '../components/ContractUploader';

const UploadPage = () => {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          Загрузка контрактов
        </h1>
        <p className="text-gray-600 mt-2">
          Загрузите DOCX файл контракта для автоматической обработки
        </p>
      </div>
      <ContractUploader />
    </div>
  );
};

export default UploadPage;
