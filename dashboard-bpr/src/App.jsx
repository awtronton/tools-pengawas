import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
} from 'react-router-dom'

import Dashboard from './pages/Dashboard'
import DetailBPR from './pages/DetailBPR'
import InputData from './pages/InputData'
import Perbandingan from './pages/Perbandingan'
import Laporan from './pages/Laporan'
import Dokumen from './pages/Dokumen'
import UploadData from './pages/UploadData'
import DataTables from './pages/DataTables'
import TableExplorer from './pages/TableExplorer'
import SchemaManager from './pages/SchemaManager'
import PlaceholderPage from './components/ui/PlaceholderPage'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Canonical routes */}
        <Route
          path="/"
          element={<Navigate to="/dashboard" replace />}
        />

        <Route
          path="/dashboard"
          element={<Dashboard />}
        />

        <Route
          path="/upload"
          element={<UploadData />}
        />

        <Route
          path="/tables"
          element={<DataTables />}
        />

        <Route
          path="/explorer"
          element={<TableExplorer />}
        />

        <Route
          path="/schema"
          element={<SchemaManager />}
        />

        <Route
          path="/visualization"
          element={
            <PlaceholderPage
              title="Visualisasi"
              description="Workspace visualisasi data pengawasan akan dibangun pada tahap berikutnya."
              module="Analysis"
            />
          }
        />

        <Route
          path="/comparison"
          element={<Perbandingan />}
        />

        <Route
          path="/bank"
          element={<DetailBPR />}
        />

        <Route
          path="/reports"
          element={<Laporan />}
        />

        <Route
          path="/documents"
          element={<Dokumen />}
        />

        {/* Existing/legacy routes kept for compatibility */}
        <Route
          path="/detail-bpr"
          element={<Navigate to="/bank" replace />}
        />

        <Route
          path="/perbandingan"
          element={<Navigate to="/comparison" replace />}
        />

        <Route
          path="/laporan"
          element={<Navigate to="/reports" replace />}
        />

        <Route
          path="/dokumen"
          element={<Navigate to="/documents" replace />}
        />

        <Route
          path="/upload-data"
          element={<Navigate to="/upload" replace />}
        />

        <Route
          path="/input-data"
          element={<InputData />}
        />

        <Route
          path="*"
          element={<Navigate to="/dashboard" replace />}
        />
      </Routes>
    </BrowserRouter>
  )
}

export default App
