import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { getApplication, updateApplication } from "../api/applications";
import { getErrorMessage } from "../api/client";
import { Alert } from "../components/Alert";
import { ApplicationForm } from "../components/ApplicationForm";

export function EditApplication() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [application, setApplication] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    async function loadApplication() {
      setError("");
      try {
        const response = await getApplication(id);
        setApplication(response.data);
      } catch (err) {
        setError(getErrorMessage(err));
      }
    }
    loadApplication();
  }, [id]);

  async function handleSubmit(payload) {
    setError("");
    setIsLoading(true);
    try {
      await updateApplication(id, payload);
      navigate(`/applications/${id}`);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-950">Edit application</h1>
        <p className="mt-1 text-sm text-zinc-500">Update role details, status, and notes</p>
      </div>
      {error && <Alert>{error}</Alert>}
      {!application ? (
        <p className="text-sm text-zinc-500">Loading application</p>
      ) : (
        <ApplicationForm
          initialValues={application}
          onSubmit={handleSubmit}
          isLoading={isLoading}
          submitLabel="Save changes"
        />
      )}
    </div>
  );
}
