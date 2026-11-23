from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class Ctx:
    """Contexto passado para os pipelines: atualizar progresso e somar custo."""

    job_id: int
    params: dict
    settings: dict
    report: Callable[[int, str], None]
    add_cost: Callable[[float], None]
    log: Callable[[str], None]
    cancelled: Callable[[], bool] = field(default=lambda: False)


class Cancelled(RuntimeError):
    pass
