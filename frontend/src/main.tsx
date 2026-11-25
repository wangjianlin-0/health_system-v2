import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
const savedFontScale = Number(localStorage.getItem('ecg_font_scale') || 100);
if (savedFontScale >= 85 && savedFontScale <= 130) document.documentElement.style.setProperty('--font-scale', String(savedFontScale / 100));
import './index.css';
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><BrowserRouter><App /></BrowserRouter></React.StrictMode>);
