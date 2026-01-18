import React, { useEffect } from 'react';
import { BrowserRouter as Router, Route, Switch } from 'react-router-dom';
import { initializeAuth } from './auth';
import ProtectedRoute from './ProtectedRoute';
import Home from './Home';
import Login from './Login';
import Dashboard from './Dashboard';

function App() {
  useEffect(() => {
    // Check for authentication token in URL
    initializeAuth();
  }, []);
  
  return (
    <Router>
      <Switch>
        <Route exact path="/" component={Home} />
        <Route path="/login" component={Login} />
        <ProtectedRoute path="/dashboard" component={Dashboard} />
        {/* Add more protected routes as needed */}
      </Switch>
    </Router>
  );
}

export default App; 