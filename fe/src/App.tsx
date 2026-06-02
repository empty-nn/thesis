import './App.css'
import { Route, Routes } from 'react-router'
import ChatPage from './pages/ChatPage'
import DataBuilding from './pages/DataBuilding';

function App() {
  return (
    <div>
      <Routes>
        <Route path="/" element={<ChatPage />} />
        <Route path="/data-building" element={<DataBuilding />} />
      </Routes>
    </div>
  );
}

export default App