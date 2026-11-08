from abc import ABC, abstractmethod

from app.pipeline.state import PipelineState


class BaseAgent(ABC):
    name: str = "agent"

    @abstractmethod
    async def run(self, state: PipelineState, **kwargs) -> PipelineState:
        raise NotImplementedError
