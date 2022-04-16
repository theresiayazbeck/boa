from collections import defaultdict
from typing import Any, Dict, Iterable, Set

from ax.core.base_trial import BaseTrial, TrialStatus
from ax.core.runner import Runner
from ax.core.trial import Trial

from optiwrap.wrapper_utils import get_trial_dir, make_trial_dir, run_model, write_configs


class QueueJobRunner(Runner):  # Deploys trials to external system.
    def __init__(self, queue, *args, **kwargs):
        self.queue = queue
        super().__init__(*args, **kwargs)

    def run(self, trial: Trial) -> Dict[str, Any]:
        """Deploys a trial based on custom runner subclass implementation.

        Args:
            trial: The trial to deploy.

        Returns:
            Dict of run metadata from the deployment process.
        """
        if not isinstance(trial, Trial):
            raise ValueError("This runner only handles `Trial`.")

        job_id = self.queue.schedule_job(trial=trial)
        # This run metadata will be attached to trial as `trial.run_metadata`
        # by the base `Scheduler`.
        return {"job_id": job_id}

    def poll_trial_status(self, trials: Iterable[BaseTrial]) -> Dict[TrialStatus, Set[int]]:
        """Checks the status of any non-terminal trials and returns their
        indices as a mapping from TrialStatus to a list of indices. Required
        for runners used with Ax ``Scheduler``.

        NOTE: Does not need to handle waiting between polling calls while trials
        are running; this function should just perform a single poll.

        Args:
            trials: Trials to poll.

        Returns:
            A dictionary mapping TrialStatus to a list of trial indices that have
            the respective status at the time of the polling. This does not need to
            include trials that at the time of polling already have a terminal
            (ABANDONED, FAILED, COMPLETED) status (but it may).
        """
        status_dict = defaultdict(set)
        for trial in trials:
            print(f"{trial.index=}")
            status = self.queue.get_job_status(trial=trial)
            status_dict[status].add(trial.index)

        return status_dict


class WrappedJobRunner(Runner):  # Deploys trials to external system.
    def __init__(self, wrapper, *args, **kwargs):

        self.wrapper = wrapper
        super().__init__(*args, **kwargs)

    def run(self, trial: BaseTrial) -> Dict[str, Any]:
        """Deploys a trial based on custom runner subclass implementation.

        Args:
            trial: The trial to deploy.

        Returns:
            Dict of run metadata from the deployment process.
        """
        if not isinstance(trial, Trial):
            raise ValueError("This runner only handles `Trial`.")

        self.wrapper.run_model(trial)
        # This run metadata will be attached to trial as `trial.run_metadata`
        # by the base `Scheduler`.
        return {"job_id": trial.index}

    def poll_trial_status(self, trials: Iterable[BaseTrial]) -> Dict[TrialStatus, Set[int]]:
        """Checks the status of any non-terminal trials and returns their
        indices as a mapping from TrialStatus to a list of indices. Required
        for runners used with Ax ``Scheduler``.

        NOTE: Does not need to handle waiting between polling calls while trials
        are running; this function should just perform a single poll.

        Args:
            trials: Trials to poll.

        Returns:
            A dictionary mapping TrialStatus to a list of trial indices that have
            the respective status at the time of the polling. This does not need to
            include trials that at the time of polling already have a terminal
            (ABANDONED, FAILED, COMPLETED) status (but it may).
        """
        status_dict = defaultdict(set)
        for trial in trials:
            print(f"{trial.index=}")
            self.wrapper.set_trial_status(trial)
            status_dict[trial.status].add(trial.index)

        return status_dict