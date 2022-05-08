from __future__ import annotations

from functools import partial
from typing import Callable, Optional

import numpy as np
import pandas as pd
import sklearn.metrics
from ax import Data, Metric
from ax.metrics.noisy_function import NoisyFunctionMetric
from ax.core.base_trial import BaseTrial
from ax.core.data import Data
from ax.core.types import TParameterization
from ax.utils.measurement.synthetic_functions import FromBotorch, from_botorch
from ax.storage.json_store.encoders import metric_to_dict
import ax.utils.measurement.synthetic_functions
import botorch.test_functions.synthetic

from optiwrap.metrics.metric_funcs import metric_from_json, metric_from_yaml
from optiwrap.utils import get_dictionary_from_callable, serialize_init_args
from optiwrap.wrapper import BaseWrapper
from optiwrap.metaclasses import MetricRegister
import optiwrap.metrics.synthethic_funcs


def get_metric_from_config(config, **kwargs):
    if config.get("metric_name"):
        if config.get("sklearn_metric"):
            kwargs["sklearn_metric"] = config["sklearn_metric"]
        return get_metric_by_class_name(config["metric_name"], **kwargs)
    if config.get("synthetic_metric"):
        return setup_synthetic_metric(config["synthetic_metric"], **kwargs)


def get_metric_by_class_name(metric_cls_name, sklearn_metric=False, **kwargs):
    if sklearn_metric:
        return setup_sklearn_metric(metric_cls_name, **kwargs)
    return globals()[metric_cls_name]


def setup_sklearn_metric(metric_to_eval, **kw):
    if metric_to_eval in sklearn.metrics.__all__:
        metric = getattr(sklearn.metrics, metric_to_eval)
    else:
        raise AttributeError(f"Sklearn metric: {metric_to_eval} not found!")

    def modular_sklearn_metric(**kwargs):
        return ModularMetric(**{**kw, **kwargs, "metric_to_eval": metric})

    return modular_sklearn_metric


def setup_synthetic_metric(metric_to_eval, **kw):
    synthetic_funcs_modules = [
        optiwrap.metrics.synthethic_funcs,
        ax.utils.measurement.synthetic_functions,
        botorch.test_functions.synthetic
    ]

    def get_synth_metric():
        for module in synthetic_funcs_modules:
            try:
                return getattr(module, metric_to_eval)
            except AttributeError:
                continue
        # If we don't find the class by the end of the modules, raise attribute error
        raise AttributeError(
            f"optiwrap synthetic function: {metric_to_eval}"
            f" not found in modules: {synthetic_funcs_modules}!"
        )

    metric = get_synth_metric()

    if issubclass(metric, ax.utils.measurement.synthetic_functions):
        metric = metric()  # if they pass a ax synthetic metric class, not instance
    if issubclass(metric, botorch.test_functions.synthetic.SyntheticTestFunction):
        # botorch synthetic functions need to be converted
        metric = from_botorch(botorch_synthetic_function=metric())

    def modular_synthetic_metric(**kwargs):
        return ModularMetric(**{**kw, **kwargs, "metric_to_eval": metric})

    return modular_synthetic_metric


def _get_name(obj):
    if hasattr(obj, "__name__"):
        return obj.__name__
    elif isinstance(obj, FromBotorch):
        # Using metrics that are FromBotorch(botorch synthethic_funcs) leaves us with
        # with having to rely on a private attribute to get to the funcs __name__
        # watch for breaking someday
        obj = obj._botorch_function
    elif isinstance(obj, partial):
        obj = obj.func
    else:
        obj = obj.__class__
    return _get_name(obj)


class ModularMetric(NoisyFunctionMetric):
    def __init__(
        self,
        metric_to_eval: Callable,
        param_names: list[str] = None,
        noise_sd: Optional[float] = 0.0,
        metric_func_kwargs: Optional[dict] = None,
        wrapper: Optional[BaseWrapper] = None,
        properties: Optional[dict[str]] = None,
        **kwargs,
    ):

        if kwargs.get("name") is None:
            kwargs["name"] = _get_name(metric_to_eval)
        param_names = param_names if param_names is not None else []
        self.metric_func_kwargs = metric_func_kwargs or {}
        # self.metric_to_eval = partial(metric_to_eval, **self.metric_func_kwargs)
        self.metric_to_eval = metric_to_eval
        self.wrapper = wrapper
        self.properties = properties
        super().__init__(param_names=param_names, noise_sd=noise_sd, **kwargs)

    @classmethod
    def is_available_while_running(cls) -> bool:
        return False

    def fetch_trial_data(self, trial: BaseTrial, *args, **kwargs):
        wrapper_kwargs = (
            self.wrapper.fetch_trial_data(trial=trial, *args, **kwargs) if self.wrapper else {}
        )
        wrapper_kwargs = wrapper_kwargs or {}
        safe_kwargs = {"trial": trial, **kwargs, **wrapper_kwargs}
        if isinstance(self.metric_to_eval, Metric):
            return self.metric_to_eval.fetch_trial_data(
                *args,
                **get_dictionary_from_callable(self.metric_to_eval.fetch_trial_data, safe_kwargs),
            )
        else:
            return self._fetch_trial_data_of_func(*args, **safe_kwargs)

    def _fetch_trial_data_of_func(self, trial: BaseTrial, noisy: bool = True, **kwargs) -> Data:
        noise_sd = self.noise_sd if noisy else 0.0
        arm_names = []
        mean = []
        for name, arm in trial.arms_by_name.items():
            arm_names.append(name)
            val = self._evaluate(params=arm.parameters, **kwargs)
            if noise_sd:
                val = val + noise_sd * np.random.randn()
            mean.append(val)
        # indicate unknown noise level in data
        if noise_sd is None:
            noise_sd = float("nan")
        df = pd.DataFrame(
            {
                "arm_name": arm_names,
                "metric_name": self.name,
                "mean": mean,
                "sem": noise_sd,
                "trial_index": trial.index,
            }
        )
        return Data(df=df)

    def _evaluate(self, params: TParameterization, **kwargs) -> float:
        kwargs["x"] = np.array([params[p] for p in self.param_names if p in params])
        return self.metric_to_eval(**get_dictionary_from_callable(self.metric_to_eval, kwargs))

    def clone(self) -> "Metric":
        """Create a copy of this Metric."""
        cls = type(self)
        return cls(**serialize_init_args(self, parents=[NoisyFunctionMetric], match_private=True),)

    def __repr__(self) -> str:
        init_dict = serialize_init_args(self, parents=[NoisyFunctionMetric], match_private=True)
        init_dict = {k: v for k, v in init_dict.items() if v}

        if isinstance(init_dict["metric_to_eval"], partial):
            init_dict["metric_to_eval"] = init_dict["metric_to_eval"].func

        arg_str = " ".join(f"{k}={v}" for k, v in init_dict.items())
        return f"{self.__class__.__name__}({arg_str})"


MSE = setup_sklearn_metric("mean_squared_error")
MeanSquaredError = MSE
RMSE = setup_sklearn_metric("mean_squared_error", metric_func_kwargs={"squared": False})
RootMeanSquaredError = RMSE
R2 = setup_sklearn_metric("r2_score")
RSquared = R2

MetricFromJSON = partial(ModularMetric, metric_to_eval=metric_from_json)
MetricFromYAML = partial(ModularMetric, metric_to_eval=metric_from_yaml)
