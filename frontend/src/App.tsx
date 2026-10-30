import { Routes, Route } from 'react-router-dom';
import { DashboardLayout } from './components/DashboardLayout';
import { Overview } from './pages/Overview';
import { Signals } from './pages/Signals';
import { Analysis } from './pages/Analysis';
import { BacktestLab } from './pages/BacktestLab';
import { DataHealth } from './pages/DataHealth';
import { PaperTrading } from './pages/PaperTrading';

function App() {
  return (
    <Routes>
      <Route element={<DashboardLayout />}>
        <Route path="/" element={<Overview />} />
        <Route path="/signals" element={<Signals />} />
        <Route path="/analysis" element={<Analysis />} />
        <Route path="/backtest" element={<BacktestLab />} />
        <Route path="/health" element={<DataHealth />} />
        <Route path="/trading" element={<PaperTrading />} />
        <Route path="*" element={<Overview />} />
      </Route>
    </Routes>
  );
}

export default App;