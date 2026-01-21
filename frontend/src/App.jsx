import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { Provider } from 'react-redux';
import { store } from './store/store';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import DashboardPage from './pages/DashboardPage';
import UploadPage from './pages/UploadPage';
import HistoryPage from './pages/HistoryPage';
import SettingsPage from './pages/SettingsPage';
import TestsPage from './pages/TestsPage';
import ContractDetails from './components/ContractDetails';
import NotificationContainer from './components/NotificationContainer';
import './styles/global.css';

const App = () => {
  return (
    <Provider store={store}>
      <Router
        future={{
          v7_startTransition: true,
          v7_relativeSplatPath: true,
        }}
      >
        <div className="min-h-screen bg-gray-50">
          <Header />
          <div className="flex">
            <Sidebar />
            <main className="flex-1 p-6">
              <Routes>
                <Route path="/" element={<DashboardPage />} />
                <Route path="/upload" element={<UploadPage />} />
                <Route path="/history" element={<HistoryPage />} />
                <Route path="/tests" element={<TestsPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/contracts/:id" element={<ContractDetails />} />
              </Routes>
            </main>
          </div>
          <NotificationContainer />
        </div>
      </Router>
    </Provider>
  );
};

export default App;
