import { createSlice } from '@reduxjs/toolkit';

const initialState = {
  contracts: [],
  currentContract: null,
  filter: 'all', // all, processing, completed, failed
  loading: false,
  error: null,
};

const contractSlice = createSlice({
  name: 'contracts',
  initialState,
  reducers: {
    setContracts: (state, action) => {
      state.contracts = action.payload;
    },
    addContract: (state, action) => {
      state.contracts.unshift(action.payload);
    },
    updateContract: (state, action) => {
      const index = state.contracts.findIndex(
        (c) => c.id === action.payload.id
      );
      if (index !== -1) {
        state.contracts[index] = { ...state.contracts[index], ...action.payload };
      }
    },
    setCurrentContract: (state, action) => {
      state.currentContract = action.payload;
    },
    setFilter: (state, action) => {
      state.filter = action.payload;
    },
    setLoading: (state, action) => {
      state.loading = action.payload;
    },
    setError: (state, action) => {
      state.error = action.payload;
    },
    removeContract: (state, action) => {
      state.contracts = state.contracts.filter(
        (c) => c.id !== action.payload
      );
    },
  },
});

export const {
  setContracts,
  addContract,
  updateContract,
  setCurrentContract,
  setFilter,
  setLoading,
  setError,
  removeContract,
} = contractSlice.actions;

export default contractSlice.reducer;
