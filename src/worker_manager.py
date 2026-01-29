"""Worker Manager - Manages worker lifecycle on macOS host."""

import asyncio
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

import uvicorn
from fastapi import FastAPI, HTTPException

from src.core.config import get_config, ModelConfig
from src.core.memory import get_memory_status, get_model_memory_requirement


@dataclass
class WorkerProcess:
    alias: str
    process: subprocess.Popen
    port: int
    model_path: str
    model_type: str
    memory_gb: float
    started_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    request_count: int = 0


class WorkerManager:
    """Manages worker processes on macOS host."""

    def __init__(self):
        self.config = get_config()
        self.workers: Dict[str, WorkerProcess] = {}
        self._lock = asyncio.Lock()
        self._running = True
        self._next_port = self.config.workers.base_port

    def _get_next_port(self) -> int:
        """Get next available port."""
        port = self._next_port
        self._next_port += 1
        return port

    def _get_worker_command(self, model_config: ModelConfig, alias: str, port: int) -> list:
        """Get command to spawn worker."""
        if model_config.type == "stt":
            module = "src.workers.stt_worker"
        elif model_config.type == "tts":
            module = "src.workers.tts_worker"
        else:
            raise ValueError(f"Unknown model type: {model_config.type}")

        return [
            sys.executable,
            "-m",
            module,
            "--alias",
            alias,
            "--model_path",
            model_config.path,
            "--port",
            str(port),
        ]

    async def spawn_worker(self, alias: str) -> WorkerProcess:
        """Spawn a new worker or return existing one."""
        async with self._lock:
            # Return existing worker
            if alias in self.workers:
                worker = self.workers[alias]
                worker.last_used = time.time()
                return worker

            # Get model config
            if alias not in self.config.models:
                raise HTTPException(status_code=404, detail=f"Model not found: {alias}")

            model_config = self.config.models[alias]
            memory_needed = get_model_memory_requirement(model_config.path, model_config.type)

            # Check memory and evict if needed
            await self._evict_for_memory(memory_needed)

            # Spawn worker
            port = self._get_next_port()
            cmd = self._get_worker_command(model_config, alias, port)

            print(f"Spawning worker: {alias} on port {port}")
            print(f"Command: {' '.join(cmd)}")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )

            worker = WorkerProcess(
                alias=alias,
                process=process,
                port=port,
                model_path=model_config.path,
                model_type=model_config.type,
                memory_gb=memory_needed,
            )

            # Wait for worker to be ready
            await self._wait_for_worker(worker)

            self.workers[alias] = worker
            print(f"Worker started: {alias} (PID: {process.pid}, port: {port})")
            return worker

    async def _wait_for_worker(self, worker: WorkerProcess, timeout: int = None):
        """Wait for worker to become healthy."""
        import httpx

        timeout = timeout or self.config.workers.startup_timeout
        start = time.time()

        while time.time() - start < timeout:
            # Check if process died
            if worker.process.poll() is not None:
                stdout, _ = worker.process.communicate()
                raise RuntimeError(f"Worker {worker.alias} died: {stdout.decode()}")

            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    response = await client.get(f"http://localhost:{worker.port}/health")
                    if response.status_code == 200:
                        return
            except httpx.HTTPError:
                pass

            await asyncio.sleep(0.5)

        raise RuntimeError(f"Worker {worker.alias} failed to start within {timeout}s")

    async def _evict_for_memory(self, needed_gb: float):
        """Evict workers if needed to free memory."""
        status = get_memory_status()
        safety = self.config.memory.safety_margin_gb
        available = status.available_gb - safety

        if available >= needed_gb:
            return

        # Sort workers by last_used (LRU)
        sorted_workers = sorted(
            self.workers.values(),
            key=lambda w: w.last_used,
        )

        for worker in sorted_workers:
            if available >= needed_gb:
                break

            print(f"Evicting worker for memory: {worker.alias} ({worker.memory_gb}GB)")
            self.stop_worker(worker.alias)
            available += worker.memory_gb

    def stop_worker(self, alias: str) -> bool:
        """Stop a worker process."""
        if alias not in self.workers:
            return False

        worker = self.workers.pop(alias)

        try:
            # Try graceful shutdown
            os.killpg(os.getpgid(worker.process.pid), signal.SIGTERM)
            try:
                worker.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill
                os.killpg(os.getpgid(worker.process.pid), signal.SIGKILL)
                worker.process.wait()
        except ProcessLookupError:
            pass

        print(f"Worker stopped: {alias}")
        return True

    def touch_worker(self, alias: str):
        """Update last-used timestamp for a worker."""
        if alias in self.workers:
            self.workers[alias].last_used = time.time()
            self.workers[alias].request_count += 1

    async def _monitor_idle_workers(self):
        """Background task to stop idle workers."""
        idle_timeout = self.config.workers.idle_timeout_seconds
        interval = self.config.workers.health_check_interval

        while self._running:
            await asyncio.sleep(interval)

            now = time.time()
            to_evict = []

            for alias, worker in self.workers.items():
                idle_time = now - worker.last_used
                if idle_time > idle_timeout:
                    to_evict.append(alias)

            for alias in to_evict:
                print(f"Evicting idle worker: {alias}")
                self.stop_worker(alias)

    def stop_all(self):
        """Stop all workers."""
        for alias in list(self.workers.keys()):
            self.stop_worker(alias)

    def get_status(self) -> dict:
        """Get status of all workers and memory."""
        memory = get_memory_status()
        return {
            "memory": {
                "total_gb": round(memory.total_gb, 2),
                "used_gb": round(memory.used_gb, 2),
                "available_gb": round(memory.available_gb, 2),
                "usage_percent": round(memory.usage_percent, 1),
            },
            "workers": {
                alias: {
                    "port": w.port,
                    "model_path": w.model_path,
                    "model_type": w.model_type,
                    "memory_gb": w.memory_gb,
                    "uptime_seconds": int(time.time() - w.started_at),
                    "idle_seconds": int(time.time() - w.last_used),
                    "request_count": w.request_count,
                }
                for alias, w in self.workers.items()
            },
        }


# FastAPI app for Worker Manager
app = FastAPI(title="Voice Insight Worker Manager")
manager = WorkerManager()


@app.on_event("startup")
async def startup():
    asyncio.create_task(manager._monitor_idle_workers())


@app.on_event("shutdown")
async def shutdown():
    manager._running = False
    manager.stop_all()


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/status")
async def status():
    return manager.get_status()


@app.post("/spawn/{alias}")
async def spawn(alias: str):
    worker = await manager.spawn_worker(alias)
    return {
        "alias": worker.alias,
        "port": worker.port,
        "memory_gb": worker.memory_gb,
        "model_type": worker.model_type,
    }


@app.post("/touch/{alias}")
async def touch(alias: str):
    manager.touch_worker(alias)
    return {"success": True}


@app.post("/stop/{alias}")
async def stop(alias: str):
    success = manager.stop_worker(alias)
    return {"success": success}


@app.post("/stop-all")
async def stop_all():
    manager.stop_all()
    return {"success": True}


def main():
    config = get_config()
    uvicorn.run(
        "src.worker_manager:app",
        host="0.0.0.0",
        port=config.workers.manager_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
