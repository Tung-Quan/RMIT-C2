import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { RoleHomeRedirect } from "./routes/RoleHomeRedirect";
import { ProtectedRoute } from "./routes/ProtectedRoute";

function lazyPage(loader, exportName) {
  return lazy(() => loader().then((module) => ({ default: module[exportName] })));
}

const CandidateApply = lazyPage(() => import("./pages/CandidateApply"), "CandidateApply");
const Layout = lazyPage(() => import("./components/Layout"), "Layout");
const CandidateDashboard = lazyPage(() => import("./pages/CandidateDashboard"), "CandidateDashboard");
const CandidateJobApplicationDetail = lazyPage(
  () => import("./pages/CandidateJobApplicationDetail"),
  "CandidateJobApplicationDetail"
);
const CandidateJobApplications = lazyPage(() => import("./pages/CandidateJobApplications"), "CandidateJobApplications");
const CandidateJobDetail = lazyPage(() => import("./pages/CandidateJobDetail"), "CandidateJobDetail");
const CandidateJobs = lazyPage(() => import("./pages/CandidateJobs"), "CandidateJobs");
const CandidateProfile = lazyPage(() => import("./pages/CandidateProfile"), "CandidateProfile");
const Chat = lazyPage(() => import("./pages/Chat"), "Chat");
const HrApplicationDetail = lazyPage(() => import("./pages/HrApplicationDetail"), "HrApplicationDetail");
const HrCompany = lazyPage(() => import("./pages/HrCompany"), "HrCompany");
const HrDashboard = lazyPage(() => import("./pages/HrDashboard"), "HrDashboard");
const HrJobApplicants = lazyPage(() => import("./pages/HrJobApplicants"), "HrJobApplicants");
const HrJobDetail = lazyPage(() => import("./pages/HrJobDetail"), "HrJobDetail");
const HrJobEditor = lazyPage(() => import("./pages/HrJobEditor"), "HrJobEditor");
const HrJobs = lazyPage(() => import("./pages/HrJobs"), "HrJobs");
const AICVMatching = lazyPage(() => import("./pages/AICVMatching"), "AICVMatching");
const ApplicationDetail = lazyPage(() => import("./pages/ApplicationDetail"), "ApplicationDetail");
const ApplicationsList = lazyPage(() => import("./pages/ApplicationsList"), "ApplicationsList");
const CreateApplication = lazyPage(() => import("./pages/CreateApplication"), "CreateApplication");
const EditApplication = lazyPage(() => import("./pages/EditApplication"), "EditApplication");
const Login = lazyPage(() => import("./pages/Login"), "Login");
const Register = lazyPage(() => import("./pages/Register"), "Register");
const SearchResults = lazyPage(() => import("./pages/SearchResults"), "SearchResults");
const Settings = lazyPage(() => import("./pages/Settings"), "Settings");
const Unauthorized = lazyPage(() => import("./pages/Unauthorized"), "Unauthorized");

function RouteFallback() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50 text-sm font-medium text-zinc-600">
      Loading
    </div>
  );
}

