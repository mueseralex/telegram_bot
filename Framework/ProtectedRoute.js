// ProtectedRoute.js - React component for protected routes

import React, { useState, useEffect } from 'react';
import { Route, Redirect } from 'react-router-dom';
import { isAuthenticated } from './auth';

const ProtectedRoute = ({ component: Component, ...rest }) => {
  const [loading, setLoading] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  
  useEffect(() => {
    const checkAuth = async () => {
      const auth = await isAuthenticated();
      setAuthenticated(auth);
      setLoading(false);
    };
    
    checkAuth();
  }, []);
  
  if (loading) {
    return <div>Loading...</div>;
  }
  
  return (
    <Route
      {...rest}
      render={(props) =>
        authenticated ? (
          <Component {...props} />
        ) : (
          <Redirect to={{ pathname: '/login', state: { from: props.location } }} />
        )
      }
    />
  );
};

export default ProtectedRoute; 