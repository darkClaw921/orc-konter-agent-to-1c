import React, { useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { removeNotification } from '../store/slices/uiSlice';

const NotificationContainer = () => {
  const dispatch = useDispatch();
  const notifications = useSelector((state) => state.ui.notifications);

  useEffect(() => {
    notifications.forEach((notification) => {
      if (notification.autoClose !== false) {
        const timer = setTimeout(() => {
          dispatch(removeNotification(notification.id));
        }, notification.duration || 5000);

        return () => clearTimeout(timer);
      }
    });
  }, [notifications, dispatch]);

  const getNotificationStyles = (type) => {
    const styles = {
      success: 'bg-green-50 border-green-200 text-green-800',
      error: 'bg-red-50 border-red-200 text-red-800',
      warning: 'bg-yellow-50 border-yellow-200 text-yellow-800',
      info: 'bg-blue-50 border-blue-200 text-blue-800',
    };
    return styles[type] || styles.info;
  };

  if (notifications.length === 0) {
    return null;
  }

  return (
    <div className="fixed top-4 right-4 z-50 space-y-2">
      {notifications.map((notification) => (
        <div
          key={notification.id}
          className={`min-w-[300px] max-w-md p-4 rounded-lg shadow-lg border ${getNotificationStyles(
            notification.type
          )}`}
        >
          <div className="flex justify-between items-start">
            <div className="flex-1">
              <p className="font-medium">{notification.message}</p>
            </div>
            <button
              onClick={() => dispatch(removeNotification(notification.id))}
              className="ml-4 text-gray-400 hover:text-gray-600"
            >
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
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>
        </div>
      ))}
    </div>
  );
};

export default NotificationContainer;
