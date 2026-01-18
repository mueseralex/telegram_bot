// auth.js - React authentication utilities

import axios from 'axios';

const AUTH_SERVER_URL = process.env.REACT_APP_AUTH_SERVER_URL || 'http://localhost:5002';

// Initialize auth from URL if present
export const initializeAuth = () => {
  const urlParams = new URLSearchParams(window.location.search);
  const token = urlParams.get('token');
  
  if (token) {
    // Store the token
    localStorage.setItem('auth_token', token);
    
    // Clean up URL
    window.history.replaceState({}, document.title, window.location.pathname);
    
    return true;
  }
  
  return false;
};

// Check if user is authenticated
export const isAuthenticated = async () => {
  const token = localStorage.getItem('auth_token');
  
  if (!token) {
    return false;
  }
  
  try {
    const response = await axios.post(`${AUTH_SERVER_URL}/verify_jwt`, {}, {
      headers: {
        Authorization: `Bearer ${token}`
      }
    });
    
    return response.data.success;
  } catch (error) {
    console.error('Authentication error:', error);
    
    // Clear token if it's invalid
    if (error.response && (error.response.status === 401 || error.response.status === 403)) {
      localStorage.removeItem('auth_token');
    }
    
    return false;
  }
};

// Get current user data
export const getCurrentUser = async () => {
  const token = localStorage.getItem('auth_token');
  
  if (!token) {
    return null;
  }
  
  try {
    const response = await axios.post(`${AUTH_SERVER_URL}/verify_jwt`, {}, {
      headers: {
        Authorization: `Bearer ${token}`
      }
    });
    
    return response.data.user;
  } catch (error) {
    console.error('Error getting user data:', error);
    return null;
  }
};

// Logout function
export const logout = () => {
  localStorage.removeItem('auth_token');
  window.location.href = '/';
}; 