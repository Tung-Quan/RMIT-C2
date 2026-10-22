import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { getErrorMessage, normalizeMutationError } from "../api/client";
import { createHrJob, getHrJob, updateHrJob } from "../api/hr";
import { Alert } from "../components/Alert";
import { JobPostingForm } from "../components/JobPostingForm";

export function HrJobEditor({ mode = "create" }) {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState(null);
  const [latestServerJob, setLatestServerJob] = useState(null);
  const [retryVersion, setRetryVersion] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(mode === "edit");
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (mode !== "edit") return;

    async function loadJob() {
      setError("");
      try {
        const response = await getHrJob(jobId);
        setJob(response.data);
      } catch (err) {
        setError(getErrorMessage(err));
      } finally {
        setIsLoading(false);
      }
    }

    loadJob();
  }, [jobId, mode]);

  async function handleSubmit(payload) {
    setError("");
    setIsSaving(true);
    try {
      const response = mode === "edit"
        ? await updateHrJob(jobId, {
            ...payload,
            expectedVersion: retryVersion || job.version
          })
        : await createHrJob(payload);
      navigate(`/hr/jobs/${response.data.id}`);
    } catch (err) {
      const mutationError = normalizeMutationError(err);
      if (mode === "edit" && ["stale", "invalid-transition"].includes(mutationError.type)) {
        try {
          const latestResponse = await getHrJob(jobId);
          setLatestServerJob(latestResponse.data);
          setRetryVersion(latestResponse.data.version);
        } catch {
          // Keep the original mutation error visible if the refresh also fails.
        }
      }
      setError(mutationError.message || getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) return <p className="text-sm text-zinc-500">Loading job editor</p>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-950">
          {mode === "edit" ? "Edit job posting" : "New job posting"}
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          Define the job details candidates will review before applying.
        </p>
      </div>

      {error && <Alert>{error}</Alert>}
      {latestServerJob && (
        <Alert type="success">
          Latest server state: {latestServerJob.status}, version {latestServerJob.version}. Your
          unsaved form values are still here; review them before saving again.
        </Alert>
      )}

      <JobPostingForm
        initialValues={job}
        onSubmit={handleSubmit}
        isLoading={isSaving}
        showStatus={mode !== "edit"}
        submitLabel={mode === "edit" ? "Save job" : "Create job"}
      />
    </div>
  );
}
