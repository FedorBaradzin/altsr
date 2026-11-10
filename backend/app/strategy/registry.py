"""Реестр стратегий с версионированием (ТЗ §5).

In-memory, детерминированный, без БД (персистентность — в `store.py`). Хранит по
каждому ключу стратегии историю версий и текущее состояние жизненного цикла.
Новая версия добавляется с номером previous+1; конфигурация версий неизменяема.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from .lifecycle import StrategyEvent, next_state
from .types import StrategyDefinition, StrategyState, StrategyVersion


@dataclass
class _Entry:
    key: str
    name: str
    state: StrategyState
    versions: list[StrategyVersion] = field(default_factory=list)


class StrategyRegistry:
    """Реестр: регистрация стратегий, версий и переходов состояния."""

    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}

    def register(
        self, key: str, name: str, version: StrategyVersion
    ) -> StrategyDefinition:
        """Регистрирует новую стратегию в состоянии CANDIDATE с версией 1."""
        if key in self._entries:
            raise ValueError(f"стратегия {key!r} уже зарегистрирована")
        if version.version != 1:
            raise ValueError("первая версия стратегии должна иметь номер 1")
        self._entries[key] = _Entry(key=key, name=name, state="CANDIDATE",
                                     versions=[version])
        return self.get(key)

    def add_version(
        self, key: str, *, notional_usd: float | None = None, **changes
    ) -> StrategyVersion:
        """Добавляет новую версию (номер = предыдущий + 1) на базе текущей."""
        entry = self._require(key)
        current = entry.versions[-1]
        fields: dict[str, object] = dict(changes)
        if notional_usd is not None:
            fields["notional_usd"] = notional_usd
        new_version = replace(current, version=current.version + 1, **fields)
        entry.versions.append(new_version)
        return new_version

    def transition(self, key: str, event: StrategyEvent) -> StrategyDefinition:
        """Переводит стратегию по жизненному циклу; бросает IllegalTransition."""
        entry = self._require(key)
        entry.state = next_state(entry.state, event)
        return self.get(key)

    def get(self, key: str) -> StrategyDefinition:
        """Снимок стратегии с текущей (последней) версией."""
        entry = self._require(key)
        return StrategyDefinition(
            key=entry.key,
            name=entry.name,
            state=entry.state,
            current_version=entry.versions[-1],
        )

    def versions(self, key: str) -> tuple[StrategyVersion, ...]:
        """Полная история версий (по возрастанию номера)."""
        return tuple(self._require(key).versions)

    def list_keys(self) -> tuple[str, ...]:
        return tuple(self._entries.keys())

    def _require(self, key: str) -> _Entry:
        try:
            return self._entries[key]
        except KeyError:
            raise KeyError(f"стратегия {key!r} не найдена") from None
