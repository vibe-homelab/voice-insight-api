"""Supervisor for managing worker connections."""

import os
from dataclasses import dataclass
from typing import Optional

import httpx

from .config import get_config


@dataclass
class WorkerInfo:
    alias: str
    address: str
    port: int
    memory_gb: float
    model_type: str


class Supervisor:
    """Manages communication between Gateway and Worker Manager."""

    def __init__(self):
        self.config = get_config()
        manager_host = os.getenv("WORKER_MANAGER_HOST", "localhost")
        manager_port = self.config.workers.manager_port
        self.manager_url = f"http://{manager_host}:{manager_port}"

        worker_host = os.getenv("WORKER_HOST", "localhost")
        self.worker_host = worker_host

    async def _call_manager(
        self, method: str, endpoint: str, **kwargs
    ) -> Optional[dict]:
        """Make HTTP request to Worker Manager."""
        url = f"{self.manager_url}{endpoint}"
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                raise RuntimeError(f"Worker Manager error: {e}")

    def _get_worker_url(self, port: int) -> str:
        """Get worker URL from port."""
        return f"http://{self.worker_host}:{port}"

    async def get_worker(self, alias: str) -> WorkerInfo:
        """Get or spawn a worker for the given model alias."""
        result = await self._call_manager("POST", f"/spawn/{alias}")

        if not result:
            raise RuntimeError(f"Failed to spawn worker: {alias}")

        worker = WorkerInfo(
            alias=alias,
            address=self._get_worker_url(result["port"]),
            port=result["port"],
            memory_gb=result.get("memory_gb", 0),
            model_type=result.get("model_type", "unknown"),
        )

        # Touch worker to reset idle timer
        await self._call_manager("POST", f"/touch/{alias}")

        return worker

    async def touch_worker(self, alias: str) -> None:
        """Update last-used timestamp for a worker."""
        await self._call_manager("POST", f"/touch/{alias}")

    async def stop_worker(self, alias: str) -> bool:
        """Stop a specific worker."""
        result = await self._call_manager("POST", f"/stop/{alias}")
        return result.get("success", False) if result else False

    async def get_status(self) -> dict:
        """Get system status from Worker Manager."""
        return await self._call_manager("GET", "/status") or {}

    async def health_check(self) -> bool:
        """Check if Worker Manager is healthy."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.manager_url}/health")
                return response.status_code == 200
        except httpx.HTTPError:
            return False
