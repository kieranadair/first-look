"""Hosted TabPFN; no model weights or GPU are loaded by this app."""

from __future__ import annotations

import os
from threading import Lock
from typing import Any, Callable

from firstlook.config import Settings
from firstlook.contracts import clean
from firstlook.providers.base import ProviderError, safe_error

_AUTH_LOCK = Lock()


class TabPFNProvider:
    def __init__(self, settings: Settings, factory: Any = None):
        self.settings, self.factory = settings, factory

    def predict(self, task: str, x_train, y_train, x_test, progress: Callable[[str], None]):
        if not self.settings.available("tabpfn"):
            raise ProviderError("TabPFN is not configured. Local baselines are still available.")
        try:
            os.environ.setdefault("TABPFN_CLIENT_ASYNC_POLL_TIMEOUT", "120")
            os.environ.setdefault("TABPFN_CLIENT_TIMEOUT", "45")
            os.environ.setdefault("TABPFN_CLIENT_UPLOAD_TIMEOUT", "90")
            os.environ.setdefault("TABPFN_DISABLE_TELEMETRY", "1")
            if self.factory is None:
                import tabpfn_client

                # One owner credential, never a mutable credential from a visitor widget.
                with _AUTH_LOCK:
                    tabpfn_client.set_access_token(self.settings.tabpfn_token)
                factory = (
                    tabpfn_client.TabPFNRegressor if task == "regression" else tabpfn_client.TabPFNClassifier
                )
            else:
                factory = self.factory
            from tabpfn_client.models import ClientOptions

            model: Any = factory(
                model_path=self.settings.tabpfn_model_path,
                random_state=20261120,
                client_options=ClientOptions(timeout=45),
            )
            progress("Submitting the hosted model")
            model.submit_fit(x_train, y_train)
            record = clean(model.save_model())
            progress("Waiting for the accepted hosted fit")
            model.wait_for_fit()
            progress("Evaluating held-out rows")
            if task == "classification":
                model.submit_predict(x_test, output_type="probas")
            else:
                model.submit_predict(x_test)
            predictions = model.wait_for_predict()
            return predictions, clean(model.save_model()), record
        except Exception as exc:
            raise safe_error("TabPFN", exc) from exc
