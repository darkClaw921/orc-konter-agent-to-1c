import { configureStore } from '@reduxjs/toolkit';
import contractReducer from './slices/contractSlice';
import userReducer from './slices/userSlice';
import uiReducer from './slices/uiSlice';

export const store = configureStore({
  reducer: {
    contracts: contractReducer,
    user: userReducer,
    ui: uiReducer,
  },
});

// TypeScript type exports (for TypeScript files that import this)
// In JavaScript, use JSDoc comments instead:
// @typedef {ReturnType<typeof store.getState>} RootState
// @typedef {typeof store.dispatch} AppDispatch
