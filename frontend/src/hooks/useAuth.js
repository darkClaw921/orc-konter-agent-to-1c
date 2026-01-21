import { useSelector, useDispatch } from 'react-redux';
import { setUser, setToken, logout } from '../store/slices/userSlice';

export const useAuth = () => {
  const dispatch = useDispatch();
  const { user, isAuthenticated, token } = useSelector((state) => state.user);

  const login = (userData, authToken) => {
    dispatch(setUser(userData));
    dispatch(setToken(authToken));
  };

  const logoutUser = () => {
    dispatch(logout());
  };

  return {
    user,
    isAuthenticated,
    token,
    login,
    logout: logoutUser,
  };
};
