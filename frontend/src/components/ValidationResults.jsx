import React from 'react';

const ValidationResults = ({ results }) => {
  if (!results || (!results.errors?.length && !results.warnings?.length)) {
    return (
      <div className="bg-green-50 border border-green-200 rounded-lg p-4">
        <div className="flex items-center space-x-2">
          <svg
            className="w-5 h-5 text-green-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M5 13l4 4L19 7"
            />
          </svg>
          <span className="text-green-800 font-medium">
            Валидация пройдена успешно
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {results.errors && results.errors.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <h4 className="text-red-800 font-semibold mb-2 flex items-center space-x-2">
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <span>Ошибки валидации ({results.errors.length})</span>
          </h4>
          <ul className="list-disc list-inside space-y-1">
            {results.errors.map((error, index) => (
              <li key={index} className="text-red-700 text-sm">
                {typeof error === 'string' ? error : JSON.stringify(error)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {results.warnings && results.warnings.length > 0 && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <h4 className="text-yellow-800 font-semibold mb-2 flex items-center space-x-2">
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
            <span>Предупреждения ({results.warnings.length})</span>
          </h4>
          <ul className="list-disc list-inside space-y-1">
            {results.warnings.map((warning, index) => (
              <li key={index} className="text-yellow-700 text-sm">
                {typeof warning === 'string' ? warning : JSON.stringify(warning)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default ValidationResults;
