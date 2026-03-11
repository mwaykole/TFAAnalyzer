## RHOAI/ODH Component Reference

### KServe Resource Hierarchy (CRITICAL for Root Cause Analysis)

When a model serving test times out, the **real root cause** is NOT the timeout itself.
You MUST trace the KServe resource chain to find the actual error:

```
InferenceService (ISVC) / LLMInferenceService (LLMISVC)
  └─ Predictor / Transformer / Explainer
       └─ Knative Revision (serverless) OR Deployment (raw)
            └─ Pod(s)
                 └─ Containers: storage-initializer, kserve-container, queue-proxy
```

**Diagnosis chain for timeouts:**
1. Check InferenceService/LLMISVC `.status.conditions` — look for non-Ready conditions with error messages
2. Check ServingRuntime/ClusterServingRuntime — is the runtime properly configured?
3. Check Predictor pod status — is it stuck in Pending, CrashLoopBackOff, ImagePullBackOff?
4. Check container logs — storage-initializer (S3/model download), kserve-container (model load)
5. Check events — scheduling failures, resource quota, image pull errors

**Common KServe/RHOAI status condition errors (from CR .status.conditions):**
- `"no matches for kind X"` → Missing CRD/operator dependency → **Product Bug** (component not installed)
- `"failed to reconcile"` → Operator reconciliation error → **Product Bug**
- `"IngressNotConfigured"` → Knative/Istio misconfiguration → **Infrastructure Issue**
- `"RevisionFailed"` → Container crash during startup → check pod logs
- `"LatestCreatedRevisionNotReady"` → Model failed to load → check storage-initializer and kserve-container logs

### LLMD (LLM Distributed) / Multi-Node Inference
| Resource | Description | Key Dependencies |
|----------|-------------|------------------|
| **LLMInferenceService** | LLMD CRD for distributed LLM serving | Requires LeaderWorkerSet CRD |
| **LeaderWorkerSet (LWS)** | Kubernetes CRD for leader-worker deployments | Must be pre-installed on cluster |
| **ServingRuntime** | Defines model runtime (vLLM, TGI, etc.) | Must match model format |

**LLMD failure patterns:**
- `"no matches for kind LeaderWorkerSet"` → LWS CRD not installed → **Product Bug** (missing dependency)
- `"failed to build the expected main LWS"` → LLMD reconciler cannot create worker sets → **Product Bug**
- `"failed to reconcile multi-node main workload"` → Orchestration failure → **Product Bug**

### Model Serving Components
| Component | Description | Common Failures |
|-----------|-------------|-----------------|
| **KServe** | Serverless inference platform | InferenceService not ready, predictor timeout |
| **InferenceService** | KServe CRD for model deployment | Status not Ready, revision failure |
| **LLMInferenceService** | LLMD CRD for distributed LLM serving | LeaderWorkerSet missing, reconcile failure |
| **ServingRuntime** | Runtime config (vLLM, TGI, Caikit) | Missing runtime, wrong model format |
| **ClusterServingRuntime** | Cluster-scoped runtime config | Same as ServingRuntime but cluster-wide |
| **vLLM** | High-performance LLM runtime (GPU) | OOM, CUDA errors, model loading timeout |
| **TGI** | Text Generation Inference | Memory issues, tokenizer errors |
| **ModelMesh** | Multi-model serving | Pod scheduling, model cache issues |
| **Caikit** | AI model runtime | gRPC errors, model format issues |

### KServe Deployment Modes
| Mode | How It Works | Failure Signatures |
|------|-------------|-------------------|
| **Serverless (Knative)** | Scale-to-zero, cold starts | `RevisionFailed`, `IngressNotConfigured`, Knative route errors |
| **RawDeployment** | Standard K8s Deployment | Pod scheduling, resource limits, no Knative dependency |
| **ModelMesh** | Shared runtime pods | Model cache, runtime pod crashes, gRPC errors |

### Distributed Computing Components
| Component | Description | Common Failures |
|-----------|-------------|-----------------|
| **Kueue** | Kubernetes batch scheduler | Queue admission, ResourceFlavor mismatch |
| **CodeFlare** | Distributed ML orchestration | Cluster creation timeout, worker failures |
| **Ray** | Distributed execution framework | Head node failure, worker OOM |
| **KubeRay** | Ray on Kubernetes operator | RayCluster not ready, GCS failure |

### Platform Components
| Component | Description | Common Failures |
|-----------|-------------|-----------------|
| **DSC (DataScienceCluster)** | Top-level RHOAI CR | Component reconciliation failures |
| **DSCI (DSCInitialization)** | Cluster initialization CR | Auth, monitoring setup failures |
| **TrustyAI** | Model explainability | Service unavailable, metric collection failure |
| **Data Science Pipelines** | ML workflow orchestration | Pipeline run failure, artifact issues |
| **Workbenches** | Jupyter environments | PVC issues, image pull failures |

### RHOAI Operator Namespaces
- `redhat-ods-operator` — RHOAI operator pods
- `redhat-ods-applications` — Component deployments (dashboard, model controller, etc.)
- `rhods-notebooks` — Workbench/notebook pods
- `redhat-ods-monitoring` — Monitoring stack
- `istio-system` / `knative-serving` — Service mesh and serverless infrastructure

### Common Failure Patterns

**Product Bugs (check CR status conditions first!):**
- `"no matches for kind"` → Missing CRD dependency (e.g., LeaderWorkerSet for LLMD)
- `"failed to reconcile"` → Operator/controller reconciliation error
- `"RevisionFailed"` with container error → Model runtime crash
- `500 Internal Server Error` → Backend service failure
- `gRPC UNAVAILABLE` → Inference endpoint failure
- `Model prediction failed` → Inference runtime error
- Service never becomes Ready despite generous timeout + healthy cluster → Component is broken

**Infrastructure Issues:**
- `CRD not found` → Operator not installed or needs reconciliation
- `InferenceService not ready` + unhealthy cluster → Resource constraints or config error
- `OOMKilled` → Memory limit too low for model size
- `GPU unavailable` → Node selector, taint, or quota issues
- `CrashLoopBackOff` → Container startup failure, missing config/secrets
- `ImagePullBackOff` → Registry auth, image not found, network issue
- `IngressNotConfigured` → Knative/Istio/service mesh not ready

**Test Automation Issues:**
- `TimeoutExpiredError` with short timeout (< 120s) → Test wait time too short for operation
- `TimeoutSampler expired` with short timeout → Polling timeout, increase wait time
- `AssertionError` → Wrong expected value OR product bug (check which)
- `fixture not found` → Test setup issue, missing dependency

**Product Bugs (timeout-related):**
- `TimeoutExpiredError` with generous timeout (≥ 300s) + healthy cluster → Service/component failing to start or respond
- Service passes readiness but fails inference/operations → Product defect
- 0% pass rate with generous timeout → Product is consistently broken

**Intermittent Failures:**
- `Connection reset` → Network flakiness
- `upstream connect error` → Service mesh timing issue
- Tests marked `@pytest.mark.flaky` → Known flaky test
- Test passed on retry → Timing-dependent failure
