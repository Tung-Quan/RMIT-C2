import { useCallback, useEffect, useRef, useState } from "react";

import { getProcessingJob, isProcessingJobTerminal } from "../api/processingJobs";

const DEFAULT_INTERVAL_MS = 1500;
const DEFAULT_MAX_POLLS = 40;

export function useProcessingJobStatus(
  jobId,
  {
    enabled = true,
    initialJob = null,
    intervalMs = DEFAULT_INTERVAL_MS,
    maxPolls = DEFAULT_MAX_POLLS,
    onTerminal
  } = {}
) {
  const [job, setJob] = useState(initialJob);
  const [error, setError] = useState(null);
  const [isPolling, setIsPolling] = useState(Boolean(enabled && jobId));
  const timerRef = useRef(null);
  const inFlightRef = useRef(false);
  const pollCountRef = useRef(0);
  const stoppedRef = useRef(false);

  const stop = useCallback(() => {
    stoppedRef.current = true;
    setIsPolling(false);
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const poll = useCallback(async () => {
    if (!enabled || !jobId || stoppedRef.current || inFlightRef.current) return;
    if (pollCountRef.current >= maxPolls) {
      stop();
      return;
    }

    inFlightRef.current = true;
    setIsPolling(true);
    try {
      const response = await getProcessingJob(jobId);
      const nextJob = response.data;
      setJob(nextJob);
      setError(null);
      pollCountRef.current += 1;
      if (isProcessingJobTerminal(nextJob)) {
        stop();
        onTerminal?.(nextJob);
        return;
      }
      const backoff = Math.min(intervalMs * Math.max(1, pollCountRef.current), intervalMs * 4);
      timerRef.current = setTimeout(poll, backoff);
    } catch (err) {
      setError(err);
      pollCountRef.current += 1;
      if (pollCountRef.current >= maxPolls) {
        stop();
        return;
      }
      timerRef.current = setTimeout(poll, intervalMs * 2);
    } finally {
      inFlightRef.current = false;
    }
  }, [enabled, intervalMs, jobId, maxPolls, onTerminal, stop]);

  useEffect(() => {
    stoppedRef.current = false;
    pollCountRef.current = 0;
    setJob(initialJob);
    setError(null);
    setIsPolling(Boolean(enabled && jobId));

    if (!enabled || !jobId) {
      stop();
      return undefined;
    }
    if (isProcessingJobTerminal(initialJob)) {
      setIsPolling(false);
      onTerminal?.(initialJob);
      return undefined;
    }

    poll();
    return stop;
  }, [enabled, initialJob, jobId, onTerminal, poll, stop]);

  return {
    job,
    error,
    isPolling,
    stop,
    isTerminal: isProcessingJobTerminal(job)
  };
}