export default function App() {
  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>
        <Route path="/" element={<ProtectedRoute><RoleHomeRedirect /></ProtectedRoute>} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/unauthorized" element={<Unauthorized />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route
            path="candidate/dashboard"
            element={
              <ProtectedRoute allowedRoles={["candidate", "admin"]}>
                <CandidateDashboard />
              </ProtectedRoute>
            }
          />
        <Route
          path="candidate/profile"
          element={
            <ProtectedRoute allowedRoles={["candidate", "admin"]}>
              <CandidateProfile />
            </ProtectedRoute>
          }
        />
        <Route
          path="candidate/jobs"
          element={
            <ProtectedRoute allowedRoles={["candidate", "admin"]}>
              <CandidateJobs />
            </ProtectedRoute>
          }
        />
        <Route
          path="candidate/jobs/:jobId"
          element={
            <ProtectedRoute allowedRoles={["candidate", "admin"]}>
              <CandidateJobDetail />
            </ProtectedRoute>
          }
        />
        <Route
          path="candidate/jobs/:jobId/apply"
          element={
            <ProtectedRoute allowedRoles={["candidate", "admin"]}>
              <CandidateApply />
            </ProtectedRoute>
          }
        />
        <Route
          path="candidate/job-applications"
          element={
            <ProtectedRoute allowedRoles={["candidate", "admin"]}>
              <CandidateJobApplications />
            </ProtectedRoute>
          }
        />
        <Route
          path="candidate/job-applications/:applicationId"
          element={
            <ProtectedRoute allowedRoles={["candidate", "admin"]}>
              <CandidateJobApplicationDetail />
            </ProtectedRoute>
          }
        />

        <Route
          path="search"
          element={
            <ProtectedRoute allowedRoles={["candidate", "hr", "admin"]}>
              <SearchResults />
            </ProtectedRoute>
          }
        />

        <Route
          path="settings"
          element={
            <ProtectedRoute allowedRoles={["candidate", "hr", "admin"]}>
              <Settings />
            </ProtectedRoute>
          }
        />

        <Route
          path="chat"
          element={
            <ProtectedRoute allowedRoles={["candidate", "hr", "admin"]}>
              <Chat />
            </ProtectedRoute>
          }
        />

        <Route
          path="applications"
          element={
            <ProtectedRoute allowedRoles={["candidate", "admin"]}>
              <ApplicationsList />
            </ProtectedRoute>
          }
        />
        <Route
          path="applications/new"
          element={
            <ProtectedRoute allowedRoles={["candidate", "admin"]}>
              <CreateApplication />
            </ProtectedRoute>
          }
        />
        <Route
          path="applications/ai-cv-matching"
          element={
            <ProtectedRoute allowedRoles={["candidate", "admin"]}>
              <AICVMatching />
            </ProtectedRoute>
          }
        />
        <Route
          path="applications/:id"
          element={
            <ProtectedRoute allowedRoles={["candidate", "admin"]}>
              <ApplicationDetail />
            </ProtectedRoute>
          }
        />
        <Route
          path="applications/:id/edit"
          element={
            <ProtectedRoute allowedRoles={["candidate", "admin"]}>
              <EditApplication />
            </ProtectedRoute>
          }
        />

        <Route
          path="hr/dashboard"
          element={
            <ProtectedRoute allowedRoles={["hr", "admin"]}>
              <HrDashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="hr/company"
          element={
            <ProtectedRoute allowedRoles={["hr", "admin"]}>
              <HrCompany />
            </ProtectedRoute>
          }
        />
        <Route
          path="hr/jobs"
          element={
            <ProtectedRoute allowedRoles={["hr", "admin"]}>
              <HrJobs />
            </ProtectedRoute>
          }
        />
        <Route
          path="hr/jobs/new"
          element={
            <ProtectedRoute allowedRoles={["hr", "admin"]}>
              <HrJobEditor mode="create" />
            </ProtectedRoute>
          }
        />
        <Route
          path="hr/jobs/:jobId"
          element={
            <ProtectedRoute allowedRoles={["hr", "admin"]}>
              <HrJobDetail />
            </ProtectedRoute>
          }
        />
        <Route
          path="hr/jobs/:jobId/edit"
          element={
            <ProtectedRoute allowedRoles={["hr", "admin"]}>
              <HrJobEditor mode="edit" />
            </ProtectedRoute>
          }
        />
        <Route
          path="hr/jobs/:jobId/applicants"
          element={
            <ProtectedRoute allowedRoles={["hr", "admin"]}>
              <HrJobApplicants />
            </ProtectedRoute>
          }
        />
        <Route
          path="hr/applications/:applicationId"
          element={
            <ProtectedRoute allowedRoles={["hr", "admin"]}>
              <HrApplicationDetail />
            </ProtectedRoute>
          }
        />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
