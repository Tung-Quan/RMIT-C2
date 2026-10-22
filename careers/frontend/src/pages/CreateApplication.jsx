import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { createApplication } from "../api/applications";
import { getErrorMessage } from "../api/client";
import { Alert } from "../components/Alert";
import { ApplicationForm } from "../components/ApplicationForm";

export function CreateApplication() {
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(payload) {
    setError("");
    setIsLoading(true);
    try {
      const response = await createApplication(payload);
      navigate(`/applications/${response.data.id}`);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-950">New saved application</h1>
        <p className="mt-1 text-sm text-zinc-500">Save the role details and job description</p>
      </div>
      {error && <Alert>{error}</Alert>}
      <ApplicationForm onSubmit={handleSubmit} isLoading={isLoading} submitLabel="Save application" />
    </div>
  );
}
