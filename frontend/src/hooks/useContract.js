import { useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { getContractStatus, getContractData } from '../services/contractService';
import { updateContract, setCurrentContract } from '../store/slices/contractSlice';

export const useContract = (contractId) => {
  const dispatch = useDispatch();
  const contract = useSelector((state) =>
    state.contracts.contracts.find((c) => c.id === parseInt(contractId))
  );

  const refreshStatus = async () => {
    if (!contractId) return;
    try {
      const status = await getContractStatus(contractId);
      dispatch(updateContract({ id: parseInt(contractId), ...status }));
    } catch (error) {
      console.error('Failed to refresh contract status:', error);
    }
  };

  const loadContractData = async () => {
    if (!contractId) return null;
    try {
      const data = await getContractData(contractId);
      dispatch(setCurrentContract(data));
      return data;
    } catch (error) {
      console.error('Failed to load contract data:', error);
      return null;
    }
  };

  return {
    contract,
    refreshStatus,
    loadContractData,
  };
};
