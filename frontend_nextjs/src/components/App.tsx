"use client";

import React, { useState } from 'react';
import Sidebar from './Sidebar';
import Header from './Header';
import Home from '../pages/Home';
import Study from '../pages/Study';
import Speaking from '../pages/Speaking';
import Writing from '../pages/Writing';
import Exam from '../pages/Exam';

export default function App() {
  const [currentPage, setCurrentPage] = useState('study');

  const renderPage = () => {
    switch(currentPage) {
      case 'home': return <Home />;
      case 'study': return <Study />;
      case 'speaking': return <Speaking />;
      case 'writing': return <Writing />;
      case 'exam': return <Exam />;
      default: return <Study />;
    }
  };

  return (
    <div className="flex h-screen w-full bg-content-bg overflow-hidden font-lexend text-primary">
      <Sidebar currentPage={currentPage} onNavigate={setCurrentPage} />
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        <Header />
        
        {/* Main Content Area */}
        {renderPage()}
      </div>
    </div>
  );
}
