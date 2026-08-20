from datetime import datetime
from typing import Literal

from pydantic import Field

from app.buy_request_schemas import InputModel


class AgentEnrollmentCreateIn(InputModel):
    expires_in_minutes: int = Field(default=20, ge=5, le=60)


class AgentGpuInventory(InputModel):
    index: int = Field(ge=0, le=255)
    name: str = Field(min_length=1, max_length=128)
    memory_total_mb: int = Field(ge=0, le=1_073_741_824)
    uuid: str | None = Field(default=None, max_length=128)
    driver_version: str | None = Field(default=None, max_length=64)


class AgentHardwareInventory(InputModel):
    collected_at: datetime
    source: Literal["host", "docker", "local_simulator"]
    os_name: str = Field(min_length=1, max_length=128)
    os_version: str = Field(default="", max_length=128)
    kernel_version: str = Field(default="", max_length=128)
    cpu_model: str = Field(min_length=1, max_length=256)
    cpu_logical_cores: int = Field(ge=1, le=65_536)
    memory_total_mb: int = Field(ge=0, le=1_073_741_824)
    disk_total_gb: int = Field(ge=0, le=100_000_000)
    disk_available_gb: int = Field(ge=0, le=100_000_000)
    gpus: list[AgentGpuInventory] = Field(default_factory=list, max_length=256)
    collection_errors: list[str] = Field(default_factory=list, max_length=32)


class AgentSshServiceCheck(InputModel):
    reachable: bool
    port: int = Field(ge=1, le=65535)
    error: str | None = Field(default=None, max_length=255)


class AgentServiceChecks(InputModel):
    checked_at: datetime
    ssh: AgentSshServiceCheck


class AgentEnrollIn(InputModel):
    enrollment_token: str = Field(min_length=32, max_length=256)
    device_public_key: str = Field(min_length=40, max_length=128)
    platform: str = Field(pattern=r"^(linux|windows)$")
    arch: str = Field(pattern=r"^(amd64|arm64)$")
    hostname: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=32)
    capabilities: list[str] = Field(default_factory=list, max_length=16)
    inventory: AgentHardwareInventory | None = None
    service_checks: AgentServiceChecks | None = None


class AgentHeartbeatIn(InputModel):
    version: str = Field(min_length=1, max_length=32)
    hostname: str = Field(min_length=1, max_length=128)
    platform: str = Field(pattern=r"^(linux|windows)$")
    arch: str = Field(pattern=r"^(amd64|arm64)$")
    capabilities: list[str] = Field(default_factory=list, max_length=16)
    inventory: AgentHardwareInventory | None = None
    service_checks: AgentServiceChecks | None = None


class AgentCommandResultIn(InputModel):
    success: bool
    message: str = Field(default="", max_length=500)
