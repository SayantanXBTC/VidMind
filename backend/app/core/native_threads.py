"""Native thread-pool pinning shared by the API and the worker.

Import this module before any ML library (see the comment below).
"""
import os

# Must be set before any ML-library import happens (including transitively,
# via app.api.routes below). This process loads three native-threaded CPU
# inference stacks in sequence within one long-lived server process:
# ctranslate2 (faster-whisper), torch (transformers, sentence-transformers),
# and faiss. Each manages its own thread pool / OpenMP runtime, and letting
# them initialize concurrently under uvicorn's event loop causes a
# non-deterministic SIGSEGV with no Python traceback — reproduced directly:
# same code crashes maybe 1 run in 5, passes clean otherwise. Pinning every
# library to single-threaded native execution removes the race. This costs
# some inference speed; for this local, one-video-at-a-time app, a server
# that never silently dies is worth far more than a few seconds of CPU time.
os.environ.setdefault("HF_DEACTIVATE_ASYNC_LOAD", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

