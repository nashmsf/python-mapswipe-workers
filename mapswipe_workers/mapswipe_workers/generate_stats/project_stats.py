import os
from psycopg2 import sql
import pandas as pd
import datetime
from typing import List
from mapswipe_workers import auth
from mapswipe_workers.definitions import logger, DATA_PATH
from mapswipe_workers.utils import geojson_functions
from mapswipe_workers.generate_stats import project_stats_by_date


def add_metadata_to_csv(filename: str):
    """
    Append a metadata line to the csv file about intended data usage.
    """

    with open(filename, "a") as fd:
        fd.write("# This data can only be used for editing in OpenStreetMap.")

    logger.info(f"added metadata to {filename}.")


def write_sql_to_csv(filename: str, sql_query: sql.SQL):
    """
    Use the copy statement to write data from postgres to a csv file.
    """

    pg_db = auth.postgresDB()
    with open(filename, "w") as f:
        pg_db.copy_expert(sql_query, f)
    logger.info(f"wrote csv file from sql: {filename}")


def load_df_from_csv(filename: str) -> pd.DataFrame:
    """
    Load a csv file into a pandas dataframe.
    Make sure that project_id, group_id and task_id are read as strings.
    """
    dtype_dict = {"project_id": str, "group_id": str, "task_id": str}

    df = pd.read_csv(filename, dtype=dtype_dict)
    logger.info(f"loaded pandas df from {filename}")
    return df


def get_results(filename: str, project_id: str) -> pd.DataFrame:
    """
    Query results from postgres database for project id.
    Save results to a csv file.
    Load pandas dataframe from this csv file.
    Parse timestamp as datetime object and add attribute "day" for each result.
    Return None if there are no results for this project.
    Otherwise return dataframe.

    Parameters
    ----------
    filename: str
    project_id: str
    """

    sql_query = sql.SQL(
        """
        COPY (
            SELECT *
            FROM results
            WHERE project_id = {}
        ) TO STDOUT WITH CSV HEADER
        """
    ).format(sql.Literal(project_id))
    write_sql_to_csv(filename, sql_query)

    df = load_df_from_csv(filename)

    if df.empty:
        logger.info(f"there are no results for this project {project_id}")
        return None
    else:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["day"] = df["timestamp"].apply(
            lambda x: datetime.datetime(year=x.year, month=x.month, day=x.day)
        )
        logger.info(f"added day attribute for results for {project_id}")
        return df


def get_tasks(filename: str, project_id: str) -> pd.DataFrame:
    """
    Check if tasks have been downloaded already.
    If not: Query tasks from postgres database for project id and
    save tasks to a csv file.
    Then load pandas dataframe from this csv file.
    Return dataframe.

    Parameters
    ----------
    filename: str
    project_id: str
    """

    if os.path.isfile(filename):
        logger.info(f"file {filename} already exists for {project_id}. skip download.")
        pass
    else:

        sql_query = sql.SQL(
            """
            COPY (
                SELECT project_id, group_id, task_id, ST_AsText(geom) as geom
                FROM tasks
                WHERE project_id = {}
            ) TO STDOUT WITH CSV HEADER
            """
        ).format(sql.Literal(project_id))
        write_sql_to_csv(filename, sql_query)

    df = load_df_from_csv(filename)
    return df


def get_groups(filename: str, project_id: str) -> pd.DataFrame:
    """
    Check if groups have been downloaded already.
    If not: Query groups from postgres database for project id and
    save groups to a csv file.
    Then load pandas dataframe from this csv file.
    Return dataframe.

    Parameters
    ----------
    filename: str
    project_id: str
    """

    if os.path.isfile(filename):
        logger.info(f"file {filename} already exists for {project_id}. skip download.")
        pass
    else:
        sql_query = sql.SQL(
            """
            COPY (
                SELECT *, (required_count+finished_count) as number_of_users_required
                FROM groups
                WHERE project_id = {}
            ) TO STDOUT WITH CSV HEADER
            """
        ).format(sql.Literal(project_id))
        write_sql_to_csv(filename, sql_query)

    df = load_df_from_csv(filename)
    return df


def calc_agreement(total: int, no: int, yes: int, maybe: int, bad: int) -> float:
    """
    for each task the "agreement" is computed as defined by Scott's Pi
    Scott's Pi is a measure for inter-rater reliability
    https://en.wikipedia.org/wiki/Scott%27s_Pi
    """

    # TODO: currently this is implemented only for the 4 given categories

    if total == 1:
        agreement = 1.0
    else:
        agreement = (
            1.0
            / (total * (total - 1))
            * (
                (no * (no - 1))
                + (yes * (yes - 1))
                + (maybe * (maybe - 1))
                + (bad * (bad - 1))
            )
        )

    return agreement


def calc_share(total: int, no: int, yes: int, maybe: int, bad: int) -> List[float]:
    """
    Calculate the share of each category ("no", "yes", "maybe", "bad") on the total count.

    Parameters
    ----------
    total
    no
    yes
    maybe
    bad

    Returns
    -------

    """

    no_share = no / total
    yes_share = yes / total
    maybe_share = maybe / total
    bad_share = bad / total

    return [no_share, yes_share, maybe_share, bad_share]


