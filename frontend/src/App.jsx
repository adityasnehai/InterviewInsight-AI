import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { useAuth } from "./context/AuthContext";
import InterviewDashboard from "./pages/InterviewDashboard";
import AuthPage from "./pages/AuthPage";
import LiveInterview from "./pages/LiveInterview";
import ProductWorkspace from "./pages/ProductWorkspace";
import ProgressDashboard from "./pages/ProgressDashboard";
import ReflectiveLearningPanel from "./pages/ReflectiveLearningPanel";
import styles from "./App.module.css";

function ProtectedLayout() {
  const { authReady, isAuthenticated } = useAuth();
  if (!authReady) {
    return null;
  }
  if (!isAuthenticated) {
    return <Navigate to="/auth" replace />;
  }

  return (
    <div className={styles.appShell}>
      <Outlet />
    </div>
  );
}

function App() {
  const { authReady, isAuthenticated } = useAuth();
  if (!authReady) {
    return null;
  }

  return (
    <Routes>
      <Route path="/auth" element={isAuthenticated ? <Navigate to="/app" replace /> : <AuthPage />} />

      <Route element={<ProtectedLayout />}>
        <Route path="/app" element={<ProductWorkspace />} />
        <Route path="/interview/live" element={<LiveInterview />} />
        <Route path="/dashboard/:sessionId" element={<InterviewDashboard />} />
        <Route path="/progress/:userId" element={<ProgressDashboard />} />
        <Route path="/reflective/:sessionId" element={<ReflectiveLearningPanel />} />
      </Route>

      <Route path="/" element={<Navigate to={isAuthenticated ? "/app" : "/auth"} replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
