import { BrowserRouter, Routes, Route } from 'react-router-dom'

import Dashboard from './pages/Dashboard'
import DetailBPR from './pages/DetailBPR'
import InputData from './pages/InputData'
import Perbandingan from './pages/Perbandingan'
import Laporan from './pages/Laporan'
import Dokumen from './pages/Dokumen'
import UploadData from './pages/UploadData'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/detail-bpr" element={<DetailBPR />} />
        <Route path="/input-data" element={<InputData />} />
        <Route path="/perbandingan" element={<Perbandingan />} />
        <Route path="/laporan" element={<Laporan />} />
        <Route path="/dokumen" element={<Dokumen />} />
        <Route path="/upload-data" element={<UploadData />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App