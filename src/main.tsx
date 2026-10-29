import React from 'react';
import {createRoot} from 'react-dom/client';
import App from './App';
import './styles.css';
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);

if ('serviceWorker' in navigator && !['5173', '5174'].includes(location.port)) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => { /* Installation can be retried on the next launch. */ });
  });
}
