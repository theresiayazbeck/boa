"""
Optimization wrapper for FETCH3.

These functions provide the interface between the optimization tool and FETCH3
- Setting up optimization experiment
- Creating directories for model outputs of each iteration
- Writing model configuration files for each iteration
- Starting model runs for each iteration
- Reading model outputs and observation data for model evaluation
- Defines objective function for optimization, and other performance metrics of interest
- Defines how results of each iteration should be evaluated
"""

import datetime as dt
import logging
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import xarray as xr
import yaml

logger = logging.getLogger(__file__)


@contextmanager
def cd_and_cd_back(path):
    cwd = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(cwd)


def load_experiment_config(config_file):
    """
    Read experiment configuration yml file for setting up the optimization.
    yml file contains the list of parameters, and whether each parameter is a fixed
    parameter or a range parameter. Fixed parameters have a value specified, and range
    parameters have a range specified.

    Parameters
    ----------
    config_file : str
        File path for the experiment configuration file

    Returns
    -------
    loaded_configs: dict
    """

    # Load the experiment config yml file
    with open(config_file, "r") as yml_config:
        config = yaml.safe_load(yml_config)

    return normalize_config(config)


def normalize_config(config):
    # Format parameters for Ax experiment
    for param in config.get("parameters", {}).keys():
        config["parameters"][param]["name"] = param  # Add "name" attribute for each parameter
    # Parameters from dictionary to list
    config["search_space_parameters"] = list(config.get("parameters", {}).values())
    config["search_space_parameter_constraints"] = config.get("parameter_constraints", [])

    return config


def make_experiment_dir(working_dir, experiment_name: str):
    """
    Creates directory for the experiment and returns the path.
    The directory is named with the experiment name and the current datetime.

    Parameters
    ----------
    working_dir : str
        Working directory, the parent directory where the experiment directory will be written
    experiment_name: str
        Name of the experiment

    Returns
    -------
    Path
        Path to the directory for the experiment
    """
    # Directory named with experiment name and datetime
    ex_dir = Path(working_dir) / f'{experiment_name}_{dt.datetime.now().strftime("%Y%m%dT%H%M%S")}'
    ex_dir.mkdir()
    return ex_dir


def get_trial_dir(experiment_dir, trial_index):
    """
    Return a directory for a trial,
    Trial directory is named with the trial index.

    Parameters
    ----------
    experiment_dir : Path
        Directory for the experiment
    trial_index : int
        Trial index from the Ax client

    Returns
    -------
    Path
        Directory for the trial
    """
    trial_dir = experiment_dir / str(trial_index).zfill(6)  # zero-padded trial index
    return trial_dir


def make_trial_dir(experiment_dir, trial_index):
    """
    Create a directory for a trial, and return the path to the directory.
    Trial directory is created inside the experiment directory, and named with the trial index.
    Model configs and outputs for each trial will be written here.

    Parameters
    ----------
    experiment_dir : Path
        Directory for the experiment
    trial_index : int
        Trial index from the Ax client

    Returns
    -------
    Path
        Directory for the trial
    """
    trial_dir = get_trial_dir(experiment_dir, trial_index)
    trial_dir.mkdir()
    return trial_dir


def write_configs(trial_dir, parameters, model_options):
    """
    Write model configuration file for each trial (model run). This is the config file used by FETCH3
    for the model run.

    The config file is written as ```config.yml``` inside the trial directory.

    Parameters
    ----------
    trial_dir : Path
        Trial directory where the config file will be written
    parameters : list
        Model parameters for the trial, generated by the ax client
    model_options : dict
        Model options loaded from the experiment config yml file.

    Returns
    -------
    str
        Path for the config file
    """
    with open(trial_dir / "config.yml", "w") as f:
        # Write model options from loaded config
        # Parameters for the trial from Ax
        config_dict = {"model_options": model_options, "parameters": parameters}
        yaml.dump(config_dict, f)
        return f.name


def run_model(model_path, config_path, data_path, output_path):
    """
    Runs FETCH3 for the trial.

    Parameters
    ----------
    model_path : str
        Path to the FETCH3 source code
    config_path : Path
        Path to the config file for the run.
    output_path : Path
        Path to write the model output

    ..todo::
        Will need to update with input directory once this option is added
    """

    with cd_and_cd_back(model_path):
        args = [
            "python3",
            "main.py",
            "--config_path",
            str(config_path),
            "--data_path",
            str(data_path),
            "--output_path",
            str(output_path),
        ]
        result = subprocess.run(
            args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        # TODO: try and catch non 0 exit code, subprocess has its own exception I think
        # TODO: but all of this runs inside its own thread. sooo that is a problem to solve
        # print("\n\n\n\n\n", result.returncode)
        # if result.returncode != 0:
        #     print("Bad result code!")
        #     print(result.stderr)
        #     import sys
        #     # sys.exit()
        #     raise SystemExit(result.returncode) from Exception(result.stderr)

        print(result.stdout)
        print(result.stderr)
        print("Done running model")


def get_model_obs(modelfile, obsfile, ex_settings, model_settings, parameters):
    """
    Read in observation data model output for a trial, which will be used for
    calculating the objective function for the trial.

    Parameters
    ----------
    modelfile : str
        File path to the model output
    obsfile : str
        File path to the observation data
    model_settings: dict
        dictionary with model settings read from model config file

    Returns
    -------
    model_output: pandas Series
        Model output
    obs: pandas Series
        Observations

    ..todo::
        * Add options to specify certain variables from the observation/output files
        * Add option to read from .nc file

    """
    # Read config file

    # Read in observation data
    obsdf = pd.read_csv(obsfile, parse_dates=[0])
    obsdf = obsdf.set_index("Timestamp")
    # metdf.index = metdf.index - pd.to_timedelta('30Min') # TODO: remove timestamp shift

    # Read in model output
    modeldf = xr.load_dataset(modelfile)

    # Slice met data to just the time period that was modeled
    obsdf = obsdf.loc[modeldf.time.data[0] : modeldf.time.data[-1]]

    # Convert model output to the same units as the input data
    modeldf["trans_scaled"] = scale_transpiration(
        modeldf.trans_2d,
        model_settings["dz"],
        parameters["mean_crown_area_sp"],
        parameters["total_crown_area_sp"],
        parameters["plot_area"],
    )

    return modeldf.trans_scaled.data, obsdf[ex_settings["obsvar"]]


def scale_transpiration(trans, dz, mean_crown_area_sp, total_crown_area_sp, plot_area):
    """Scales transpiration from FETCH output (in m H20 m-1stem s-1) to W m-2"""
    scaled_trans = (
        trans * 1000 * dz * 2440000 / mean_crown_area_sp * total_crown_area_sp / plot_area
    ).sum(dim="z", skipna=True)
    return scaled_trans
