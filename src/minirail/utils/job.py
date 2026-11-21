"""Business-logic units.

A job is a dataclass owning one business operation (create a booking, confirm
it, ...). It composes services and fetchers, runs inside its caller's
transaction, and NEVER commits — flushing is fine, the commit belongs to the
api/actor/cli layer that owns the unit of work.

Two entry points, one per kind of caller:

- ``call_for_api()`` returns the output and lets business exceptions
  propagate: the API exception handler turns any MinirailException into a
  structured HTTP error from its ``http_status_code``/``error_code``.
- ``call()`` returns a JobResult and only catches the exceptions the job
  *declared* in ``business_exceptions``. Anything undeclared is a bug and
  keeps propagating — an actor crash (and retry) is better than silently
  swallowing a programming error.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

from minirail.utils.app import get_app
from minirail.utils.exc import MinirailException


@dataclass
class JobResult[OutputT]:
    success: bool
    output: OutputT | None = None
    error: MinirailException | None = None


@dataclass(kw_only=True)
class BaseJob[OutputT](ABC):
    """Subclasses declare their inputs as dataclass fields, list their
    expected business exceptions, and implement _call() ending with
    self.set_output(...)."""

    business_exceptions: ClassVar[tuple[type[MinirailException], ...]] = ()

    _output: OutputT | None = field(default=None, init=False, repr=False)

    @abstractmethod
    def _call(self) -> None: ...

    def set_output(self, output: OutputT) -> None:
        self._output = output

    def call_for_api(self) -> OutputT:
        self._call()
        return self._require_output()

    def call(self) -> JobResult[OutputT]:
        try:
            self._call()
        except self.business_exceptions as exc:
            get_app().logger.info("%s failed: %s", type(self).__name__, exc.message)
            return JobResult(success=False, error=exc)
        return JobResult(success=True, output=self._require_output())

    def _require_output(self) -> OutputT:
        if self._output is None:
            raise RuntimeError(f"{type(self).__name__}._call() completed without calling set_output()")
        return self._output
