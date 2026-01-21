import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useSelector } from 'react-redux';

const Sidebar = () => {
  const location = useLocation();
  const { sidebarOpen } = useSelector((state) => state.ui);

  const menuItems = [
    { path: '/', label: 'Главная', icon: '📊' },
    { path: '/upload', label: 'Загрузка контрактов', icon: '📤' },
    { path: '/history', label: 'История', icon: '📋' },
    { path: '/tests', label: 'Тесты', icon: '🧪' },
    { path: '/settings', label: 'Настройки', icon: '⚙️' },
  ];

  const isActive = (path) => {
    return location.pathname === path;
  };

  if (!sidebarOpen) {
    return null;
  }

  return (
    <aside className="w-64 bg-white shadow-sm border-r border-gray-200 h-full">
      <nav className="p-4">
        <ul className="space-y-2">
          {menuItems.map((item) => (
            <li key={item.path}>
              <Link
                to={item.path}
                className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors ${
                  isActive(item.path)
                    ? 'bg-blue-50 text-blue-700 font-medium'
                    : 'text-gray-700 hover:bg-gray-50'
                }`}
              >
                <span className="text-xl">{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  );
};

export default Sidebar;
