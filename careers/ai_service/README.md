# FairEnrol local Qwen service

This optional FastAPI service handles local CV/job reranking and job-description parsing. The FairEnrol API calls it from the Kind workloads; it is not exposed to the browser. Model weights stay outside Git and are mounted read-only.

## Start with Docker Compose

Set `FAIRENROL_MODELS_PATH` in the root `.env` to a directory containing both model folders:

```text
qwen3-4b-instruct/
qwen3-reranker-0.6b/
```

Then run from the FairEnrol repository root:

```powershell
npm.cmd run kind:ai
curl.exe http://127.0.0.1:8010/health
```

The service uses the local GPU and the root `.env` key `FAIRENROL_AI_KEY`. FairEnrol's API and worker send that key over the local Docker Desktop host bridge. Keep the service and its published port on this development machine.

## Run directly with Python

Install the CUDA-compatible PyTorch build for the machine, then install `careers/requirements-qwen.txt`. From the repository root:

```powershell
$env:QWEN_RERANKER_MODEL_PATH = "C:\path\to\models\qwen3-reranker-0.6b"
$env:JOB_PARSER_MODEL = "C:\path\to\models\qwen3-4b-instruct"
$env:AI_SERVICE_API_KEY = "<local development key>"
python -m uvicorn ai_service.app:app --app-dir careers --host 127.0.0.1 --port 8010
```

`/health` remains available for readiness checks. Other service requests require `X-AI-Service-Key` when a key is configured. Use the bundled request examples under `careers/ai_service/examples/` to test reranking and group scoring.
