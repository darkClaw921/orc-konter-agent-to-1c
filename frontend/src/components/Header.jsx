import React from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { toggleSidebar } from '../store/slices/uiSlice';

const Header = () => {
  const dispatch = useDispatch();
  const { user } = useSelector((state) => state.user);

  return (
    <header className="bg-white shadow-sm border-b border-gray-200">
      <div className="flex items-center justify-between px-6 py-4">
        <div className="flex items-center space-x-4">
          <button
            onClick={() => dispatch(toggleSidebar())}
            className="p-2 rounded-md hover:bg-gray-100 transition-colors"
            aria-label="Toggle sidebar"
          >
            <svg
              className="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 6h16M4 12h16M4 18h16"
              />
            </svg>
          </button>
          <h1 className="text-xl font-semibold text-gray-900">
            SGR Agent - Контрагенты в 1С
          </h1>
        </div>
        <div className="flex items-center space-x-4">
          {user && (
            <span className="text-sm text-gray-600">
              {user.username || 'Пользователь'}
            </span>
          )}
        </div>
      </div>
    </header>
  );
};

export default Header;