def calc_count(row) -> List[int]:
    """
    Check if a count exists for each category ("no", "yes", "maybe", "bad").
    Then calculate total count as the sum of all categories.

    Parameters
    ----------
    row

    Returns
    -------

    """

    try:
        no_count = row[0]
    except KeyError:
        no_count = 0

    try:
        yes_count = row[1]
    except KeyError:
        yes_count = 0

    try:
        maybe_count = row[2]
    except KeyError:
        maybe_count = 0

    try:
        bad_count = row[3]
    except KeyError:
        bad_count = 0

    total_count = no_count + yes_count + maybe_count + bad_count
    assert total_count > 0, "Total count for result must be bigger than zero."

    return [total_count, no_count, yes_count, maybe_count, no_count]


def get_agg_results_by_task_id(
    results_df: pd.DataFrame, tasks_df: pd.DataFrame
) -> pd.DataFrame:
    """
    For each task several users contribute results.
    Get agg_results dataframe by aggregating results df by task_id, group_id and project_id.
    Calculate the following attributes to agg_results dataframe:
    total_count, 0_count, 1_count, 2_count, 3_count
    0_share, 1_share, 2_share, 3_share.
    Calculate "agreement" for each task based on Scott's Pi.
    Perform a left join for agg_results df with tasks dataframe to add the task geometry.
    Return aggregated results dataframe.

    Parameters
    ----------
    results_df: pd.DataFrame
    tasks_df: pd.DataFrame
    """

    results_by_task_id_df = (
        results_df.groupby(["project_id", "group_id", "task_id", "result"])
        .size()
        .unstack(fill_value=0)
    )

    # calculate total count and check if other counts are defined
    results_by_task_id_df[["total_count", 0, 1, 2, 3]] = results_by_task_id_df.apply(
        lambda row: calc_count(row), axis=1, result_type="expand"
    )

    # calculate share based on counts
    results_by_task_id_df[
        ["0_share", "1_share", "2_share", "3_share"]
    ] = results_by_task_id_df.apply(
        lambda row: calc_share(row["total_count"], row[0], row[1], row[2], row[3]),
        axis=1,
        result_type="expand",
    )

    # calculate agreement
    results_by_task_id_df["agreement"] = results_by_task_id_df.apply(
        lambda row: calc_agreement(row["total_count"], row[0], row[1], row[2], row[3]),
        axis=1,
    )
    logger.info(f"calculated agreement")

    # add task geometry using left join
    agg_results_df = results_by_task_id_df.merge(
        tasks_df[["geom", "task_id"]], left_on="task_id", right_on="task_id"
    )
    logger.info(f"added geometry to aggregated results")

    # rename columns, ogr2ogr will fail otherwise
    agg_results_df.rename(
        columns={0: "0_count", 1: "1_count", 2: "2_count", 3: "3_count"}, inplace=True
    )

    return agg_results_df


def get_per_project_statistics(project_id: str, project_info: pd.Series) -> dict:
    """
    The function calculates all project related statistics.
    Always save results to csv file.
    Save groups and tasks to csv file, if not downloaded before.
    If there are new results, this function will:
    - Save aggregated results to csv file and GeoJSON file.
    - Save project history to csv file.
    - return the most recent statistics as a dictionary
    The returned dictionary will be used by generate_stats.py to update the projects_dynamic.csv
    """

    # set filenames
    results_filename = f"{DATA_PATH}/api-data/results/results_{project_id}.csv"
    tasks_filename = f"{DATA_PATH}/api-data/tasks/tasks_{project_id}.csv"
    groups_filename = f"{DATA_PATH}/api-data/groups/groups_{project_id}.csv"
    agg_results_filename = (
        f"{DATA_PATH}/api-data/agg_results/agg_results_{project_id}.csv"
    )
    project_stats_by_date_filename = (
        f"{DATA_PATH}/api-data/history/history_{project_id}.csv"
    )

    # load data from postgres or local storage if already downloaded
    results_df = get_results(results_filename, project_id)

    if results_df is None:
        logger.info(f"no results: skipping per project stats for {project_id}")
        return {}
    else:
        groups_df = get_groups(groups_filename, project_id)
        tasks_df = get_tasks(tasks_filename, project_id)

        # aggregate results by task id
        agg_results_df = get_agg_results_by_task_id(results_df, tasks_df)
        agg_results_df.to_csv(agg_results_filename, index_label="idx")
        logger.info(f"saved agg results for {project_id}: {agg_results_filename}")
        geojson_functions.csv_to_geojson(agg_results_filename, "geom")

        if any("maxar" in s for s in project_info["tile_server_names"]):
            add_metadata_to_csv(agg_results_filename)
            geojson_functions.add_metadata_to_geojson(agg_results_filename)

        project_stats_by_date_df = project_stats_by_date.get_project_history(
            results_df, groups_df
        )
        project_stats_by_date_df["project_id"] = project_id
        project_stats_by_date_df.to_csv(project_stats_by_date_filename)
        logger.info(
            f"saved project stats by date for {project_id}: {project_stats_by_date_filename}"
        )

        project_stats_dict = {
            "project_id": project_id,
            "progress": project_stats_by_date_df["cum_progress"].iloc[-1],
            "number_of_users": project_stats_by_date_df["cum_number_of_users"].iloc[-1],
            "number_of_results": project_stats_by_date_df["cum_number_of_results"].iloc[
                -1
            ],
            "number_of_results_progress": project_stats_by_date_df[
                "cum_number_of_results_progress"
            ].iloc[-1],
            "day": project_stats_by_date_df.index[-1],
        }

        return project_stats_dict
