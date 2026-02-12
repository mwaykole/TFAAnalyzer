## RHOAI/ODH Component Reference

### Model Serving Components
| Component | Description | Common Failures |
|-----------|-------------|-----------------|
| **KServe** | Serverless inference platform | InferenceService not ready, predictor timeout |
| **InferenceService** | KServe CRD for model deployment | Status not Ready, revision failure |
| **vLLM** | High-performance LLM runtime (GPU) | OOM, CUDA errors, model loading timeout |
| **TGI** | Text Generation Inference | Memory issues, tokenizer errors |
| **ModelMesh** | Multi-model serving | Pod scheduling, model cache issues |
| **Caikit** | AI model runtime | gRPC errors, model format issues |

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
| **TrustyAI** | Model explainability | Service unavailable, metric collection failure |
| **Data Science Pipelines** | ML workflow orchestration | Pipeline run failure, artifact issues |
| **Workbenches** | Jupyter environments | PVC issues, image pull failures |

### Common Failure Patterns

**Infrastructure Issues:**
- `CRD not found` → Operator not installed or needs reconciliation
- `InferenceService not ready` → Model loading, resource constraints, or config error
- `Timeout waiting for pod` → Resource scheduling, image pull, or init container issues
- `OOMKilled` → Memory limit too low for model size
- `GPU unavailable` → Node selector, taint, or quota issues
- `CrashLoopBackOff` → Container startup failure, missing config/secrets
- `ImagePullBackOff` → Registry auth, image not found, network issue

**Test Automation Issues:**
- `TimeoutExpiredError` → Test wait time too short for operation
- `TimeoutSampler expired` → Polling timeout, resource not ready in time
- `AssertionError` → Wrong expected value OR product bug (check which)
- `fixture not found` → Test setup issue, missing dependency

**Product Bugs:**
- `500 Internal Server Error` → Backend service failure
- `gRPC UNAVAILABLE` → Service mesh or endpoint issue
- `Model prediction failed` → Inference runtime error
- `Version mismatch` → Compatibility issue between components

**Intermittent Failures:**
- `Connection reset` → Network flakiness
- `upstream connect error` → Service mesh timing issue
- Tests marked `@pytest.mark.flaky` → Known flaky test
- Test passed on retry → Timing-dependent failure
