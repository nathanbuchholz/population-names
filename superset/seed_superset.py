"""Seed Superset with prebuilt datasets, charts, and dashboards.

Entry point: main() at bottom of file.
Flow: login -> create_saved_queries -> create_datasets -> create charts
      (trends, snapshots, validation) -> build dashboard layouts.
"""

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request

from superset_queries import DATASET_CONFIG, DATASETS, SAVED_QUERIES

logger = logging.getLogger(__name__)

SUPERSET_URL = os.environ.get("SUPERSET_URL", "http://superset:8088")
USERNAME = os.environ.get("SUPERSET_ADMIN_USER", "admin")
PASSWORD = os.environ["SUPERSET_ADMIN_PASSWORD"]

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

_access_token = None
_csrf_token = None


def _request(method, path, body=None, parse=True):
    """Make an authenticated request to the Superset API."""
    global _csrf_token

    url = f"{SUPERSET_URL}{path}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    if _access_token:
        headers["Authorization"] = f"Bearer {_access_token}"

    # Fetch CSRF token for mutating requests
    if _access_token and method in ("POST", "PUT", "DELETE") and _csrf_token is None:
        csrf_req = urllib.request.Request(
            f"{SUPERSET_URL}/api/v1/security/csrf_token/",
            headers={
                "Authorization": f"Bearer {_access_token}",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(csrf_req) as resp:
            _csrf_token = json.loads(resp.read())["result"]

    if _csrf_token and method in ("POST", "PUT", "DELETE"):
        headers["X-CSRFToken"] = _csrf_token
        headers["Referer"] = SUPERSET_URL

    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as resp:
            if parse:
                return json.loads(resp.read())
            return resp.read()
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        logger.error(f"  ERROR {e.code} {method} {path}: {err_body}")
        raise


def login():
    global _access_token
    resp = _request(
        "POST",
        "/api/v1/security/login",
        {
            "username": USERNAME,
            "password": PASSWORD,
            "provider": "db",
            "refresh": True,
        },
    )
    _access_token = resp["access_token"]
    logger.debug("Logged in to Superset API.")


def get_database_id():
    resp = _request("GET", "/api/v1/database/")
    for db in resp.get("result", []):
        if db["database_name"] == "Population Names":
            logger.debug(f"Found database 'Population Names' (id={db['id']}).")
            return db["id"]
    logger.error("'Population Names' database not found in Superset.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Column metadata cache
# ---------------------------------------------------------------------------

_column_cache = {}  # dataset_id -> {column_name -> column_dict}


def get_dataset_columns(ds_id):
    """Return dict of column_name -> column metadata for a dataset."""
    if ds_id not in _column_cache:
        ds = _request("GET", f"/api/v1/dataset/{ds_id}")
        _column_cache[ds_id] = {col["column_name"]: col for col in ds["result"]["columns"]}
    return _column_cache[ds_id]


# ---------------------------------------------------------------------------
# Metric / filter helpers
# ---------------------------------------------------------------------------


def _adhoc_metric(column_meta, aggregate="SUM", label=None):
    """Build an adhoc metric with full column metadata.

    column_meta: full column dict from get_dataset_columns().
    """
    return {
        "expressionType": "SIMPLE",
        "column": {
            "id": column_meta["id"],
            "column_name": column_meta["column_name"],
            "type": column_meta.get("type", ""),
            "type_generic": column_meta.get("type_generic"),
            "filterable": column_meta.get("filterable", True),
            "groupby": column_meta.get("groupby", False),
        },
        "aggregate": aggregate,
        "label": label or f"{aggregate}({column_meta['column_name']})",
    }


def _adhoc_filter(column, value, op="=="):
    return {
        "expressionType": "SIMPLE",
        "clause": "WHERE",
        "subject": column,
        "operator": op,
        "comparator": value,
    }


def _sql_metric(expression, label):
    return {
        "expressionType": "SQL",
        "sqlExpression": expression,
        "label": label,
    }


# ---------------------------------------------------------------------------
# Saved queries
# ---------------------------------------------------------------------------


def create_saved_queries(db_id):
    logger.debug("Creating saved queries...")
    for q in SAVED_QUERIES:
        _request("POST", "/api/v1/saved_query/", {**q, "db_id": db_id})
        logger.debug(f"  Created saved query: {q['label']}")


# ---------------------------------------------------------------------------
# Virtual datasets
# ---------------------------------------------------------------------------


def configure_dataset(ds_id, name):
    """Configure column roles and metrics for a dataset."""
    config = DATASET_CONFIG.get(name)
    if not config:
        return

    ds = _request("GET", f"/api/v1/dataset/{ds_id}")
    columns = ds["result"]["columns"]

    updated_columns = []
    for col in columns:
        is_dim = col["column_name"] in config["dimensions"]
        is_temporal = col["column_name"] == config.get("temporal")
        updated_columns.append(
            {
                "id": col["id"],
                "column_name": col["column_name"],
                "groupby": is_dim,
                "filterable": True,
                "is_dttm": is_temporal,
            }
        )

    metrics = [
        {
            "metric_name": m["metric_name"],
            "expression": m["expression"],
            "d3format": m.get("d3format", ""),
        }
        for m in config["metrics"]
    ]

    payload = {"columns": updated_columns}
    if metrics:
        payload["metrics"] = metrics

    _request("PUT", f"/api/v1/dataset/{ds_id}", payload)
    logger.debug(f"  Configured dataset: {name}")


def create_datasets(db_id):
    """Create all virtual datasets, return dict of name -> id."""
    logger.debug("Creating virtual datasets...")
    result = {}
    for name, sql in DATASETS.items():
        resp = _request(
            "POST",
            "/api/v1/dataset/",
            {
                "database": db_id,
                "schema": "public",
                "table_name": name,
                "sql": sql,
            },
        )
        ds_id = resp["id"]
        result[name] = ds_id
        logger.debug(f"  Created dataset: {name} (id={ds_id})")
        configure_dataset(ds_id, name)
    return result


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------


def create_chart(name, viz_type, datasource_id, dashboard_id, params, description=""):
    params.update(
        {
            "datasource": f"{datasource_id}__table",
            "viz_type": viz_type,
            "color_scheme": "supersetColors",
            "extra_form_data": {},
            "dashboards": [dashboard_id],
        }
    )
    payload = {
        "slice_name": name,
        "viz_type": viz_type,
        "datasource_id": datasource_id,
        "datasource_type": "table",
        "dashboards": [dashboard_id],
        "params": json.dumps(params),
    }
    if description:
        payload["description"] = description
    resp = _request("POST", "/api/v1/chart/", payload)
    chart_id = resp["id"]
    logger.debug(f"  Created chart: {name} (id={chart_id})")
    return chart_id


def create_trends_charts(ds, dashboard_id):
    """Charts for the Name Trends dashboard - time-series focus."""
    logger.debug("Creating trends charts...")
    ids = []

    nd_cols = get_dataset_columns(ds["Name Diversity"])
    ftmy_cols = get_dataset_columns(ds["Forename Trends Multi-Year"])
    ld_cols = get_dataset_columns(ds["Letter Distribution"])
    tns_cols = get_dataset_columns(ds["Top Name Share"])

    # Diversity over time
    ids.append(
        create_chart(
            "Name Diversity Over Time",
            "echarts_timeseries_line",
            ds["Name Diversity"],
            dashboard_id,
            {
                "x_axis": "year",
                "metrics": [
                    _adhoc_metric(nd_cols["unique_names_per_m"], "MAX", "Unique names per 1M pop.")
                ],
                "groupby": ["country"],
                "adhoc_filters": [_adhoc_filter("gender", "Female")],
                "row_limit": 10000,
                "order_desc": False,
                "show_legend": True,
                "rich_tooltip": True,
            },
            description=(
                "Distinct female forenames per million population, by country and year. "
                "Normalised by population so smaller countries are comparable to larger ones."
            ),
        )
    )

    ids.append(
        create_chart(
            "Top-10 Concentration Over Time",
            "echarts_timeseries_line",
            ds["Name Diversity"],
            dashboard_id,
            {
                "x_axis": "year",
                "metrics": [_adhoc_metric(nd_cols["top10_concentration_pct"], "MAX", "Top-10 %")],
                "groupby": ["country"],
                "adhoc_filters": [_adhoc_filter("gender", "Female")],
                "row_limit": 10000,
                "order_desc": False,
                "show_legend": True,
                "rich_tooltip": True,
            },
            description=(
                "Percentage of all female births captured by the 10 most popular names. "
                "A falling line indicates naming is becoming more diverse."
            ),
        )
    )

    # Cross-country name popularity (filtered by dashboard name filter)
    ids.append(
        create_chart(
            "'Nathan' Cross-Country",
            "echarts_timeseries_line",
            ds["Forename Trends Multi-Year"],
            dashboard_id,
            {
                "x_axis": "year",
                "metrics": [_adhoc_metric(ftmy_cols["pct_of_year_total"], "SUM", "% of births")],
                "groupby": ["country"],
                "adhoc_filters": [
                    _adhoc_filter("gender", "Male"),
                    _adhoc_filter("name", "Nathan"),
                ],
                "row_limit": 10000,
                "order_desc": False,
                "show_legend": True,
                "rich_tooltip": True,
            },
            description="Cross-country popularity over time. Use the Male Name filter to change the name shown.",
        )
    )

    ids.append(
        create_chart(
            "'Sarah' Cross-Country",
            "echarts_timeseries_line",
            ds["Forename Trends Multi-Year"],
            dashboard_id,
            {
                "x_axis": "year",
                "metrics": [_adhoc_metric(ftmy_cols["pct_of_year_total"], "SUM", "% of births")],
                "groupby": ["country"],
                "adhoc_filters": [
                    _adhoc_filter("gender", "Female"),
                    _adhoc_filter("name", "Sarah"),
                ],
                "row_limit": 10000,
                "order_desc": False,
                "show_legend": True,
                "rich_tooltip": True,
            },
            description="Cross-country popularity over time. Use the Female Name filter to change the name shown.",
        )
    )

    # Top Name Share Over Time + Letter Distribution
    ids.append(
        create_chart(
            "Top Name Share Over Time",
            "echarts_timeseries_line",
            ds["Top Name Share"],
            dashboard_id,
            {
                "x_axis": "year",
                "metrics": [_adhoc_metric(tns_cols["top_name_pct"], "AVG", "Top name %")],
                "groupby": ["country"],
                "adhoc_filters": [_adhoc_filter("gender", "Female")],
                "row_limit": 10000,
                "order_desc": False,
                "show_legend": True,
                "rich_tooltip": True,
            },
            description=(
                "The #1 female name's share of all births, by country and year. "
                "Shows how naming concentration has declined over time (e.g. Mary 5% -> Emma 2%)."
            ),
        )
    )

    ids.append(
        create_chart(
            "Letter Distribution",
            "pivot_table_v2",
            ds["Letter Distribution"],
            dashboard_id,
            {
                "groupbyColumns": ["first_letter"],
                "groupbyRows": ["country"],
                "metrics": [_adhoc_metric(ld_cols["letter_pct"], "MAX", "Letter %")],
                "valueFormat": ".1f",
                "colOrder": "key_a_to_z",
                "rowOrder": "key_a_to_z",
                "conditional_formatting": [
                    {
                        "column": "Letter %",
                        "operator": ">",
                        "targetValue": 0,
                        "colorScheme": "#E6F3F0",
                    }
                ],
                "row_limit": 10000,
            },
            description=(
                "Share of baby names starting with each letter, by country (latest year, all genders). "
                "Reveals cross-country letter preferences."
            ),
        )
    )

    return ids


def create_snapshot_charts(ds, dashboard_id):
    """Charts for the Name Snapshots dashboard - point-in-time focus."""
    logger.debug("Creating snapshot charts...")
    ids = []

    fr_cols = get_dataset_columns(ds["Forename Rankings"])
    sr_cols = get_dataset_columns(ds["Surname Rankings"])

    # Top US forenames + top surnames
    ids.append(
        create_chart(
            "Top 10 US Forenames",
            "echarts_timeseries_bar",
            ds["Forename Rankings"],
            dashboard_id,
            {
                "x_axis": "name",
                "metrics": [_adhoc_metric(fr_cols["pct_of_year_total"], "SUM", "% of births")],
                "groupby": ["gender"],
                "adhoc_filters": [
                    _adhoc_filter("country_code", "US"),
                    _adhoc_filter("rank", 10, "<="),
                ],
                "row_limit": 50,
                "order_desc": True,
                "show_legend": True,
                "x_axis_sort_asc": False,
                "x_axis_sort_series": "sum",
                "x_axis_sort_series_ascending": False,
                "xAxisLabelRotation": 45,
                "truncateXAxis": False,
            },
            description="Most popular US baby names in the latest available year (% of births), split by gender.",
        )
    )

    ids.append(
        create_chart(
            "Top 10 US Surnames",
            "echarts_timeseries_bar",
            ds["Surname Rankings"],
            dashboard_id,
            {
                "x_axis": "name",
                "metrics": [_adhoc_metric(sr_cols["pct_of_year_total"], "SUM", "% of population")],
                "groupby": [],
                "adhoc_filters": [
                    _adhoc_filter("country_code", "US"),
                    _adhoc_filter("rank", 11, "<="),
                    _adhoc_filter("rank", 1, ">"),
                ],
                "row_limit": 50,
                "order_desc": True,
                "show_legend": False,
                "x_axis_sort_asc": False,
                "x_axis_sort_series": "sum",
                "x_axis_sort_series_ascending": False,
                "xAxisLabelRotation": 45,
                "truncateXAxis": False,
            },
            description="Ten most common US surnames from the 2010 Census (% of population).",
        )
    )

    # Gender-neutral + cross-country
    ids.append(
        create_chart(
            "Most Gender-Neutral Names (by share of births)",
            "table",
            ds["Gender-Neutral Names"],
            dashboard_id,
            {
                "all_columns": [
                    "name",
                    "country",
                    "male_count",
                    "female_count",
                    "pct_of_births",
                    "balance_pct",
                ],
                "adhoc_filters": [],
                "row_limit": 1000,
                "order_desc": True,
                "order_by_cols": ['["pct_of_births", false]'],
                "column_config": {
                    "male_count": {"d3NumberFormat": ",d"},
                    "female_count": {"d3NumberFormat": ",d"},
                    "pct_of_births": {"d3NumberFormat": ".2f", "suffix": "%"},
                    "balance_pct": {"d3NumberFormat": ".1f", "suffix": "%"},
                },
            },
            description=(
                "Names given to both boys and girls, sorted by popularity (% of births). "
                "Balance % ranges 0-100 where 100 = perfectly even gender split. "
                "Filtered to names with balance >= 20%."
            ),
        )
    )

    ids.append(
        create_chart(
            "Cross-Country Names",
            "table",
            ds["Cross-Country Names"],
            dashboard_id,
            {
                "all_columns": ["name", "gender", "avg_pct_of_births"],
                "adhoc_filters": [],
                "row_limit": 1000,
                "order_desc": True,
                "order_by_cols": ['["avg_pct_of_births", false]'],
                "column_config": {
                    "avg_pct_of_births": {"d3NumberFormat": ".2f", "suffix": "%"},
                },
            },
            description=(
                "Names that appear in ALL countries in the dataset. "
                "Ranked by average % of births across countries."
            ),
        )
    )

    # Country signature names
    ids.append(
        create_chart(
            "Country Signature Names",
            "table",
            ds["Country Signature Names"],
            dashboard_id,
            {
                "all_columns": [
                    "name",
                    "gender",
                    "country",
                    "local_pct",
                    "global_avg_pct",
                    "distinctiveness_ratio",
                ],
                "adhoc_filters": [],
                "row_limit": 1000,
                "order_desc": True,
                "order_by_cols": ['["distinctiveness_ratio", false]'],
                "column_config": {
                    "local_pct": {"d3NumberFormat": ".2f", "suffix": "%"},
                    "global_avg_pct": {"d3NumberFormat": ".2f", "suffix": "%"},
                    "distinctiveness_ratio": {"d3NumberFormat": ".1f"},
                },
            },
            description=(
                "Names that are distinctively popular in one country compared to the global average. "
                "Distinctiveness ratio = local % / global avg %. "
                "High ratio means the name is unusually popular in that country (e.g. Aoife in Ireland)."
            ),
        )
    )

    # Big number totals
    ids.append(
        create_chart(
            "Total Distinct Forenames",
            "big_number_total",
            ds["Forename Trends"],
            dashboard_id,
            {
                "metric": _sql_metric("COUNT(DISTINCT name)", "Distinct forenames"),
                "adhoc_filters": [],
                "header_font_size": 0.4,
                "subheader": "unique forenames in the database",
                "number_format": "SMART_NUMBER",
            },
            description="Total number of unique forename spellings across all countries, genders, and years.",
        )
    )

    ids.append(
        create_chart(
            "Total Distinct Surnames",
            "big_number_total",
            ds["Surname Trends"],
            dashboard_id,
            {
                "metric": _sql_metric("COUNT(DISTINCT name)", "Distinct surnames"),
                "adhoc_filters": [],
                "header_font_size": 0.4,
                "subheader": "unique surnames in the database",
                "number_format": "SMART_NUMBER",
            },
            description="Total number of unique surname spellings across all countries and years.",
        )
    )

    return ids


def create_validation_charts(ds, dashboard_id):
    """Charts for the Data Validation dashboard - developer-facing quality only."""
    logger.debug("Creating validation charts...")
    ids = []

    rsc_cols = get_dataset_columns(ds["Raw Source Counts"])
    fbc_cols = get_dataset_columns(ds["Forenames by Country"])
    fyc_cols = get_dataset_columns(ds["Forename Year Coverage"])

    # Raw source health
    ids.append(
        create_chart(
            "Raw Source Row Counts",
            "echarts_timeseries_bar",
            ds["Raw Source Counts"],
            dashboard_id,
            {
                "x_axis": "source",
                "metrics": [_adhoc_metric(rsc_cols["row_count"], "MAX", "Rows")],
                "groupby": [],
                "adhoc_filters": [],
                "row_limit": 50,
                "order_desc": True,
                "show_legend": False,
                "x_axis_sort_asc": True,
            },
            description="Row count in each raw source table after the latest ingest.",
        )
    )

    ids.append(
        create_chart(
            "Empty Sources (Alert)",
            "table",
            ds["Empty Sources"],
            dashboard_id,
            {
                "all_columns": ["source", "row_count"],
                "adhoc_filters": [],
                "row_limit": 50,
                "order_desc": False,
                "column_config": {
                    "row_count": {"d3NumberFormat": ",d"},
                },
                "conditional_formatting": [
                    {
                        "column": "row_count",
                        "operator": "=",
                        "targetValue": 0,
                        "colorScheme": "#EF1D1D",
                    },
                ],
            },
            description="Row counts for all raw sources. Zero-row sources are highlighted red.",
        )
    )

    # Volume by country
    ids.append(
        create_chart(
            "Forenames by Country & Gender",
            "echarts_timeseries_bar",
            ds["Forenames by Country"],
            dashboard_id,
            {
                "x_axis": "country",
                "metrics": [_adhoc_metric(fbc_cols["row_count"], "MAX", "Rows")],
                "groupby": ["gender"],
                "adhoc_filters": [],
                "row_limit": 50,
                "order_desc": True,
                "show_legend": True,
            },
            description="Total forename rows per country, split by gender. Validates relative data volume across sources.",
        )
    )

    ids.append(
        create_chart(
            "Forename Year Coverage",
            "pivot_table_v2",
            ds["Forename Year Coverage"],
            dashboard_id,
            {
                "groupbyColumns": ["year"],
                "groupbyRows": ["country"],
                "metrics": [_adhoc_metric(fyc_cols["row_count"], "MAX", "Rows")],
                "valueFormat": ",d",
                "colOrder": "key_a_to_z",
                "rowOrder": "key_a_to_z",
                "conditional_formatting": [
                    {
                        "column": "Rows",
                        "operator": ">",
                        "targetValue": 0,
                        "colorScheme": "#E6F3F0",
                    }
                ],
                "row_limit": 10000,
            },
            description="Heatmap of which years have forename data for each country. Gaps indicate missing years.",
        )
    )

    # Source quality scorecard + rejected rows
    ids.append(
        create_chart(
            "Source Quality Scorecard",
            "table",
            ds["Source Quality Scorecard"],
            dashboard_id,
            {
                "all_columns": [
                    "source_id",
                    "row_count",
                    "ingest_success_count",
                    "ingest_fail_count",
                    "last_run_at",
                    "last_success_rows",
                ],
                "adhoc_filters": [],
                "row_limit": 50,
                "order_desc": False,
                "column_config": {
                    "row_count": {"d3NumberFormat": ",d"},
                    "last_success_rows": {"d3NumberFormat": ",d"},
                },
            },
            description="Per-source ingest health: row counts, success/failure tallies, and last successful load.",
        )
    )

    ids.append(
        create_chart(
            "Rejected Rows by Source",
            "table",
            ds["Rejected Rows"],
            dashboard_id,
            {
                "all_columns": ["source_table", "filename", "rejection_reason", "rejected_count"],
                "adhoc_filters": [],
                "row_limit": 200,
                "order_desc": True,
                "order_by_cols": ['["rejected_count", false]'],
                "column_config": {
                    "rejected_count": {"d3NumberFormat": ",d"},
                },
            },
            description="Rows rejected during staging, grouped by source, file, and rejection reason. No data indicates no rejected rows.",
        )
    )

    return ids


# ---------------------------------------------------------------------------
# Dashboard layout
# ---------------------------------------------------------------------------


def _build_layout(title, rows, chart_meta):
    """Build a position_json for a dashboard with named rows of charts.

    rows: list of lists of chart_ids, e.g. [[c1, c2], [c3, c4]]
    chart_meta: dict of chart_id -> slice_name
    """
    all_chart_ids = [cid for row in rows for cid in row]
    row_ids = [f"ROW-row{i}" for i in range(len(rows))]

    position = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {
            "type": "ROOT",
            "id": "ROOT_ID",
            "children": ["GRID_ID"],
        },
        "GRID_ID": {
            "type": "GRID",
            "id": "GRID_ID",
            "parents": ["ROOT_ID"],
            "children": row_ids,
        },
        "HEADER_ID": {
            "type": "HEADER",
            "id": "HEADER_ID",
            "meta": {"text": title},
        },
    }

    for row_id, chart_ids in zip(row_ids, rows):
        width = 12 // len(chart_ids)
        position[row_id] = {
            "type": "ROW",
            "id": row_id,
            "parents": ["ROOT_ID", "GRID_ID"],
            "children": [f"CHART-{cid}" for cid in chart_ids],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        }
        for cid in chart_ids:
            position[f"CHART-{cid}"] = {
                "type": "CHART",
                "id": f"CHART-{cid}",
                "parents": ["ROOT_ID", "GRID_ID", row_id],
                "children": [],
                "meta": {
                    "width": width,
                    "height": 50,
                    "chartId": cid,
                    "sliceName": chart_meta.get(cid, ""),
                },
            }

    metadata = {
        "chart_configuration": {
            str(cid): {
                "id": cid,
                "crossFilters": {
                    "scope": "global",
                    "chartsInScope": [x for x in all_chart_ids if x != cid],
                },
            }
            for cid in all_chart_ids
        },
        "global_chart_configuration": {
            "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
            "chartsInScope": all_chart_ids,
        },
        "color_scheme": "supersetColors",
        "cross_filters_enabled": True,
        "default_filters": "{}",
        "expanded_slices": {str(cid): True for cid in all_chart_ids},
        "refresh_frequency": 0,
        "color_scheme_domain": [],
        "label_colors": {},
        "shared_label_colors": [],
        "map_label_colors": {},
    }

    return position, metadata


def create_dashboard(title, slug, rows, chart_names):
    """Create a dashboard and set its layout.

    rows: list of lists of chart_ids
    chart_names: dict of chart_id -> name
    """
    resp = _request(
        "POST",
        "/api/v1/dashboard/",
        {
            "dashboard_title": title,
            "published": True,
            "slug": slug,
        },
    )
    dash_id = resp["id"]
    logger.debug(f"  Created dashboard: {title} (id={dash_id})")

    position, metadata = _build_layout(title, rows, chart_names)
    _request(
        "PUT",
        f"/api/v1/dashboard/{dash_id}",
        {
            "position_json": json.dumps(position),
            "json_metadata": json.dumps(metadata),
        },
    )
    logger.debug("  Updated dashboard layout.")
    return dash_id


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def wait_for_superset(max_wait=120):
    logger.debug(f"Waiting for Superset API at {SUPERSET_URL}...")
    start = time.time()
    while time.time() - start < max_wait:
        try:
            req = urllib.request.Request(f"{SUPERSET_URL}/health")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    logger.debug("Superset API is ready.")
                    return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(2)
    logger.error("Timed out waiting for Superset API.")
    sys.exit(1)


def already_seeded():
    try:
        resp = _request("GET", "/api/v1/dashboard/")
        return any(d.get("slug") == "name-trends" for d in resp.get("result", []))
    except Exception:
        return False


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    wait_for_superset()
    login()

    if already_seeded():
        logger.debug("Dashboard 'name-trends' already exists - skipping seed.")
        return

    db_id = get_database_id()
    create_saved_queries(db_id)
    ds = create_datasets(db_id)

    # -- Name Trends dashboard ------------------------------------------------
    trends_dash = _request(
        "POST",
        "/api/v1/dashboard/",
        {
            "dashboard_title": "Name Trends",
            "published": True,
            "slug": "name-trends",
        },
    )["id"]
    logger.debug(f"  Created dashboard: Name Trends (id={trends_dash})")

    trends_ids = create_trends_charts(ds, trends_dash)
    trends_names = {
        trends_ids[0]: "Name Diversity Over Time",
        trends_ids[1]: "Top-10 Concentration Over Time",
        trends_ids[2]: "'Nathan' Cross-Country",
        trends_ids[3]: "'Sarah' Cross-Country",
        trends_ids[4]: "Top Name Share Over Time",
        trends_ids[5]: "Letter Distribution",
    }
    # Cross-country charts first (top row), then diversity, then others
    position, metadata = _build_layout(
        "Name Trends",
        [trends_ids[2:4], trends_ids[0:2], trends_ids[4:6]],
        trends_names,
    )
    # Add native filters for name selection (dropdown with default values)
    ftmy_ds_id = ds["Forename Trends Multi-Year"]
    male_chart_id = trends_ids[2]
    female_chart_id = trends_ids[3]
    metadata["native_filter_configuration"] = [
        {
            "id": "NATIVE_FILTER-male-name",
            "name": "Male Name",
            "filterType": "filter_select",
            "targets": [{"datasetId": ftmy_ds_id, "column": {"name": "name"}}],
            "defaultDataMask": {
                "filterState": {
                    "value": ["Nathan"],
                    "label": "Nathan",
                },
                "extraFormData": {
                    "filters": [{"col": "name", "op": "IN", "val": ["Nathan"]}],
                },
            },
            "scope": {
                "rootPath": ["ROOT_ID"],
                "excluded": [cid for cid in trends_ids if cid != male_chart_id],
            },
            "controlValues": {
                "enableEmptyFilter": False,
                "defaultToFirstItem": False,
                "multiSelect": False,
                "searchAllOptions": True,
                "inverseSelection": False,
            },
            "chartsInScope": [male_chart_id],
        },
        {
            "id": "NATIVE_FILTER-female-name",
            "name": "Female Name",
            "filterType": "filter_select",
            "targets": [{"datasetId": ftmy_ds_id, "column": {"name": "name"}}],
            "defaultDataMask": {
                "filterState": {
                    "value": ["Sarah"],
                    "label": "Sarah",
                },
                "extraFormData": {
                    "filters": [{"col": "name", "op": "IN", "val": ["Sarah"]}],
                },
            },
            "scope": {
                "rootPath": ["ROOT_ID"],
                "excluded": [cid for cid in trends_ids if cid != female_chart_id],
            },
            "controlValues": {
                "enableEmptyFilter": False,
                "defaultToFirstItem": False,
                "multiSelect": False,
                "searchAllOptions": True,
                "inverseSelection": False,
            },
            "chartsInScope": [female_chart_id],
        },
    ]
    metadata["filter_bar_orientation"] = "VERTICAL"
    _request(
        "PUT",
        f"/api/v1/dashboard/{trends_dash}",
        {
            "position_json": json.dumps(position),
            "json_metadata": json.dumps(metadata),
        },
    )
    logger.debug("  Updated trends dashboard layout.")

    # -- Name Snapshots dashboard ---------------------------------------------
    snapshots_dash = _request(
        "POST",
        "/api/v1/dashboard/",
        {
            "dashboard_title": "Name Snapshots",
            "published": True,
            "slug": "name-snapshots",
        },
    )["id"]
    logger.debug(f"  Created dashboard: Name Snapshots (id={snapshots_dash})")

    snapshot_ids = create_snapshot_charts(ds, snapshots_dash)
    snapshot_names = {
        snapshot_ids[0]: "Top 10 US Forenames",
        snapshot_ids[1]: "Top 10 US Surnames",
        snapshot_ids[2]: "Most Gender-Neutral Names (by share of births)",
        snapshot_ids[3]: "Cross-Country Names",
        snapshot_ids[4]: "Country Signature Names",
        snapshot_ids[5]: "Total Distinct Forenames",
        snapshot_ids[6]: "Total Distinct Surnames",
    }
    position, metadata = _build_layout(
        "Name Snapshots",
        [snapshot_ids[0:2], snapshot_ids[2:4], [snapshot_ids[4]], snapshot_ids[5:7]],
        snapshot_names,
    )
    _request(
        "PUT",
        f"/api/v1/dashboard/{snapshots_dash}",
        {
            "position_json": json.dumps(position),
            "json_metadata": json.dumps(metadata),
        },
    )
    logger.debug("  Updated snapshots dashboard layout.")

    # -- Data Validation dashboard --------------------------------------------
    val_dash = _request(
        "POST",
        "/api/v1/dashboard/",
        {
            "dashboard_title": "Data Validation",
            "published": True,
            "slug": "data-validation",
        },
    )["id"]
    logger.debug(f"  Created dashboard: Data Validation (id={val_dash})")

    val_ids = create_validation_charts(ds, val_dash)
    val_names = {
        val_ids[0]: "Raw Source Row Counts",
        val_ids[1]: "Empty Sources (Alert)",
        val_ids[2]: "Forenames by Country & Gender",
        val_ids[3]: "Forename Year Coverage",
        val_ids[4]: "Source Quality Scorecard",
        val_ids[5]: "Rejected Rows by Source",
    }
    position, metadata = _build_layout(
        "Data Validation",
        [val_ids[0:2], val_ids[2:4], val_ids[4:6]],
        val_names,
    )
    _request(
        "PUT",
        f"/api/v1/dashboard/{val_dash}",
        {
            "position_json": json.dumps(position),
            "json_metadata": json.dumps(metadata),
        },
    )
    logger.debug("  Updated validation dashboard layout.")

    logger.debug("Superset seeding complete!")


if __name__ == "__main__":
    main()
